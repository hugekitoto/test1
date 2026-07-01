"""VE Phase 2 — formalise each volatility phase.

Once Phase 1 shows a cycle exists, Phase 2 characterises *what each phase means*
statistically, per asset and per asset class:

  * forward realised volatility  (does Compression really precede an expansion?)
  * forward move magnitude       (direction-neutral: |cumulative return|)
  * phase duration distribution
  * transition confidence        (how reliably the phase hands off canonically)

It also tests time-consistency (§11.3): are these relationships stable across
Bull / Bear / Range regimes?
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PHASES, CANONICAL_CYCLE, VEConfig, DEFAULT
from .cycles import transition_matrix


def _forward_stats(ann: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Add forward-looking columns (evaluated over the next `horizon` days)."""
    logret = ann["LogRet"]
    # realised vol over the *next* horizon days, annualised
    fwd_vol = logret.rolling(horizon).std().shift(-horizon) * np.sqrt(DEFAULT.trading_days)
    # magnitude of the cumulative move over the next horizon days
    fwd_move = logret.rolling(horizon).sum().shift(-horizon).abs()
    out = ann.copy()
    out["FwdVol"] = fwd_vol
    out["FwdMove"] = fwd_move
    # vol change: how much realised vol rises/falls after this bar vs current HV
    out["FwdVolChange"] = fwd_vol - ann["HV"]
    return out


def phase_profile(ann: pd.DataFrame, horizon: int = 10,
                  cfg: VEConfig = DEFAULT) -> pd.DataFrame:
    """Per-phase forward statistics for one asset.

    Returns a DataFrame indexed by phase with columns:
      n, avg_duration, fwd_vol, fwd_vol_change, fwd_move, canonical_follow.
    """
    enr = _forward_stats(ann, horizon)
    tm = transition_matrix(ann["PhaseSmooth"])

    rows = []
    for ph in PHASES:
        mask = enr["PhaseSmooth"] == ph
        sub = enr[mask]
        follow = (tm.loc[ph, CANONICAL_CYCLE[ph]]
                  if ph in tm.index else np.nan)
        rows.append({
            "phase": ph,
            "n_days": int(mask.sum()),
            "avg_duration": float(sub["PhaseDuration"].mean()) if len(sub) else np.nan,
            "fwd_vol": float(sub["FwdVol"].mean()),
            "fwd_vol_change": float(sub["FwdVolChange"].mean()),
            "fwd_move": float(sub["FwdMove"].mean()),
            "canonical_follow": float(follow),
        })
    return pd.DataFrame(rows).set_index("phase")


def time_consistency(ann: pd.DataFrame, regime: pd.Series) -> pd.DataFrame:
    """Canonical-follow rate for each phase, computed *within* each regime.

    Stable numbers across Bull / Bear / Range => the cycle is regime-independent
    (success criterion §11.3). Returns a DataFrame: rows=phase, cols=regime.
    """
    df = pd.DataFrame(index=PHASES)
    for reg in ["Bull", "Bear", "Range"]:
        mask = regime == reg
        if mask.sum() < 30:
            df[reg] = np.nan
            continue
        tm = transition_matrix(ann["PhaseSmooth"][mask])
        df[reg] = [tm.loc[p, CANONICAL_CYCLE[p]] if p in tm.index else np.nan
                   for p in PHASES]
    return df


def profile_validates(profile: pd.DataFrame) -> dict:
    """Check the core Phase-2 predictions hold in a profile.

    * Compression should have the LOWEST forward vol but POSITIVE fwd_vol_change
      (quiet now, expanding next).
    * Exhaustion should have the HIGHEST forward vol but NEGATIVE fwd_vol_change
      (loud now, cooling next).
    """
    fv = profile["fwd_vol"]
    fvc = profile["fwd_vol_change"]
    checks = {
        "compression_is_quietest": fv.idxmin() == "Compression",
        "compression_expands_next": fvc.get("Compression", np.nan) > 0,
        "exhaustion_is_loudest": fv.idxmax() == "Exhaustion",
        "exhaustion_cools_next": fvc.get("Exhaustion", np.nan) < 0,
    }
    checks["passed"] = int(sum(bool(v) for v in checks.values()))
    return checks
