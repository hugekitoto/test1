"""Volatility Engine (VE) — central configuration.

All tunable research parameters live here so experiments stay reproducible
and every module reads the *same* definitions. Nothing here looks at price
direction: VE studies volatility itself (see research design v0.1).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class VEConfig:
    # --- volatility measurement ---
    hv_window: int = 20            # rolling window for historical volatility (trading days)
    atr_window: int = 14           # Wilder ATR window
    trading_days: int = 252        # annualisation factor for HV

    # --- volatility "water level" (percentile) ---
    percentile_window: int = 252   # window used to rank current HV -> percentile [0,1]
    high_level: float = 0.55       # HV percentile >= this  -> "high" water level
    low_level: float = 0.45        # HV percentile <  this  -> "low" water level
    #   the gap between low_level and high_level is a neutral band that damps
    #   whipsaw; a bar inside the band keeps the previous water level (hysteresis).

    # --- volatility "momentum" (rate of change of HV) ---
    mom_fast: int = 5              # fast EMA of HV
    mom_slow: int = 20             # slow EMA of HV
    #   momentum sign = sign(EMA_fast(HV) - EMA_slow(HV)); >0 rising, <=0 falling.

    # --- distance-from-extreme lookback ---
    extreme_window: int = 60       # window for distance from recent high / low

    # --- phase smoothing ---
    min_phase_len: int = 3         # collapse phase runs shorter than this into their
    #   neighbour to avoid single-bar flicker being counted as a real phase.

    # --- assets studied (used by the sample generator / research runner) ---
    assets: List[str] = field(default_factory=lambda: [
        "ETF_0050", "AI_STOCK", "SEMICONDUCTOR", "HIGH_DIVIDEND",
    ])


DEFAULT = VEConfig()

# The four volatility phases. Order is the *natural cycle* order.
PHASES = ["Compression", "Expansion", "Exhaustion", "Recovery"]

# Canonical (healthy) cycle transitions. Used only for reference / reporting,
# never to force the classification.
CANONICAL_CYCLE = {
    "Compression": "Expansion",
    "Expansion": "Exhaustion",
    "Exhaustion": "Recovery",
    "Recovery": "Compression",
}
