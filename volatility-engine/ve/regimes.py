"""Market-regime tagging — for validation only.

VE's phase logic never looks at price direction. But to test success criterion
§11.3 (does the volatility cycle hold across bull / bear / range markets?) we
need to *stratify* results by trend regime. This module tags each day as
Bull / Bear / Range using a slow trend filter. It is used ONLY to slice the
phase statistics, never to classify phases.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def tag_regime(close: pd.Series, fast: int = 50, slow: int = 200,
               flat_band: float = 0.03) -> pd.Series:
    """Tag Bull / Bear / Range from the gap between a fast and slow MA.

    * Bull  : fast MA more than +flat_band above slow MA
    * Bear  : fast MA more than -flat_band below slow MA
    * Range : within the flat band
    """
    ma_fast = close.rolling(fast, min_periods=fast // 2).mean()
    ma_slow = close.rolling(slow, min_periods=slow // 2).mean()
    gap = (ma_fast - ma_slow) / ma_slow
    out = pd.Series("Range", index=close.index, dtype=object)
    out[gap > flat_band] = "Bull"
    out[gap < -flat_band] = "Bear"
    out[gap.isna()] = np.nan
    return out
