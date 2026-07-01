"""Tests for Phase 2 (profile) and Phase 3 (zones, backtest, evaluate).

Run:  python tests/test_phase23.py    (no network needed)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data, features, phases, zones, backtest, profile, regimes
from ve.config import DEFAULT, PHASES


def _pipeline(cycle_len=100, seed=5, mr=0.035):
    df = data.generate_sample("T", n_days=1500, cycle_len=cycle_len,
                              seed=seed, mean_reversion=mr)
    ann = phases.classify_phases(features.compute_features(df, DEFAULT), DEFAULT)
    return df, ann


def test_zones_columns_and_direction():
    _, ann = _pipeline()
    z = zones.derive_zones(ann, DEFAULT)
    for c in ["PosInRange", "Imbalance", "BuildDir", "InBuildZone", "InExitZone"]:
        assert c in z.columns
    assert z["PosInRange"].dropna().between(0, 1).all()
    assert set(np.unique(z["BuildDir"])) <= {-1.0, 0.0, 1.0}
    # build/exit zones must line up with the right phases
    assert (z.loc[z["InBuildZone"], "PhaseSmooth"] == "Compression").all()
    assert (z.loc[z["InExitZone"], "PhaseSmooth"] == "Exhaustion").all()


def test_backtest_runs_and_is_consistent():
    _, ann = _pipeline()
    z = zones.derive_zones(ann, DEFAULT)
    res = backtest.run_backtest(z, DEFAULT, long_short=True)
    m = res["metrics"]
    assert m["n_trades"] >= 1
    assert 0.0 <= m["win_rate"] <= 1.0
    # equity is the compounded strat return
    assert abs(res["equity"].iloc[-1] - (1 + res["strat_ret"]).prod()) < 1e-6


def test_long_only_has_no_short_trades():
    _, ann = _pipeline()
    z = zones.derive_zones(ann, DEFAULT)
    res = backtest.run_backtest(z, DEFAULT, long_short=False)
    if len(res["trades"]):
        assert (res["trades"]["dir"] > 0).all()


def test_no_lookahead_in_positions():
    # position must be flat during the warmup where phase is undefined
    _, ann = _pipeline()
    z = zones.derive_zones(ann, DEFAULT)
    res = backtest.run_backtest(z, DEFAULT)
    warmup = z["PhaseSmooth"].isna()
    assert (res["position"][warmup] == 0).all()


def test_profile_predictions_direction():
    # with a real cycle, compression should expand and exhaustion should cool
    _, ann = _pipeline(cycle_len=110)
    p = profile.phase_profile(ann, horizon=10)
    assert p.loc["Compression", "fwd_vol_change"] > p.loc["Exhaustion", "fwd_vol_change"]


def test_regime_labels_valid():
    df, _ = _pipeline()
    reg = regimes.tag_regime(df["Close"])
    assert set(reg.dropna().unique()) <= {"Bull", "Bear", "Range"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed")
