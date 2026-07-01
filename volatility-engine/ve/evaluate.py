"""VE success-criteria evaluation (research design §11).

Given per-asset artifacts, decide whether VE meets each of the six criteria.
Everything returns plain data so the runner can print a scorecard.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def evaluate(assets: Dict[str, dict]) -> pd.DataFrame:
    """assets[name] must contain:
        canonical_follow : dict phase->rate
        persistence      : dict phase->rate
        time_consistency : DataFrame (phase x regime) of canonical rates
        bt_ls            : long/short backtest result dict
        strat_ret        : pd.Series of long/short daily strategy returns
        asset_ret        : pd.Series of daily asset returns
    Returns a scorecard DataFrame (criterion x [result, detail]).
    """
    names = list(assets)

    # C1: cycle reproducible across most assets
    follow_means = {n: np.nanmean(list(a["canonical_follow"].values()))
                    for n, a in assets.items()}
    c1_ok_frac = np.mean([v > 0.5 for v in follow_means.values()])
    c1 = (c1_ok_frac >= 0.6,
          f"{c1_ok_frac*100:.0f}% of assets show canonical-follow > 50% "
          f"(mean {np.mean(list(follow_means.values()))*100:.0f}%)")

    # C2: not industry-dependent -> low spread of follow-rate across assets
    spread = float(np.nanstd(list(follow_means.values())))
    c2 = (spread < 0.15, f"cross-asset follow-rate spread = {spread:.3f} "
                         f"(<0.15 => industry-independent)")

    # C3: time consistency across Bull/Bear/Range
    reg_spreads = []
    for a in assets.values():
        tc = a["time_consistency"]
        # spread of each phase's follow-rate across regimes, averaged
        reg_spreads.append(np.nanmean(tc.std(axis=1).to_numpy()))
    tc_spread = float(np.nanmean(reg_spreads))
    c3 = (tc_spread < 0.2, f"mean within-phase follow-rate spread across regimes "
                           f"= {tc_spread:.3f} (<0.20 => regime-consistent)")

    # C4: explains BOTH long and short (symmetry)
    long_rets = [a["bt_ls"]["metrics"]["avg_long_ret"] for a in assets.values()]
    short_rets = [a["bt_ls"]["metrics"]["avg_short_ret"] for a in assets.values()]
    ml, ms = np.nanmean(long_rets), np.nanmean(short_rets)
    c4 = (ml > 0 and ms > 0,
          f"avg trade return  long={ml*100:+.2f}%  short={ms*100:+.2f}%  "
          f"(both >0 => symmetric edge)")

    # C5: Build/Exit derived from cycle & actually tradable + net positive
    tot_rets = [a["bt_ls"]["metrics"]["total_return"] for a in assets.values()]
    n_trades = [a["bt_ls"]["metrics"]["n_trades"] for a in assets.values()]
    pos_frac = np.mean([r > 0 for r in tot_rets])
    c5 = (pos_frac >= 0.6 and np.mean(n_trades) >= 5,
          f"{pos_frac*100:.0f}% of assets net-positive from cycle zones "
          f"(avg {np.mean(n_trades):.0f} trades/asset)")

    # C6: independent from momentum/trend -> low corr(strategy, buy&hold)
    corrs = []
    for a in assets.values():
        s, r = a["strat_ret"].align(a["asset_ret"], join="inner")
        if s.std() > 0 and r.std() > 0:
            corrs.append(float(np.corrcoef(s, r)[0, 1]))
    mean_corr = float(np.nanmean(corrs)) if corrs else float("nan")
    c6 = (abs(mean_corr) < 0.4,
          f"mean corr(VE returns, buy&hold) = {mean_corr:+.2f} "
          f"(|corr|<0.4 => independent alpha engine)")

    rows = [
        ("1. Reproducible across stocks & ETFs", *c1),
        ("2. Not industry-dependent", *c2),
        ("3. Time-consistent (bull/bear/range)", *c3),
        ("4. Explains long AND short", *c4),
        ("5. Build/Exit derived from cycle", *c5),
        ("6. Independent from momentum/trend", *c6),
    ]
    df = pd.DataFrame([(c, "PASS" if ok else "FAIL", d) for c, ok, d in rows],
                      columns=["criterion", "result", "detail"]).set_index("criterion")
    return df
