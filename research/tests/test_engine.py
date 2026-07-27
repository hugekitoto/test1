"""
Mechanical correctness tests for the engine (run: python tests/test_engine.py).

These use tiny hand-built data so the expected numbers can be checked by hand.
They verify the two properties that make the study valid:
  1. No look-ahead: a signal at close of day t executes at the OPEN of day t+1.
  2. Budget carryover: unused monthly budget accumulates with no cap.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import engine
from strategies import build_orders, _signal_to_orders


def _px(dates, opens, closes):
    df = pd.DataFrame({"open": opens, "high": closes, "low": opens,
                       "close": closes}, index=pd.DatetimeIndex(dates))
    df["prev_close"] = df["close"].shift(1)
    return df


def test_no_lookahead():
    dates = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    # 0050: down on day 2 (close 99 < 100) -> buy must land on day 3's OPEN
    etf = _px(dates, [100, 100, 100, 100], [100, 99, 101, 101])
    tsmc = _px(dates, [200, 210, 220, 230], [205, 215, 225, 235])
    orders = build_orders("C_0050_blackk", tsmc, etf)
    # signal on 01-03 -> order on 01-06 (the next trading day), amount 5000
    assert orders.loc["2020-01-06"] == 5000, orders.to_dict()
    assert orders.drop(pd.Timestamp("2020-01-06")).sum() == 0, orders.to_dict()

    sim = engine.run(tsmc, orders)
    buys = sim["buys"]
    assert len(buys) == 1
    # executed at day-3 OPEN = 220 (NOT day-2's price)
    assert abs(buys.iloc[0]["price"] - 220) < 1e-9, buys
    print("PASS test_no_lookahead")


def test_budget_carryover():
    # Two months. Month 1: exactly one buy (5000) -> 45000 carries over.
    # Month 2: budget available should be 45000 + 50000 = 95000.
    m1 = pd.bdate_range("2020-01-01", "2020-01-31")
    m2 = pd.bdate_range("2020-02-01", "2020-02-28")
    dates = m1.append(m2)
    opens = [10.0] * len(dates)
    closes = [10.0] * len(dates)
    tsmc = _px(dates, opens, closes)

    # one order in Jan (5000), then 20 orders of 5000 in Feb (=100000 requested)
    orders = pd.Series(0.0, index=dates)
    orders.iloc[1] = 5000                      # a Jan buy
    for i in range(len(m1), len(m1) + 20):     # 20 Feb buys requested
        if i < len(dates):
            orders.iloc[i] = 5000

    sim = engine.run(tsmc, orders)
    ledger = sim["ledger"]
    # Jan contributes 50000, spends 5000 -> 45000 idle entering Feb.
    # Feb contributes +50000 -> 95000 available -> at most 19 buys of 5000 fill
    # (95000/5000 = 19). Total filled = 1 (Jan) + 19 (Feb) = 20 buys = 100000.
    total_filled = sim["buys"]["amount"].sum()
    assert total_filled == 100000, total_filled
    # end cash = 100000 contributed - 100000 deployed = 0
    assert abs(ledger["cash"].iloc[-1]) < 1e-6, ledger["cash"].iloc[-1]
    print("PASS test_budget_carryover")


def test_all_strategies_run():
    from generate_synthetic import generate
    etf_raw, tsmc_raw = generate(start="2019-01-01", end="2021-12-31")
    etf = etf_raw.set_index(pd.DatetimeIndex(etf_raw["date"]))[["open", "high", "low", "close"]]
    tsmc = tsmc_raw.set_index(pd.DatetimeIndex(tsmc_raw["date"]))[["open", "high", "low", "close"]]
    etf["prev_close"] = etf["close"].shift(1)
    tsmc["prev_close"] = tsmc["close"].shift(1)
    from strategies import STRATEGIES
    import metrics as mm
    for name, _ in STRATEGIES:
        orders = build_orders(name, tsmc, etf)
        sim = engine.run(tsmc, orders)
        res = mm.compute(sim["ledger"], sim["buys"])
        assert res["Final Assets"] > 0, name
    print("PASS test_all_strategies_run")


if __name__ == "__main__":
    test_no_lookahead()
    test_budget_carryover()
    test_all_strategies_run()
    print("\nAll tests passed.")
