#!/usr/bin/env python3
"""Run the DCA-signal study: benchmarks A-E (+ G2-G6) and answer Q1-Q3.

Usage:
    # real data (two CSVs with Date/Open/Close), signal=0050, target=2330
    python scripts/run_dca.py --signal data/0050.csv --target data/2330.csv

    # offline synthetic demo
    python scripts/run_dca.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from dca import data, engine  # noqa: E402

pd.set_option("display.width", 220)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", help="signal asset CSV (0050)")
    ap.add_argument("--target", help="buy target CSV (2330)")
    ap.add_argument("--budget", type=float, default=50000)
    ap.add_argument("--buy", type=float, default=5000)
    args = ap.parse_args()

    if args.signal and args.target:
        sig = data.load_csv(args.signal)
        tgt = data.load_csv(args.target)
        src = "REAL data"
    else:
        sig, tgt = data.generate_pair()
        src = "SYNTHETIC demo data (offline)"

    results = engine.run_all(sig, tgt, args.budget, args.buy)

    span = f"{tgt.index.min().date()} ~ {tgt.index.max().date()}"
    print("=" * 100)
    print(f"DCA-SIGNAL STUDY  ({src})   target span {span}")
    print("Signal = 0050 down days -> dollar-cost-average into 2330 (TSMC)")
    print("=" * 100)

    rows = []
    for name, r in results.items():
        m = r.metrics
        rows.append({
            "strategy": name,
            "final_assets": round(m["final_assets"]),
            "invested": round(m["total_invested"]),
            "CAGR": round(m["cagr"], 4),
            "IRR": round(m["irr_annual"], 4),
            "avg_cost": round(m["avg_cost"], 2),
            "n_buys": m["n_buys"],
            "buys/mo": round(m["avg_buys_per_month"], 2),
            "wait_d": round(m["avg_wait_days"], 1) if not np.isnan(m["avg_wait_days"]) else np.nan,
            "avg_idle": round(m["avg_idle_cash"]),
            "max_idle": round(m["max_idle_cash"]),
            "MDD": round(m["mdd"], 3),
            "vol": round(m["vol"], 3),
        })
    table = pd.DataFrame(rows).set_index("strategy")
    print(table.to_string())

    # ---- core research questions ----
    C = results["C_0050_blackK"].metrics
    A = results["A_monthly_lump"].metrics
    B = results["B_spread_10x"].metrics
    E = results["E_2330_blackK"].metrics

    print("\n" + "=" * 100)
    print("CORE VERIFICATION")
    print("=" * 100)

    # Q1: does the black-K signal lower the average buy cost?
    better_cost = C["avg_cost"] < min(A["avg_cost"], B["avg_cost"])
    print(f"Q1  avg buy cost:  C(0050 blackK)={C['avg_cost']:.2f}  "
          f"A(lump)={A['avg_cost']:.2f}  B(spread)={B['avg_cost']:.2f}")
    print(f"    -> black-K {'LOWERS' if better_cost else 'does NOT lower'} avg cost vs both benchmarks.")

    # Q2: does cash drag cancel the cost advantage?
    dfa = C["final_assets"] - B["final_assets"]
    print(f"Q2  final assets:  C={C['final_assets']:,.0f}  B={B['final_assets']:,.0f}  "
          f"(diff {dfa:+,.0f})   C avg idle cash = {C['avg_idle_cash']:,.0f}")
    if C["avg_cost"] < B["avg_cost"] and dfa <= 0:
        print("    -> cost edge exists but CASH DRAG cancels it (C ends behind B).")
    elif dfa > 0:
        print("    -> C ends ahead even after cash drag.")
    else:
        print("    -> no cost edge to begin with.")

    # Q3: is 0050 a useful timing signal for 2330? (vs A, B, and vs 2330's own signal E)
    ranked = sorted(results.items(), key=lambda kv: kv[1].metrics["irr_annual"], reverse=True)
    print("Q3  timing signal test — IRR ranking (higher = better):")
    for name, r in ranked:
        print(f"      {name:22s} IRR {r.metrics['irr_annual']:+.4f}  "
              f"final {r.metrics['final_assets']:,.0f}")
    winner = ranked[0][0]
    c_beats_bench = C["irr_annual"] > max(A["irr_annual"], B["irr_annual"])
    print(f"    -> best: {winner}.  0050 black-K {'BEATS' if c_beats_bench else 'does NOT beat'} "
          f"plain DCA (A/B).  vs 2330's own black-K (E): "
          f"{'0050 better' if C['irr_annual'] > E['irr_annual'] else '2330-self better'}.")
    print("\nNote: metrics include leftover cash; IRR treats 50k/month as committed")
    print("capital, so idle cash is penalised. Run with --signal/--target for real data.")


if __name__ == "__main__":
    main()
