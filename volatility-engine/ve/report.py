"""VE reporting layer.

Aggregates per-asset cycle statistics and answers the 8 research questions
(design section 9) in plain text. This is the Phase-1 deliverable: not a
trading strategy, just evidence for/against the existence of a volatility cycle.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .config import PHASES, CANONICAL_CYCLE


def _fmt_pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:5.1f}%"


def cross_asset_summary(results: Dict[str, dict]) -> pd.DataFrame:
    """One row per asset with the headline cycle metrics."""
    rows = []
    for name, r in results.items():
        cl = r["cycle_lengths"]
        follow = r["canonical_follow"]
        pers = r["persistence"]
        rows.append({
            "asset": name,
            "n_cycles": cl["n_cycles"],
            "cycle_len_mean_d": round(cl["mean"], 1) if not np.isnan(cl["mean"]) else np.nan,
            "cycle_len_median_d": round(cl["median"], 1) if not np.isnan(cl["median"]) else np.nan,
            "comp->exp": round(follow.get("Compression", np.nan), 3),
            "exp->exh": round(follow.get("Expansion", np.nan), 3),
            "exh->rec": round(follow.get("Recovery", np.nan), 3),
            "mean_persist": round(np.nanmean(list(pers.values())), 3),
        })
    return pd.DataFrame(rows).set_index("asset")


def _avg_transition(results: Dict[str, dict]) -> pd.DataFrame:
    mats = [r["transition_matrix"] for r in results.values()]
    return sum(mats) / len(mats)


def answer_research_questions(results: Dict[str, dict]) -> str:
    """Produce the human-readable Phase-1 conclusion text."""
    summary = cross_asset_summary(results)
    avg_tm = _avg_transition(results)

    # aggregate helpers
    all_persist = [np.nanmean(list(r["persistence"].values())) for r in results.values()]
    comp_exp = [r["canonical_follow"].get("Compression", np.nan) for r in results.values()]
    exp_exh = [r["canonical_follow"].get("Expansion", np.nan) for r in results.values()]
    exh_rec = [r["canonical_follow"].get("Recovery", np.nan) for r in results.values()]
    rec_comp = [r["canonical_follow"].get("Recovery", np.nan) for r in results.values()]
    cyc_means = [r["cycle_lengths"]["mean"] for r in results.values()
                 if not np.isnan(r["cycle_lengths"]["mean"])]

    lines = []
    lines.append("=" * 68)
    lines.append("VOLATILITY ENGINE — PHASE 1 RESEARCH REPORT")
    lines.append("Question: does a repeatable volatility cycle exist?")
    lines.append("=" * 68)
    lines.append("")
    lines.append("Per-asset summary")
    lines.append("-" * 68)
    lines.append(summary.to_string())
    lines.append("")
    lines.append("Average run-to-run transition matrix  P(next | current)")
    lines.append("-" * 68)
    lines.append(avg_tm.round(3).to_string())
    lines.append("")
    lines.append("Research questions")
    lines.append("-" * 68)

    q = []
    # Q1 life cycle
    mean_follow = np.nanmean(comp_exp + exp_exh + exh_rec)
    q.append(
        f"1. Volatility life cycle?  Canonical steps fire {_fmt_pct(mean_follow)} of the "
        f"time on average (random would be ~33%). "
        f"{'YES — structure present.' if mean_follow > 0.45 else 'WEAK — near random.'}"
    )
    # Q2 inertia
    mp = np.nanmean(all_persist)
    q.append(
        f"2. Volatility inertia?  Same-phase-next-day probability = {_fmt_pct(mp)}. "
        f"{'YES — volatility state is sticky.' if mp > 0.6 else 'WEAK.'}"
    )
    # Q3 compression -> expansion
    ce = np.nanmean(comp_exp)
    q.append(
        f"3. Compression leads to Expansion?  {_fmt_pct(ce)} of Compression runs are "
        f"followed by Expansion. {'YES.' if ce > 0.5 else 'MIXED.'}"
    )
    # Q4 expansion -> contraction (via exhaustion/recovery back to compression)
    er = np.nanmean(exh_rec)
    q.append(
        f"4. Expansion leads back to Contraction?  Exhaustion->Recovery fires "
        f"{_fmt_pct(er)}; the cycle closes back toward Compression. "
        f"{'YES.' if er > 0.5 else 'MIXED.'}"
    )
    # Q5 average cycle
    if cyc_means:
        q.append(
            f"5. Average cycle length?  {np.mean(cyc_means):.0f} calendar days "
            f"(range {np.min(cyc_means):.0f}-{np.max(cyc_means):.0f} across assets)."
        )
    else:
        q.append("5. Average cycle length?  Not enough completed cycles in sample.")
    # Q6 ETF vs stock common structure
    spread = np.nanstd([np.nanmean(list(r['persistence'].values())) for r in results.values()])
    q.append(
        f"6. ETF & single stocks share structure?  Cross-asset persistence spread "
        f"= {spread:.3f} (small => shared regime behaviour). "
        f"{'Consistent across assets.' if spread < 0.1 else 'Some divergence.'}"
    )
    # Q7 long/short symmetry — VE is direction-neutral by construction
    q.append(
        "7. Long/short symmetry?  Phases are defined on volatility only, so every "
        "phase applies identically to over- and under-shoots — symmetric by design; "
        "the trading layer decides whether shorts are enabled."
    )
    # Q8 cross-market — needs stage 3 data (US ETFs etc.)
    q.append(
        "8. Cross-market common structure?  Requires stage-2/3 data (mid/small caps, "
        "US ETFs). Framework is asset-agnostic and ready once that data is supplied."
    )
    lines.extend(q)
    lines.append("")
    lines.append("Note: run above is on the data provided. With the bundled synthetic")
    lines.append("sample (which contains a *planted* cycle) strong YES answers confirm the")
    lines.append("engine detects known cycles. Real conclusions require real market data.")
    lines.append("=" * 68)
    return "\n".join(lines)
