#!/usr/bin/env python3
"""VE Phase-1 research runner.

Loads every CSV under a data directory, runs the full pipeline, prints the
Phase-1 report, and writes phase-annotated CSVs to output/.

Usage:
    python scripts/run_research.py                      # uses data/sample
    python scripts/run_research.py --data path/to/csvs  # your own OHLCV CSVs
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd  # noqa: E402

from ve import data, features, phases, cycles, report  # noqa: E402
from ve.config import DEFAULT  # noqa: E402

HERE = os.path.dirname(__file__)


def run_one(path: str):
    df = data.load_csv(path)
    feat = features.compute_features(df, DEFAULT)
    ann = phases.classify_phases(feat, DEFAULT)
    stats = cycles.analyse(ann["PhaseSmooth"])
    return ann, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "sample"),
                    help="directory of OHLCV CSVs")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output"),
                    help="directory for phase-annotated CSVs")
    args = ap.parse_args()

    csvs = sorted(glob.glob(os.path.join(args.data, "*.csv")))
    if not csvs:
        print(f"No CSVs in {args.data}. Run scripts/generate_sample_data.py first.")
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    results = {}
    for path in csvs:
        name = os.path.splitext(os.path.basename(path))[0]
        ann, stats = run_one(path)
        results[name] = stats
        # persist annotated data + a compact current-state line
        ann.to_csv(os.path.join(args.out, f"{name}_annotated.csv"))
        last = ann.dropna(subset=["PhaseSmooth"]).iloc[-1]
        print(f"[{name:14s}] current phase: {last['PhaseSmooth']:12s} "
              f"day {int(last['PhaseDuration'])} of run | "
              f"HV pctl {last['HV_pct']*100:4.0f}%")

    print()
    print(report.answer_research_questions(results))


if __name__ == "__main__":
    main()
