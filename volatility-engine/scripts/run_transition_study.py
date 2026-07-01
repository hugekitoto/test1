#!/usr/bin/env python3
"""VE v0.2 — Phase Transition study.

For each asset: fit the transition model, report out-of-sample predictive skill
(AUC vs base rate), show which features drive each transition (candidate
Triggers), and print the hazard curve summary. The headline is the honest
verdict: does the volatility-lifecycle model *predict* the next phase?

Usage:
    python scripts/run_transition_study.py --data data/real     # your data
    python scripts/run_transition_study.py                      # sample data
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ve import data, features, phases, transitions  # noqa: E402
from ve.config import DEFAULT, PHASES  # noqa: E402

HERE = os.path.dirname(__file__)
pd.set_option("display.width", 200)


def top_triggers(coefs: dict, k: int = 3):
    """Return the k features with the largest |coefficient| (signed)."""
    items = sorted(coefs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:k]
    return ", ".join(f"{name}{'+' if c > 0 else '-'}{abs(c):.2f}" for name, c in items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sample"))
    ap.add_argument("--horizon", type=int, default=5,
                    help="predict transition within this many days")
    args = ap.parse_args()

    csvs = sorted(glob.glob(os.path.join(args.data, "*.csv")))
    if not csvs:
        print(f"No CSVs in {args.data}.")
        sys.exit(1)

    all_aucs = {ph: [] for ph in PHASES}
    print("=" * 72)
    print(f"VE v0.2 — PHASE TRANSITION STUDY  (predict transition within "
          f"{args.horizon} days)")
    print("Question: can we PREDICT the next phase out-of-sample?")
    print("=" * 72)

    for path in csvs:
        name = os.path.splitext(os.path.basename(path))[0]
        df = data.load_csv(path)
        ann = phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)
        study = transitions.study_asset(ann, horizon=args.horizon)

        print(f"\n[{name}]  (out-of-sample AUC; 0.50 = coin-flip)")
        print("-" * 72)
        for ph in PHASES:
            m = study["models"].get(ph)
            hz = study["hazards"][ph]
            # hazard "sweet spot": day-in-phase with the highest hazard
            sweet = hz["hazard"].idxmax() if len(hz) else np.nan
            if m is None:
                print(f"  {ph:12s}  (insufficient data)")
                continue
            all_aucs[ph].append(m["auc"])
            skill = ("PREDICTS" if m["auc"] > 0.60 else
                     "weak" if m["auc"] > 0.55 else "no edge")
            print(f"  {ph:12s} -> {m['next_phase']:12s} "
                  f"AUC={m['auc']:.3f} (base {m['base_rate']:.2f}) [{skill}]  "
                  f"peak-hazard day~{sweet}")
            print(f"       triggers: {top_triggers(m['coefs'])}")

        v = transitions.predictive_verdict(study["models"])
        print(f"  => asset mean AUC = {v['mean_auc']:.3f}")

    # ---- cross-asset verdict ----
    print("\n" + "=" * 72)
    print("CROSS-ASSET PREDICTIVE VERDICT")
    print("=" * 72)
    flat = [a for lst in all_aucs.values() for a in lst if not np.isnan(a)]
    for ph in PHASES:
        vals = [a for a in all_aucs[ph] if not np.isnan(a)]
        if vals:
            print(f"  {ph:12s}  mean AUC {np.mean(vals):.3f}  "
                  f"(n={len(vals)} assets)")
    mean_auc = float(np.mean(flat)) if flat else float("nan")
    print(f"\n  OVERALL mean out-of-sample AUC = {mean_auc:.3f}")
    if mean_auc > 0.60:
        print("  VERDICT: PREDICTIVE ✅  transitions can be forecast — the model")
        print("           earns the right to a trading layer (per §highest principle).")
    elif mean_auc > 0.55:
        print("  VERDICT: WEAK ⚠️  some skill, but hunt for stronger Triggers first.")
    else:
        print("  VERDICT: NOT PREDICTIVE YET ❌  per the highest principle, do NOT")
        print("           design trading rules — keep researching Transitions/Triggers.")
    print("\nAUC key: 0.50 coin-flip · 0.55 weak · 0.60 usable · 0.65+ strong")
    print("Coefficients are on standardised features; sign shows direction of effect.")


if __name__ == "__main__":
    main()
