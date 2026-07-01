#!/usr/bin/env python3
"""VE v0.2 — full six-layer validation report.

Runs layers 3-6 (layers 1-2 are the transition & robustness studies) and prints
an honest scorecard for each. The headline question: is there a volatility
lifecycle that recurs across time, assets and regimes AND carries trading value?

Usage:
    python scripts/run_validation.py --data data/real
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ve import data, features, phases, validation  # noqa: E402
from ve.config import DEFAULT, PHASES  # noqa: E402

HERE = os.path.dirname(__file__)
pd.set_option("display.width", 200)


def load_all(data_dir):
    anns = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        name = os.path.splitext(os.path.basename(path))[0]
        df = data.load_csv(path)
        anns[name] = phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)
    return anns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sample"))
    ap.add_argument("--horizon", type=int, default=5)
    args = ap.parse_args()

    anns = load_all(args.data)
    if not anns:
        print(f"No CSVs in {args.data}.")
        sys.exit(1)
    H = args.horizon

    # ---------------- Layer 3a: Cross-Time ----------------
    print("=" * 76)
    print("LAYER 3a — CROSS-TIME  (stable across eras, not fit to one market?)")
    print("=" * 76)
    for name, ann in anns.items():
        rows = validation.cross_time(ann, horizon=H)
        aucs = [r["auc"] for r in rows if not np.isnan(r["auc"])]
        tag = "  ".join(f"{r['test']}={r['auc']:.2f}" for r in rows)
        stab = (f"mean {np.mean(aucs):.2f} min {np.min(aucs):.2f} "
                f"std {np.std(aucs):.2f}") if aucs else "n/a"
        print(f"  {name:14s} {tag}   [{stab}]")
    print("  -> want: every era well above 0.50 with small spread (stable regularity).")

    # ---------------- Layer 3b: Cross-Asset ----------------
    print("\n" + "=" * 76)
    print("LAYER 3b — CROSS-ASSET  (trains on row, tests on column)")
    print("=" * 76)
    mat = validation.cross_asset(anns, horizon=H)
    print(mat.round(3).to_string())
    off = mat.where(~np.eye(len(mat), dtype=bool)).stack()
    print(f"  off-diagonal mean AUC = {off.mean():.3f}  "
          f"(high => volatility structure transfers across names/industries)")

    # ---------------- Layer 3c: Regime Robustness ----------------
    print("\n" + "=" * 76)
    print("LAYER 5(regime) — REGIME ROBUSTNESS  (test AUC by market regime)")
    print("=" * 76)
    for name, ann in anns.items():
        r = validation.regime_auc(ann, horizon=H)
        cells = "  ".join(f"{k}={r[k]:.2f}" if not np.isnan(r.get(k, np.nan)) else f"{k}=n/a"
                          for k in ["ALL", "Bull", "Bear", "Range"])
        print(f"  {name:14s} {cells}")
    print("  -> which regimes hold up; where the model needs re-defining.")

    # ---------------- Layer 4: Information Gain ----------------
    print("\n" + "=" * 76)
    print("LAYER 4 — INFORMATION GAIN  (do new features add real skill?)")
    print("=" * 76)
    for name, ann in anns.items():
        ig = validation.information_gain(ann, horizon=H)
        top = sorted(ig["loo"].items(), key=lambda kv: kv[1], reverse=True)[:3]
        tops = ", ".join(f"{k}+{v:.3f}" for k, v in top)
        print(f"  {name:14s} baseline {ig['baseline_auc']:.3f} -> full "
              f"{ig['full_auc']:.3f}  (gain {ig['gain']:+.3f})")
        print(f"       most informative added features: {tops}")
    print("  -> gain > 0 means volatility features beat {time, HV pct} alone.")

    # ---------------- Layer 5: Oracle Decision Test ----------------
    print("\n" + "=" * 76)
    print("LAYER 5 — ORACLE DECISION TEST  (does a phase have TRADING value?)")
    print("=" * 76)
    agg = {ph: {"dir": [], "long": [], "strad": [], "win": []} for ph in PHASES}
    for name, ann in anns.items():
        o = validation.oracle_test(ann)
        for ph in PHASES:
            if ph in o.index and o.loc[ph].get("n", 0):
                agg[ph]["dir"].append(o.loc[ph]["directional_best"])
                agg[ph]["long"].append(o.loc[ph]["long_only"])
                agg[ph]["strad"].append(o.loc[ph]["straddle_net"])
                agg[ph]["win"].append(o.loc[ph]["straddle_winrate"])
    print(f"  {'phase':12s} {'|move|':>8s} {'long_only':>10s} "
          f"{'straddle_net':>13s} {'strad_win':>10s}")
    for ph in PHASES:
        a = agg[ph]
        if not a["dir"]:
            continue
        print(f"  {ph:12s} {np.mean(a['dir']):8.3f} {np.mean(a['long']):10.3f} "
              f"{np.mean(a['strad']):13.3f} {np.mean(a['win']):10.2f}")
    print("  -> long_only ~0 but |move| large => classification value, not")
    print("     directional value. straddle_net > 0 => a volatility trade exists.")

    # ---------------- Layer 6: Liquidity Hypothesis ----------------
    print("\n" + "=" * 76)
    print("LAYER 6 — LIQUIDITY HYPOTHESIS  (does liquidity lead volatility?)")
    print("=" * 76)
    for name, ann in anns.items():
        lq = validation.liquidity_test(ann, horizon=H)
        print(f"  {name:14s} best lead-lag: volume leads HV by {lq['best_lag']}d "
              f"(corr {lq['best_xcorr']:+.2f})  |  "
              f"pred AUC {lq['auc_price_vol']:.3f} -> {lq['auc_with_liquidity']:.3f} "
              f"(liquidity gain {lq['liquidity_gain']:+.3f})")
    print("  -> positive lead + AUC gain => liquidity may DRIVE the vol cycle")
    print("     (VE as a market-liquidity lifecycle, not just a price cycle).")

    print("\n" + "=" * 76)
    print("Reading order (design v0.2): existence(done) -> not self-referential")
    print("(robustness) -> generality(3) -> new info(4) -> trading value(5) ->")
    print("mechanism(6). VE earns a trading system only if ALL hold on real data.")
    print("=" * 76)


if __name__ == "__main__":
    main()
