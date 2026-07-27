#!/usr/bin/env python3
"""
Entry point: run every strategy on the configured data and emit the report.

Usage
-----
    python run.py                       # uses data/0050.csv, data/2330.csv
    python run.py --etf X.csv --tsmc Y.csv
    python run.py --idle-rate 0.01      # credit idle cash 1%/yr (default 0)

If the data files are missing, a clearly-labelled SYNTHETIC dataset is
generated first so the pipeline is runnable out of the box. Replace the CSVs
with real adjusted-price history for real conclusions (see data/README.md).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pandas as pd  # noqa: E402

import data_loader   # noqa: E402
import engine        # noqa: E402
import metrics as metrics_mod  # noqa: E402
import report as report_mod    # noqa: E402
from strategies import STRATEGIES, build_orders  # noqa: E402


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--etf", default=os.path.join(here, "data", "0050.csv"))
    ap.add_argument("--tsmc", default=os.path.join(here, "data", "2330.csv"))
    ap.add_argument("--idle-rate", type=float, default=0.0,
                    help="annual interest credited to idle cash (default 0)")
    ap.add_argument("--lot-size", type=float, default=None,
                    help="force whole-lot buys of this share size (default: fractional)")
    ap.add_argument("--out", default=os.path.join(here, "results"))
    args = ap.parse_args()

    synthetic = False
    if not (os.path.exists(args.etf) and os.path.exists(args.tsmc)):
        print("[run] data files not found -> generating SYNTHETIC illustrative data")
        from generate_synthetic import main as gen
        gen(out_dir=os.path.join(here, "data"))
        synthetic = True
    else:
        # heuristic: our generator leaves a marker file
        synthetic = os.path.exists(os.path.join(here, "data", ".synthetic"))

    etf = data_loader.load_prices(args.etf)
    tsmc = data_loader.load_prices(args.tsmc)
    etf, tsmc = data_loader.align(etf, tsmc)

    start, end = tsmc.index[0].date(), tsmc.index[-1].date()
    data_note = f"{start} ~ {end}（{len(tsmc)} 交易日）" + ("；合成示範資料" if synthetic else "")

    results, labels = {}, {}
    for name, label in STRATEGIES:
        orders = build_orders(name, tsmc, etf)
        sim = engine.run(tsmc, orders, idle_annual_rate=args.idle_rate,
                         lot_size=args.lot_size)
        results[name] = metrics_mod.compute(sim["ledger"], sim["buys"])
        labels[name] = label

    os.makedirs(args.out, exist_ok=True)

    table = report_mod.summary_table(results, labels)
    table.to_csv(os.path.join(args.out, "summary.csv"))

    md = report_mod.to_markdown(results, labels, synthetic, data_note)
    with open(os.path.join(args.out, "report.md"), "w") as f:
        f.write(md)

    # console preview
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print("\n=== SUMMARY (see results/report.md for full narrative) ===\n")
    key_cols = ["Final Assets", "IRR (money-weighted)", "Avg Buy Cost",
                "Avg Idle Cash", "Cash Drag Ratio", "MDD", "Num Buys"]
    print(table[["Description"] + key_cols].to_string())
    print(f"\n[run] wrote {args.out}/summary.csv and {args.out}/report.md")


if __name__ == "__main__":
    main()
