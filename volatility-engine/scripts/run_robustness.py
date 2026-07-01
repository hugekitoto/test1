#!/usr/bin/env python3
"""VE v0.2 — Robustness / "is the predictability real?" check.

The transition model scores a high AUC, but part of that could be mechanical
(phases are defined by the same volatility features we predict from). This
script decomposes it honestly with four controls per asset:

  full            headline AUC (features -> phase-end)
  placebo         labels shuffled -> should collapse to ~0.50 (no leakage)
  time_only       duration/hazard structure alone
  external_target predict a target NOT defined by our phases (future realised
                  vol regime) -> if this stays high, the skill is genuine

Usage:
    python scripts/run_robustness.py --data data/real
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402

from ve import data, features, phases, transitions  # noqa: E402
from ve.config import DEFAULT  # noqa: E402

HERE = os.path.dirname(__file__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sample"))
    ap.add_argument("--horizon", type=int, default=5)
    args = ap.parse_args()

    csvs = sorted(glob.glob(os.path.join(args.data, "*.csv")))
    if not csvs:
        print(f"No CSVs in {args.data}.")
        sys.exit(1)

    print("=" * 74)
    print("VE v0.2 — ROBUSTNESS CHECK  (is the transition predictability REAL?)")
    print("=" * 74)
    print(f"{'asset':14s} {'full':>7s} {'placebo':>8s} {'time_only':>10s} "
          f"{'external':>9s} {'ext_placebo':>12s}")
    print("-" * 74)

    agg = {k: [] for k in ["full", "placebo", "time_only",
                           "external_target", "external_placebo"]}
    for path in csvs:
        name = os.path.splitext(os.path.basename(path))[0]
        df = data.load_csv(path)
        ann = phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)
        r = transitions.robustness_check(ann, horizon=args.horizon)
        for k in agg:
            if not np.isnan(r[k]):
                agg[k].append(r[k])
        print(f"{name:14s} {r['full']:7.3f} {r['placebo']:8.3f} "
              f"{r['time_only']:10.3f} {r['external_target']:9.3f} "
              f"{r['external_placebo']:12.3f}")

    print("-" * 74)
    m = {k: float(np.mean(v)) if v else float("nan") for k, v in agg.items()}
    print(f"{'MEAN':14s} {m['full']:7.3f} {m['placebo']:8.3f} "
          f"{m['time_only']:10.3f} {m['external_target']:9.3f} "
          f"{m['external_placebo']:12.3f}")

    print("\n" + "=" * 74)
    print("READING THE RESULT")
    print("=" * 74)
    ok_placebo = m["placebo"] < 0.56
    print(f"1. Placebo = {m['placebo']:.3f}  "
          f"{'OK (~0.50, no leakage)' if ok_placebo else 'WARNING: too high — possible leakage'}")
    lift = m["full"] - m["time_only"]
    print(f"2. Features add {lift:+.3f} AUC over time-only "
          f"({m['time_only']:.3f} -> {m['full']:.3f})")
    ext = m["external_target"]
    if ext > 0.60:
        verdict = ("GENUINE ✅ — predicts an independent volatility target too, "
                   "so the skill is real, not just self-referential.")
    elif ext > 0.55:
        verdict = "PARTLY genuine ⚠️ — weak but present on the external target."
    else:
        verdict = ("MOSTLY MECHANICAL ❌ — collapses on an independent target; the "
                   "headline AUC is largely an artifact of phase definition.")
    print(f"3. External target = {ext:.3f}  -> {verdict}")
    print("\nBottom line: trust the transition model only to the extent the EXTERNAL")
    print("target AUC (and a ~0.50 placebo) hold up. Predicting volatility is not")
    print("predicting price — a tradeable edge still needs the direction/size step.")


if __name__ == "__main__":
    main()
