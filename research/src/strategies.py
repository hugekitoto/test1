"""
Strategy definitions.

Every strategy is expressed as a **buy-order schedule**: a ``pandas.Series`` of
NTD amounts indexed by the trading date on which the order executes *at the
open*. The backtest engine then applies the shared budget / cash-pool rules
(see ``engine.py``) uniformly to every strategy, so that the ONLY thing that
differs between the signal strategies is the signal itself.

Two families:

1. **Signal strategies** (C/G1, D/G4, E, G2, G3, G5, G6, G7).
   A boolean signal is evaluated using information available *at the close* of
   day ``t``; the resulting 5,000 NTD order executes at the OPEN of day
   ``t+1`` (the next trading day). Shifting the signal forward by one trading
   day is what prevents a look-ahead (future) function.

2. **Cadence benchmarks** (A, B).
   A: one 50,000 NTD order on the first trading day of each month.
   B: ten 5,000 NTD orders on evenly spaced trading days each month.

All amounts are *requested*; whether an order actually fills depends on the
cash available in the pool at execution time (that is where Cash Drag and the
monthly budget cap come from, and it is handled centrally in the engine).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PER_BUY = 5_000
MONTHLY_BUDGET = 50_000
MAX_BUYS_PER_MONTH = MONTHLY_BUDGET // PER_BUY  # 10


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _signal_to_orders(signal: pd.Series, index: pd.DatetimeIndex,
                      amount: float = PER_BUY) -> pd.Series:
    """Convert a close-of-day boolean signal into next-open buy orders.

    ``signal[t] == True`` -> place a buy of ``amount`` at the OPEN of the next
    trading day ``t+1``. Signals on the final day are dropped (no next open).
    """
    signal = signal.reindex(index).fillna(False).astype(bool)
    # execution date = the trading day AFTER the signal day
    exec_dates = index[1:]                     # t+1 ... end
    fired = signal.values[:-1]                 # signal on t (for t in 0..n-2)
    orders = pd.Series(0.0, index=index)
    orders.loc[exec_dates[fired]] = amount
    return orders


def _first_trading_day_each_month(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, index.month]).first().values)


def _evenly_spaced_days_each_month(index: pd.DatetimeIndex, n: int) -> pd.DatetimeIndex:
    """Pick up to ``n`` evenly spaced trading days within each calendar month."""
    picks = []
    df = pd.DataFrame({"d": index}, index=index)
    for _, grp in df.groupby([index.year, index.month]):
        days = grp["d"].values
        k = min(n, len(days))
        # evenly spaced positions across the month's trading days
        pos = np.linspace(0, len(days) - 1, k).round().astype(int)
        pos = np.unique(pos)
        picks.extend(days[pos])
    return pd.DatetimeIndex(picks)


# --------------------------------------------------------------------------- #
# signal builders  (each returns a close-of-day boolean Series)
# --------------------------------------------------------------------------- #
def sig_black_k(px: pd.DataFrame) -> pd.Series:
    """Black K: today's close < yesterday's close."""
    return px["close"] < px["prev_close"]


def sig_down_pct(px: pd.DataFrame, pct: float = 0.01) -> pd.Series:
    """Down at least ``pct`` (e.g. 0.01 = 1%) vs previous close."""
    ret = px["close"] / px["prev_close"] - 1.0
    return ret <= -abs(pct)


def sig_consecutive_down(px: pd.DataFrame, n: int) -> pd.Series:
    """Down for ``n`` consecutive trading days (n black Ks in a row)."""
    down = px["close"] < px["prev_close"]
    streak = down.copy()
    for k in range(1, n):
        streak &= down.shift(k).fillna(False)
    return streak


def sig_below_ma(px: pd.DataFrame, window: int = 20) -> pd.Series:
    """Close below its own ``window``-day simple moving average."""
    ma = px["close"].rolling(window).mean()
    return px["close"] < ma


def sig_freshness(px: pd.DataFrame, window: int = 60, threshold: float = 0.05) -> pd.Series:
    """2330 'freshness': pulled back at least ``threshold`` from a recent high.

    Freshness is operationalised as the drawdown from the trailing
    ``window``-day rolling maximum close::

        pullback = (rolling_max(close, window) - close) / rolling_max(close, window)

    ``freshness signal = pullback >= threshold``.  Intuition: only buy when the
    target is 'fresh' off a local top rather than at a stretched high. (This is
    our explicit operationalisation of the term used in the research design.)
    """
    roll_max = px["close"].rolling(window, min_periods=1).max()
    pullback = (roll_max - px["close"]) / roll_max
    return pullback >= threshold


# --------------------------------------------------------------------------- #
# strategy registry -> order schedules
# --------------------------------------------------------------------------- #
def build_orders(name: str, tsmc: pd.DataFrame, etf: pd.DataFrame,
                 params: dict | None = None) -> pd.Series:
    """Return the buy-order schedule (amount indexed by execution date)."""
    params = params or {}
    index = tsmc.index  # execution calendar = 2330's trading days

    if name == "A_monthly_lump":
        days = _first_trading_day_each_month(index)
        return pd.Series(MONTHLY_BUDGET, index=index).where(
            index.isin(days), 0.0)

    if name == "B_spread_10":
        days = _evenly_spaced_days_each_month(index, MAX_BUYS_PER_MONTH)
        return pd.Series(PER_BUY, index=index).where(index.isin(days), 0.0)

    if name == "C_0050_blackk":            # == G1, the core strategy
        return _signal_to_orders(sig_black_k(etf), index)

    if name == "D_0050_down1pct":          # == G4
        pct = params.get("pct", 0.01)
        return _signal_to_orders(sig_down_pct(etf, pct), index)

    if name == "E_2330_blackk":
        return _signal_to_orders(sig_black_k(tsmc), index)

    if name == "G2_0050_down2":
        return _signal_to_orders(sig_consecutive_down(etf, 2), index)

    if name == "G3_0050_down3":
        return _signal_to_orders(sig_consecutive_down(etf, 3), index)

    if name == "G5_0050_below_ma20":
        w = params.get("window", 20)
        return _signal_to_orders(sig_below_ma(etf, w), index)

    if name == "G6_0050_and_2330_blackk":
        sig = sig_black_k(etf) & sig_black_k(tsmc)
        return _signal_to_orders(sig, index)

    if name == "G7_0050_blackk_2330_fresh":
        w = params.get("window", 60)
        thr = params.get("threshold", 0.05)
        sig = sig_black_k(etf) & sig_freshness(tsmc, w, thr)
        return _signal_to_orders(sig, index)

    raise ValueError(f"unknown strategy: {name}")


STRATEGIES = [
    ("A_monthly_lump", "Benchmark A: 每月一次投入 50,000"),
    ("B_spread_10", "Benchmark B: 每月平均分 10 次 (不看漲跌)"),
    ("C_0050_blackk", "Benchmark C / G1: 0050 黑K -> 隔日開盤買 2330"),
    ("D_0050_down1pct", "Benchmark D / G4: 0050 下跌 >= 1%"),
    ("E_2330_blackk", "Benchmark E: 2330 自己黑K"),
    ("G2_0050_down2", "G2: 0050 連跌 2 天"),
    ("G3_0050_down3", "G3: 0050 連跌 3 天"),
    ("G5_0050_below_ma20", "G5: 0050 跌破 MA20"),
    ("G6_0050_and_2330_blackk", "G6: 0050 黑K 且 2330 黑K"),
    ("G7_0050_blackk_2330_fresh", "G7: 0050 黑K + 2330 回檔(freshness>=5%)"),
]
