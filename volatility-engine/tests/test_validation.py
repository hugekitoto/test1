"""Tests for the v0.2 six-layer validation framework. No network needed."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data, features, phases, validation
from ve.config import DEFAULT, PHASES


def _ann(cycle_len=100, seed=5, n=1800):
    df = data.generate_sample("T", n_days=n, cycle_len=cycle_len, seed=seed)
    return phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)


def _assets():
    return {f"A{i}": _ann(cycle_len=90 + 15 * i, seed=i + 1) for i in range(3)}


def test_cross_time_returns_windows_with_valid_auc():
    rows = validation.cross_time(_ann(n=2600), horizon=5)
    assert len(rows) >= 1
    for r in rows:
        assert np.isnan(r["auc"]) or 0.0 <= r["auc"] <= 1.0


def test_cross_asset_matrix_shape_and_bounds():
    mat = validation.cross_asset(_assets(), horizon=5)
    assert mat.shape[0] == mat.shape[1] == 3
    vals = mat.to_numpy().astype(float)
    vals = vals[~np.isnan(vals)]
    assert ((vals >= 0) & (vals <= 1)).all()


def test_regime_auc_has_all_key():
    r = validation.regime_auc(_ann(), horizon=5)
    assert "ALL" in r


def test_information_gain_keys_and_full_ge_reasonable():
    ig = validation.information_gain(_ann(cycle_len=110), horizon=5)
    assert {"baseline_auc", "full_auc", "gain", "loo"} <= set(ig)
    assert set(ig["loo"]) == set(validation.FEATURES)


def test_oracle_move_bounds_directional():
    # invariant: directional (long-only) capture can never exceed the perfect
    # |move| bound; and there is a real move to trade.
    o = validation.oracle_test(_ann(cycle_len=100))
    for ph in PHASES:
        if ph in o.index and o.loc[ph].get("n", 0):
            assert o.loc[ph]["avg_abs_move"] > 0
            assert abs(o.loc[ph]["long_only"]) <= o.loc[ph]["directional_best"] + 1e-9


def test_liquidity_test_keys():
    lq = validation.liquidity_test(_ann(), horizon=5)
    assert {"best_lag", "best_xcorr", "auc_price_vol",
            "auc_with_liquidity", "liquidity_gain"} <= set(lq)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed")
