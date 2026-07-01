#!/usr/bin/env python3
"""VE end-to-end runner — Phases 1, 2, 3 + charts + success scorecard.

Usage:
    python scripts/run_full.py                      # bundled synthetic sample
    python scripts/run_full.py --data path/to/csvs  # your own OHLCV CSVs
    python scripts/run_full.py --no-charts          # skip PNG generation
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd  # noqa: E402

from ve import (data, features, phases, cycles, report, regimes,  # noqa: E402
                profile, zones, backtest, evaluate)
from ve.config import DEFAULT  # noqa: E402

HERE = os.path.dirname(__file__)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def process(path):
    df = data.load_csv(path)
    feat = features.compute_features(df, DEFAULT)
    ann = phases.classify_phases(feat, DEFAULT)
    zoned = zones.derive_zones(ann, DEFAULT)
    reg = regimes.tag_regime(df["Close"])
    stats = cycles.analyse(ann["PhaseSmooth"])
    prof = profile.phase_profile(ann, horizon=10)
    tc = profile.time_consistency(ann, reg)
    bt_ls = backtest.run_backtest(zoned, DEFAULT, long_short=True)
    bt_lo = backtest.run_backtest(zoned, DEFAULT, long_short=False)
    return {
        "df": df, "ann": ann, "zoned": zoned, "stats": stats, "profile": prof,
        "time_consistency": tc, "bt_ls": bt_ls, "bt_lo": bt_lo,
        "canonical_follow": stats["canonical_follow"],
        "persistence": stats["persistence"],
        "strat_ret": bt_ls["strat_ret"],
        "asset_ret": df["Close"].pct_change().fillna(0.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sample"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output"))
    ap.add_argument("--no-charts", action="store_true")
    args = ap.parse_args()

    csvs = sorted(glob.glob(os.path.join(args.data, "*.csv")))
    if not csvs:
        print(f"No CSVs in {args.data}. Run scripts/generate_sample_data.py first.")
        sys.exit(1)
    os.makedirs(args.out, exist_ok=True)

    assets = {}
    stats_for_report = {}
    for path in csvs:
        name = os.path.splitext(os.path.basename(path))[0]
        a = process(path)
        assets[name] = a
        stats_for_report[name] = a["stats"]

    # ---------------- PHASE 1 ----------------
    print(report.answer_research_questions(stats_for_report))

    # ---------------- PHASE 2 ----------------
    print("\n" + "=" * 68)
    print("PHASE 2 — PHASE PROFILES (forward 10-day stats per asset)")
    print("=" * 68)
    for name, a in assets.items():
        print(f"\n[{name}]")
        p = a["profile"][["n_days", "avg_duration", "fwd_vol",
                          "fwd_vol_change", "fwd_move", "canonical_follow"]]
        print(p.round(4).to_string())
        v = profile.profile_validates(a["profile"])
        print(f"  profile checks passed: {v['passed']}/4  "
              f"(compression quietest={v['compression_is_quietest']}, "
              f"expands_next={v['compression_expands_next']}, "
              f"exhaustion loudest={v['exhaustion_is_loudest']}, "
              f"cools_next={v['exhaustion_cools_next']})")

    # ---------------- PHASE 3 ----------------
    print("\n" + "=" * 68)
    print("PHASE 3 — BUILD/EXIT ZONE BACKTEST (long/short, cycle-derived)")
    print("=" * 68)
    keys = ["n_trades", "win_rate", "total_return", "cagr", "sharpe",
            "max_drawdown", "buy_hold_return", "avg_long_ret", "avg_short_ret"]
    bt_table = pd.DataFrame(
        {name: {k: a["bt_ls"]["metrics"][k] for k in keys}
         for name, a in assets.items()}).T
    print(bt_table.round(4).to_string())

    # ---------------- SUCCESS SCORECARD (§11) ----------------
    print("\n" + "=" * 68)
    print("SUCCESS CRITERIA SCORECARD (design §11)")
    print("=" * 68)
    scorecard = evaluate.evaluate(assets)
    for crit, row in scorecard.iterrows():
        print(f"[{row['result']}] {crit}")
        print(f"        {row['detail']}")
    n_pass = int((scorecard["result"] == "PASS").sum())
    print(f"\nSCORE: {n_pass}/6 criteria met.")

    # ---------------- CHARTS ----------------
    if not args.no_charts:
        from ve import plotting
        for name, a in assets.items():
            out = os.path.join(args.out, f"{name}.png")
            plotting.plot_asset(a["zoned"], a["bt_ls"], name, out)
            a["ann"].to_csv(os.path.join(args.out, f"{name}_annotated.csv"))
        print(f"\nCharts + annotated CSVs written to {os.path.abspath(args.out)}/")

    print("\nReminder: results are on the data supplied. The bundled sample has a "
          "PLANTED cycle, so strong scores confirm the engine works — real "
          "conclusions need real market data (see README data note).")


if __name__ == "__main__":
    main()
