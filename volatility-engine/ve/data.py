"""VE data layer.

Responsibilities:
  * define the canonical daily OHLCV schema VE expects,
  * load that schema from CSV,
  * generate synthetic sample data with *known* volatility cycles so the whole
    pipeline is runnable offline and the engine can be validated against ground
    truth (does it recover the cycle we planted?).

VE never needs price *direction* — but it does need OHLCV to derive True Range,
daily range, etc. The schema mirrors section 8 of the research design.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Raw columns VE reads from a data source. Everything else (ATR, HV, phases…)
# is *derived* by the feature/phase layers, never stored in raw data.
RAW_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
# Turnover is optional (section 8) — filled if the source provides it.
OPTIONAL_COLUMNS = ["Turnover"]


def load_csv(path: str) -> pd.DataFrame:
    """Load a daily OHLCV CSV into VE's canonical frame.

    Expected: a 'Date' column (parseable) plus the RAW_COLUMNS. Column names
    are matched case-insensitively so exports from different sources just work.
    """
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}

    if "date" not in lower:
        raise ValueError(f"{path}: no 'Date' column found (got {list(df.columns)})")

    rename = {}
    for want in RAW_COLUMNS + OPTIONAL_COLUMNS + ["Date"]:
        if want.lower() in lower:
            rename[lower[want.lower()]] = want
    df = df.rename(columns=rename)

    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").set_index("Date")
    keep = [c for c in RAW_COLUMNS + OPTIONAL_COLUMNS if c in df.columns]
    return df[keep].astype(float)


def generate_sample(
    name: str,
    n_days: int = 1500,
    cycle_len: int = 120,
    base_vol: float = 0.012,
    vol_amp: float = 0.9,
    seed: int = 0,
    mean_reversion: float = 0.035,
) -> pd.DataFrame:
    """Generate synthetic daily OHLCV with an embedded volatility cycle.

    The *volatility* (not the price direction) follows a mean-reverting
    oscillation of period ``cycle_len`` days plus AR(1) noise — this is the
    structure VE is meant to detect.

    On top of that, price carries a *mild* mean-reversion toward a slow anchor
    (strength ``mean_reversion``). This models VE's §6 hypothesis directly —
    "市場偏離平衡 → 回歸" — so the Build/Exit trading layer has real imbalance to
    act on. Set ``mean_reversion=0`` for a pure direction-neutral random walk
    (volatility cycle only, no tradable edge). Either way the shocks are
    symmetric, so long and short remain interchangeable.

    Returns a frame with columns Open/High/Low/Close/Volume/Turnover and a
    hidden '_true_vol' column (ground-truth latent volatility the engine never
    reads).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_days)

    # Latent volatility: base level modulated by a sinusoidal cycle, then pushed
    # through a mean-reverting (AR(1)) noise so it is stochastic, not a clean
    # sine — real markets never repeat exactly.
    cycle = 1.0 + vol_amp * np.sin(2 * np.pi * t / cycle_len)
    ar = np.zeros(n_days)
    for i in range(1, n_days):
        ar[i] = 0.92 * ar[i - 1] + rng.normal(0, 0.25)
    true_vol = base_vol * np.clip(cycle * np.exp(ar), 0.15, None)

    # Symmetric volatility shocks + a weak pull back toward a slow anchor.
    shocks = rng.normal(0.0, 1.0, n_days) * true_vol
    logp = np.zeros(n_days)
    anchor = 0.0
    for i in range(1, n_days):
        anchor = 0.98 * anchor + 0.02 * logp[i - 1]          # slow-moving fair value
        pull = -mean_reversion * (logp[i - 1] - anchor)      # imbalance -> reversion
        logp[i] = logp[i - 1] + pull + shocks[i]
    close = 100.0 * np.exp(logp)

    # Build a plausible OHLC around each close. Intraday range scales with vol.
    open_ = np.empty(n_days)
    open_[0] = 100.0
    open_[1:] = close[:-1] * (1 + rng.normal(0, 0.1, n_days - 1) * true_vol[1:])
    intraday = true_vol * rng.uniform(0.8, 2.2, n_days)
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 1, n_days)) * intraday)
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 1, n_days)) * intraday)

    # Volume/turnover loosely rise with volatility (busy markets are volatile).
    volume = (1e6 * (1 + 3 * (true_vol / base_vol - 1)) *
              rng.uniform(0.7, 1.3, n_days)).clip(1e4)
    turnover = volume * close

    dates = pd.bdate_range("2018-01-01", periods=n_days)
    df = pd.DataFrame(
        {
            "Open": open_, "High": high, "Low": low, "Close": close,
            "Volume": volume, "Turnover": turnover, "_true_vol": true_vol,
        },
        index=pd.Index(dates, name="Date"),
    )
    df.attrs["name"] = name
    df.attrs["planted_cycle_len"] = cycle_len
    return df
