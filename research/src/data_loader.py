"""
Data loading and alignment for the 0050 -> 2330 timing study.

Expected CSV format (one file per instrument), header row required::

    date,open,high,low,close[,adj_close][,volume]
    2015-01-05,140.0,141.5,139.0,141.0,120.3,12345678

Rules
-----
* ``date`` is parsed as a calendar date (YYYY-MM-DD).
* If an ``adj_close`` column is present it is treated as the dividend/split
  adjusted close, and open/high/low/close are rescaled by the factor
  ``adj_close / close`` so that the whole OHLC bar is on an adjusted basis.
  This matters: without adjustment, an ex-dividend gap-down would register as
  a spurious "black K" signal.
* If ``adj_close`` is absent, the raw ``close`` is used as-is (a warning is the
  caller's responsibility; see data/README.md).

The loader returns a tidy DataFrame indexed by date with columns
``open, high, low, close`` (all adjusted) plus ``prev_close``.
"""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {"date", "open", "high", "low", "close"}


def load_prices(path: str) -> pd.DataFrame:
    """Load a single instrument CSV into an adjusted-OHLC DataFrame."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.sort_values("date").drop_duplicates("date").set_index("date")

    ohlc = ["open", "high", "low", "close"]
    df[ohlc] = df[ohlc].astype(float)

    if "adj_close" in df.columns:
        adj = df["adj_close"].astype(float)
        factor = adj / df["close"]
        for col in ohlc:
            df[col] = df[col] * factor
        df["close"] = adj

    out = df[ohlc].copy()
    out["prev_close"] = out["close"].shift(1)
    return out


def align(a: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Restrict two price frames to their common set of trading dates.

    Both instruments must trade on the same calendar for the signal (from one)
    and the execution (on the other) to line up. We intersect the indices and
    recompute ``prev_close`` on the intersected calendar so that a "black K" is
    measured against the previous *common* trading day.
    """
    common = a.index.intersection(b.index)
    a2 = a.loc[common].copy()
    b2 = b.loc[common].copy()
    a2["prev_close"] = a2["close"].shift(1)
    b2["prev_close"] = b2["close"].shift(1)
    return a2, b2
