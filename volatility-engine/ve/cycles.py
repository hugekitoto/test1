"""VE cycle-analysis layer.

Turns per-day phase labels into the statistics that answer the research
questions (design section 9): does volatility have a life cycle? inertia?
does compression lead to expansion? average cycle length? etc.

All functions take a phase-annotated frame (output of phases.classify_phases)
and return plain dicts / DataFrames so they are easy to aggregate across assets.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .config import PHASES, CANONICAL_CYCLE


def _runs(phase: pd.Series) -> List[dict]:
    """Compress a phase series into runs: [{phase, start, end, length}, ...]."""
    runs = []
    vals = phase.to_numpy(dtype=object)
    idx = phase.index
    i, n = 0, len(vals)
    while i < n:
        v = vals[i]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            i += 1
            continue
        j = i
        while j + 1 < n and vals[j + 1] == v:
            j += 1
        runs.append({"phase": v, "start": idx[i], "end": idx[j], "length": j - i + 1})
        i = j + 1
    return runs


def transition_matrix(phase: pd.Series) -> pd.DataFrame:
    """Run-to-run transition probabilities P(next phase | current phase).

    Built on *runs*, not raw days, so self-transitions (a phase to itself) are
    excluded — we care what a phase turns into, not how long it persists.
    """
    runs = _runs(phase)
    counts = pd.DataFrame(0, index=PHASES, columns=PHASES, dtype=float)
    for a, b in zip(runs[:-1], runs[1:]):
        if a["phase"] in PHASES and b["phase"] in PHASES:
            counts.loc[a["phase"], b["phase"]] += 1
    row_sums = counts.sum(axis=1).replace(0, np.nan)
    return counts.div(row_sums, axis=0).fillna(0.0)


def phase_persistence(phase: pd.Series) -> Dict[str, float]:
    """Volatility inertia: P(same phase tomorrow | phase today), per phase.

    High persistence => volatility state is 'sticky' (has inertia), a key VE
    hypothesis (research question 2).
    """
    p = phase.dropna()
    today = p.iloc[:-1].to_numpy()
    tomorrow = p.iloc[1:].to_numpy()
    out = {}
    for ph in PHASES:
        mask = today == ph
        out[ph] = float((tomorrow[mask] == ph).mean()) if mask.any() else float("nan")
    return out


def cycle_lengths(phase: pd.Series) -> Dict[str, object]:
    """Measure full-cycle length = days between consecutive Compression starts."""
    runs = _runs(phase)
    comp_starts = [r["start"] for r in runs if r["phase"] == "Compression"]
    if len(comp_starts) < 2:
        return {"n_cycles": len(comp_starts), "lengths": [], "mean": float("nan"),
                "median": float("nan"), "std": float("nan")}
    lengths = [(b - a).days for a, b in zip(comp_starts[:-1], comp_starts[1:])]
    arr = np.array(lengths, dtype=float)
    return {
        "n_cycles": len(lengths),
        "lengths": lengths,
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std()),
    }


def phase_length_stats(phase: pd.Series) -> pd.DataFrame:
    """Mean/median/count of how long each phase lasts (in trading days)."""
    runs = _runs(phase)
    rows = []
    for ph in PHASES:
        lens = [r["length"] for r in runs if r["phase"] == ph]
        rows.append({
            "phase": ph,
            "count": len(lens),
            "mean_days": float(np.mean(lens)) if lens else float("nan"),
            "median_days": float(np.median(lens)) if lens else float("nan"),
        })
    return pd.DataFrame(rows).set_index("phase")


def canonical_follow_rate(phase: pd.Series) -> Dict[str, float]:
    """For each phase, fraction of transitions that follow the canonical cycle.

    e.g. how often Compression is actually followed by Expansion. This directly
    tests research questions 3 & 4 (does compression lead to expansion, etc.).
    """
    tm = transition_matrix(phase)
    out = {}
    for src, dst in CANONICAL_CYCLE.items():
        out[src] = float(tm.loc[src, dst]) if src in tm.index else float("nan")
    return out


def analyse(phase: pd.Series) -> dict:
    """Bundle all per-asset cycle statistics into one dict."""
    return {
        "transition_matrix": transition_matrix(phase),
        "persistence": phase_persistence(phase),
        "cycle_lengths": cycle_lengths(phase),
        "phase_lengths": phase_length_stats(phase),
        "canonical_follow": canonical_follow_rate(phase),
        "phase_share": phase.value_counts(normalize=True).to_dict(),
    }
