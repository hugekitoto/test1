"""Tests for the DCA-signal engine. No network needed."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dca import data, signals, engine


def _pair():
    return data.generate_pair(n_days=1200, seed=1)


def test_no_lookahead_execution():
    # a signal at close of t must execute at OPEN of t+1, never same day
    sig, tgt = _pair()
    common = sig.index.intersection(tgt.index)
    s = signals.black_k(sig.loc[common, "Close"])
    desired = engine.desired_from_signal(tgt.loc[common], s, buy_size=5000)
    fire = s.reindex(common).fillna(False).astype(bool)
    # desired on day i should equal signal on day i-1
    d = desired.to_numpy()
    f = fire.to_numpy()
    assert (d[1:] > 0).tolist() == f[:-1].tolist()
    assert d[0] == 0  # nothing to act on before the first bar


def test_budget_never_overspent_and_carryover():
    sig, tgt = _pair()
    res = engine.run_all(sig, tgt, monthly_budget=50000, buy_size=5000)
    for name, r in res.items():
        m = r.metrics
        # cash pool (idle) must stay non-negative throughout
        assert (r.idle >= -1e-6).all(), name
        # can never invest more than has been contributed
        assert m["total_invested"] <= m["total_contributed"] + 1e-6, name


def test_avg_cost_identity():
    sig, tgt = _pair()
    r = engine.run_all(sig, tgt)["C_0050_blackK"]
    got = r.metrics["avg_cost"]
    exp = r.buys["amount"].sum() / r.buys["shares"].sum()
    assert abs(got - exp) < 1e-6


def test_rare_signal_leaves_idle_cash():
    # requiring 3 consecutive down days fires rarely -> more idle cash than blackK
    sig, tgt = _pair()
    res = engine.run_all(sig, tgt)
    assert res["G3_0050_down3"].metrics["avg_idle_cash"] > \
           res["C_0050_blackK"].metrics["avg_idle_cash"]


def test_lump_invests_full_budget():
    sig, tgt = _pair()
    r = engine.run_all(sig, tgt)["A_monthly_lump"]
    m = r.metrics
    # lump deploys essentially everything -> tiny idle cash on average
    assert m["avg_idle_cash"] < 50000
    assert m["irr_annual"] == m["irr_annual"]  # not NaN


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} tests passed")
