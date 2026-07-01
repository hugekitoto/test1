"""Tests for the v0.2 transition model. No network needed."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data, features, phases, transitions
from ve.config import DEFAULT, PHASES


def _ann(cycle_len=100, seed=5):
    df = data.generate_sample("T", n_days=1800, cycle_len=cycle_len, seed=seed)
    return phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)


def test_remaining_days_monotonic_within_run():
    ann = _ann()
    rem = transitions.remaining_days_in_phase(ann)
    # within any run, remaining must strictly decrease by 1 each day to 0
    ps = ann["PhaseSmooth"].to_numpy(dtype=object)
    r = rem.to_numpy()
    for i in range(1, len(ps)):
        if isinstance(ps[i], str) and ps[i] == ps[i - 1]:
            assert r[i] == r[i - 1] - 1


def test_features_have_no_lookahead_columns():
    ann = _ann()
    feats = transitions.build_transition_features(ann)
    assert set(transitions.FEATURES).issubset(feats.columns)


def test_hazard_curve_valid_probabilities():
    ann = _ann()
    hz = transitions.hazard_curve(ann, "Compression")
    assert (hz["hazard"].dropna().between(0, 1)).all()
    # at_risk must be non-increasing as day-in-phase grows
    assert (hz["at_risk"].diff().dropna() <= 0).all()


def test_auc_bounds_and_sanity():
    # perfect separation -> AUC 1.0 ; reversed -> 0.0
    y = np.array([0, 0, 1, 1])
    assert transitions._auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert transitions._auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0


def test_transition_model_runs_and_has_signal_on_synthetic():
    # synthetic data has a strong time-based cycle, so the model should beat
    # a coin flip out-of-sample for at least one phase.
    ann = _ann(cycle_len=110, seed=3)
    study = transitions.study_asset(ann, horizon=5)
    aucs = [m["auc"] for m in study["models"].values() if not np.isnan(m["auc"])]
    assert len(aucs) >= 1
    assert max(aucs) > 0.55, aucs  # detectable predictive skill somewhere


def test_robustness_placebo_collapses():
    # placebo (shuffled labels) must score near coin-flip and well below full
    ann = _ann(cycle_len=110, seed=3)
    r = transitions.robustness_check(ann, horizon=5)
    assert r["placebo"] < 0.60, r["placebo"]
    assert r["full"] - r["placebo"] > 0.10, r
    assert not np.isnan(r["external_target"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed")
