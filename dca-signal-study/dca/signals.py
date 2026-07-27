"""Signal definitions for the DCA study (all computed on daily closes)."""

from __future__ import annotations

import pandas as pd


def black_k(close: pd.Series) -> pd.Series:
    """Down day: today's close < yesterday's close."""
    return close < close.shift(1)


def down_pct(close: pd.Series, pct: float = 0.01) -> pd.Series:
    """Fell by at least `pct` (e.g. 0.01 = -1%)."""
    return close.pct_change() <= -pct


def consecutive_down(close: pd.Series, n: int) -> pd.Series:
    """Down for n consecutive days (today inclusive)."""
    d = (close < close.shift(1)).astype(float)
    return d.rolling(n).sum() == n


def below_ma(close: pd.Series, n: int = 20) -> pd.Series:
    """Close below its n-day moving average."""
    return close < close.rolling(n).mean()
