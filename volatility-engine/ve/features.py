"""VE feature layer — volatility measurement.

Every column produced here is a property of *volatility*, never of price
direction. These are the raw materials for phase classification and cycle
analysis (research design sections 8 & the "優先研究" list).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import VEConfig, DEFAULT


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder's True Range = max(H-L, |H-Cprev|, |L-Cprev|)."""
    prev_close = df["Close"].shift(1)
    hl = df["High"] - df["Low"]
    hc = (df["High"] - prev_close).abs()
    lc = (df["Low"] - prev_close).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def atr(df: pd.DataFrame, window: int) -> pd.Series:
    """Average True Range via Wilder smoothing (EMA with alpha = 1/window)."""
    tr = true_range(df)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def historical_volatility(close: pd.Series, window: int, trading_days: int) -> pd.Series:
    """Annualised historical volatility = std(log returns) * sqrt(trading_days)."""
    logret = np.log(close / close.shift(1))
    return logret.rolling(window).std() * np.sqrt(trading_days)


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """Percentile rank of the *current* value within its trailing window, in [0,1].

    1.0 = current value is the highest in the window, 0.0 = the lowest.
    """
    return series.rolling(window, min_periods=window // 2).rank(pct=True)


def compute_features(df: pd.DataFrame, cfg: VEConfig = DEFAULT) -> pd.DataFrame:
    """Return a new frame with all VE volatility features attached.

    Added columns:
      TrueRange, ATR, DailyRange, LogRet, HV, HV_pct (percentile),
      VolMomentum (EMA_fast(HV) - EMA_slow(HV)), VolMomSign (+1/-1),
      DistFromHigh, DistFromLow  (fraction below recent high / above recent low).
    """
    out = df.copy()

    out["TrueRange"] = true_range(df)
    out["ATR"] = atr(df, cfg.atr_window)
    # Daily range as a fraction of price -> comparable across assets/price levels.
    out["DailyRange"] = (df["High"] - df["Low"]) / df["Close"]

    out["LogRet"] = np.log(df["Close"] / df["Close"].shift(1))
    out["HV"] = historical_volatility(df["Close"], cfg.hv_window, cfg.trading_days)
    out["HV_pct"] = rolling_percentile(out["HV"], cfg.percentile_window)

    # Volatility momentum: is HV rising or falling? (rate of change, not price).
    ema_fast = out["HV"].ewm(span=cfg.mom_fast, adjust=False).mean()
    ema_slow = out["HV"].ewm(span=cfg.mom_slow, adjust=False).mean()
    out["VolMomentum"] = ema_fast - ema_slow
    out["VolMomSign"] = np.where(out["VolMomentum"] > 0, 1, -1)

    # Distance from recent extremes — direction-neutral positioning context.
    roll_high = df["Close"].rolling(cfg.extreme_window, min_periods=1).max()
    roll_low = df["Close"].rolling(cfg.extreme_window, min_periods=1).min()
    out["DistFromHigh"] = (roll_high - df["Close"]) / roll_high
    out["DistFromLow"] = (df["Close"] - roll_low) / roll_low

    return out
