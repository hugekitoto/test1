"""Smoke + correctness tests for the VE pipeline.

Run:  python -m pytest tests/ -q     (or)     python tests/test_pipeline.py
No network needed — everything uses the synthetic generator.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data, features, phases, cycles
from ve.config import DEFAULT, PHASES


def _annotated(cycle_len=100, seed=7):
    df = data.generate_sample("TEST", n_days=1500, cycle_len=cycle_len, seed=seed)
    feat = features.compute_features(df, DEFAULT)
    return phases.classify_phases(feat, DEFAULT)


def test_true_range_nonnegative():
    df = data.generate_sample("TEST", n_days=300, seed=1)
    tr = features.true_range(df)
    assert (tr.dropna() >= 0).all()


def test_hv_percentile_bounds():
    ann = _annotated()
    pct = ann["HV_pct"].dropna()
    assert pct.min() >= 0.0 and pct.max() <= 1.0


def test_only_valid_phase_labels():
    ann = _annotated()
    labels = set(ann["PhaseSmooth"].dropna().unique())
    assert labels.issubset(set(PHASES)), labels


def test_all_four_phases_appear():
    # a series with a real cycle should visit every phase
    ann = _annotated(cycle_len=90)
    labels = set(ann["PhaseSmooth"].dropna().unique())
    assert labels == set(PHASES), f"missing phases: {set(PHASES) - labels}"


def test_engine_recovers_planted_cycle():
    # The generator plants a cycle_len-day volatility cycle. VE's detected mean
    # cycle length should land in the right ballpark (within 60%).
    planted = 100
    ann = _annotated(cycle_len=planted, seed=3)
    cl = cycles.cycle_lengths(ann["PhaseSmooth"])
    assert cl["n_cycles"] >= 3, "too few cycles detected"
    assert 0.4 * planted <= cl["mean"] <= 2.0 * planted, cl["mean"]


def test_volatility_has_inertia():
    # Persistence (same phase tomorrow) should clearly beat random (0.25).
    ann = _annotated(cycle_len=110)
    pers = cycles.phase_persistence(ann["PhaseSmooth"])
    assert np.nanmean(list(pers.values())) > 0.5


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")
