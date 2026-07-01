#!/usr/bin/env python3
"""Answer the headline VE question for one asset:
"Which volatility phase is it in right now?" (research design section 10).

Usage:
    python scripts/current_phase.py data/sample/ETF_0050.csv
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data, features, phases  # noqa: E402
from ve.config import DEFAULT, CANONICAL_CYCLE  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="OHLCV CSV file")
    args = ap.parse_args()

    df = data.load_csv(args.csv)
    ann = phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)
    row = ann.dropna(subset=["PhaseSmooth"]).iloc[-1]

    phase = row["PhaseSmooth"]
    name = os.path.splitext(os.path.basename(args.csv))[0]
    print(f"Asset            : {name}")
    print(f"As of            : {row.name.date()}")
    print(f"Volatility phase : {phase}")
    print(f"Days in phase    : {int(row['PhaseDuration'])}")
    print(f"HV percentile    : {row['HV_pct']*100:.0f}%  (water level: {row['WaterLevel']})")
    print(f"Vol momentum     : {'rising' if row['VolMomSign'] > 0 else 'falling'}")
    print(f"Typical next     : {CANONICAL_CYCLE.get(phase, '?')}  (canonical cycle)")
    print()
    print("Reminder: this is a Phase-1 *position* readout, not a trade signal. "
          "Build/Exit zones come in Phase 3.")


if __name__ == "__main__":
    main()
