"""VE Phase 3 — Build Zone / Exit Zone, derived from the volatility cycle.

Key principle (design §7, §10): zones come from *where you are in the cycle*,
not from hand-set prices.

  * Build Zone  = Compression. Volatility is low and coiling, about to expand —
    the cheap place to build a position (tight stops, low noise).
  * Exit Zone   = Exhaustion. Volatility has climaxed and is spent — take the
    move off. (We also flatten once the cycle rolls into Recovery.)

Direction is decided by *imbalance* (design §6), not by a price forecast:
  position-in-range near the LOW  => downward imbalance => LONG bias
  position-in-range near the HIGH => upward imbalance   => SHORT bias
This keeps the research layer symmetric; the trading layer chooses whether to
act on shorts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import VEConfig, DEFAULT


def derive_zones(ann: pd.DataFrame, cfg: VEConfig = DEFAULT,
                 imbalance_band: float = 0.15) -> pd.DataFrame:
    """Add zone + directional-bias columns to a phase-annotated frame.

    Added columns:
      PosInRange   : where Close sits in the recent extreme window, in [0,1].
      Imbalance    : signed, +1..-1 ; >0 = stretched up, <0 = stretched down.
      BuildDir     : +1 long / -1 short / 0 none  (only meaningful in Build Zone).
      InBuildZone  : bool (Compression).
      InExitZone   : bool (Exhaustion).
    """
    out = ann.copy()
    win = cfg.extreme_window
    roll_high = out["High"].rolling(win, min_periods=1).max()
    roll_low = out["Low"].rolling(win, min_periods=1).min()
    span = (roll_high - roll_low).replace(0, np.nan)
    pos = ((out["Close"] - roll_low) / span).clip(0, 1)
    out["PosInRange"] = pos

    # Imbalance centred on 0: +1 = pinned to range high, -1 = pinned to range low.
    imbalance = 2 * pos - 1
    out["Imbalance"] = imbalance

    # Direction from imbalance, with a neutral dead-band so we don't trade noise.
    # Stretched DOWN (imbalance < -band) -> long ; stretched UP (> band) -> short.
    build_dir = np.zeros(len(out), dtype=float)
    build_dir[imbalance < -imbalance_band] = 1.0
    build_dir[imbalance > imbalance_band] = -1.0
    out["BuildDir"] = build_dir

    out["InBuildZone"] = out["PhaseSmooth"] == "Compression"
    out["InExitZone"] = out["PhaseSmooth"] == "Exhaustion"
    return out
