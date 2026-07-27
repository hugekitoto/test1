"""Data layer for the DCA-signal study.

Needs daily Open + Close for two tickers: a *signal* asset (0050) and a *buy
target* (2330). Provides CSV loading, an optional yfinance fetcher (for Colab /
local use — the hosted research env blocks market data), and a synthetic
two-asset generator so the whole study runs offline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def load_csv(path: str) -> pd.DataFrame:
    """Load daily OHLCV with a Date index (case-insensitive column matching)."""
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}
    if "date" not in lower:
        raise ValueError(f"{path}: no 'Date' column (got {list(df.columns)})")
    ren = {lower[c.lower()]: c for c in COLUMNS + ["Date"] if c.lower() in lower}
    df = df.rename(columns=ren)
    for need in ["Open", "Close"]:
        if need not in df.columns:
            raise ValueError(f"{path}: missing required column {need}")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").set_index("Date")
    keep = [c for c in COLUMNS if c in df.columns]
    return df[keep].astype(float)


def fetch_yfinance(ticker: str, start: str = "2015-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch daily OHLCV via yfinance (needs network). Flattens MultiIndex cols."""
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data for {ticker} (blocked in hosted env; use Colab/CSV).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    df = df.loc[:, ~df.columns.duplicated()]
    df.index.name = "Date"
    return df[[c for c in COLUMNS if c in df.columns]].astype(float)


def generate_pair(n_days: int = 2500, seed: int = 0,
                  target_drift: float = 0.00055, signal_drift: float = 0.00030,
                  beta: float = 1.15):
    """Synthetic (signal, target) pair. Target ~ higher drift/vol (like 2330 vs
    0050), correlated through a shared market factor plus idiosyncratic noise.
    Returns (signal_df, target_df) with Open/High/Low/Close/Volume.
    """
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0.0, 0.011, n_days)          # common market factor
    sig_ret = signal_drift + mkt + rng.normal(0, 0.004, n_days)
    tgt_ret = target_drift + beta * mkt + rng.normal(0, 0.010, n_days)

    def _ohlc(rets, p0, vol):
        close = p0 * np.exp(np.cumsum(rets))
        open_ = np.empty(n_days)
        open_[0] = p0
        open_[1:] = close[:-1] * (1 + rng.normal(0, 0.003, n_days - 1))
        hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol, n_days)))
        lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol, n_days)))
        vol_ = rng.uniform(1e6, 3e6, n_days)
        idx = pd.bdate_range("2015-01-01", periods=n_days)
        return pd.DataFrame({"Open": open_, "High": hi, "Low": lo,
                             "Close": close, "Volume": vol_},
                            index=pd.Index(idx, name="Date"))

    return _ohlc(sig_ret, 50.0, 0.006), _ohlc(tgt_ret, 140.0, 0.012)
