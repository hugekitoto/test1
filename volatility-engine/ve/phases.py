"""VE phase layer — classify each day into a volatility phase.

Phase = f(water level, momentum), both derived from volatility only:

    water level (HV percentile)  x  momentum (HV rising / falling)

        level \ momentum   rising        falling
        low                Expansion     Compression
        high               Exhaustion    Recovery

Natural cycle order: Compression -> Expansion -> Exhaustion -> Recovery -> ...
This is fully direction-neutral (research design section 6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import VEConfig, DEFAULT


def _water_level_with_hysteresis(pct: pd.Series, cfg: VEConfig) -> pd.Series:
    """Map HV percentile -> 'high'/'low' with a neutral band (hysteresis).

    Inside [low_level, high_level) the level is ambiguous, so we carry the
    previous decision forward. This stops the classifier flickering when HV
    hovers near the median.
    """
    level = pd.Series(index=pct.index, dtype=object)
    state = "low"
    for i, p in enumerate(pct.to_numpy()):
        if np.isnan(p):
            level.iloc[i] = np.nan
            continue
        if p >= cfg.high_level:
            state = "high"
        elif p < cfg.low_level:
            state = "low"
        # else: keep previous state (neutral band)
        level.iloc[i] = state
    return level


def _raw_phase(level: str, mom_sign: int) -> str:
    if level == "high":
        return "Exhaustion" if mom_sign > 0 else "Recovery"
    return "Expansion" if mom_sign > 0 else "Compression"


def _despeckle(phases: pd.Series, min_len: int) -> pd.Series:
    """Merge phase runs shorter than min_len into the preceding run.

    A 1-2 bar phase is noise, not a real regime; collapsing it makes cycle
    statistics meaningful without changing the big structure.
    """
    result = phases.copy()
    vals = result.to_numpy(dtype=object).copy()
    # find run boundaries
    i = 0
    n = len(vals)
    prev_valid = None
    while i < n:
        if vals[i] is None or (isinstance(vals[i], float) and np.isnan(vals[i])):
            i += 1
            continue
        j = i
        while j + 1 < n and vals[j + 1] == vals[i]:
            j += 1
        run_len = j - i + 1
        if run_len < min_len and prev_valid is not None:
            vals[i:j + 1] = prev_valid
        else:
            prev_valid = vals[i]
        i = j + 1
    return pd.Series(vals, index=phases.index, dtype=object)


def classify_phases(feat: pd.DataFrame, cfg: VEConfig = DEFAULT) -> pd.DataFrame:
    """Attach phase columns to a features frame.

    Added columns:
      WaterLevel (high/low), Phase (raw), PhaseSmooth (despeckled),
      PhaseDuration (# consecutive days in current PhaseSmooth run),
      DaysSinceCompression (days since the last Compression run started),
      NewCycle (True on the bar a fresh Compression->... cycle begins).
    """
    out = feat.copy()
    out["WaterLevel"] = _water_level_with_hysteresis(out["HV_pct"], cfg)

    raw = [
        _raw_phase(lv, ms) if isinstance(lv, str) else np.nan
        for lv, ms in zip(out["WaterLevel"], out["VolMomSign"])
    ]
    out["Phase"] = pd.Series(raw, index=out.index, dtype=object)
    out["PhaseSmooth"] = _despeckle(out["Phase"], cfg.min_phase_len)

    # PhaseDuration: length of the current consecutive run so far.
    ps = out["PhaseSmooth"]
    dur = np.zeros(len(ps), dtype=float)
    days_since_comp = np.full(len(ps), np.nan)
    new_cycle = np.zeros(len(ps), dtype=bool)
    run = 0
    last_comp_start = None
    prev = None
    for i, val in enumerate(ps.to_numpy(dtype=object)):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            dur[i] = np.nan
            prev = None
            run = 0
            continue
        if val == prev:
            run += 1
        else:
            run = 1
            if val == "Compression":
                # a new compression run starts a new cycle
                new_cycle[i] = last_comp_start is not None
                last_comp_start = i
        dur[i] = run
        days_since_comp[i] = (i - last_comp_start) if last_comp_start is not None else np.nan
        prev = val

    out["PhaseDuration"] = dur
    out["DaysSinceCompression"] = days_since_comp
    out["NewCycle"] = new_cycle
    return out
