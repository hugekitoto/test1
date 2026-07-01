"""VE visualisation — phase-shaded price, HV cycle, and equity curve.

Uses matplotlib's non-interactive Agg backend so it runs headless (the hosted
research environment has no display). Saves PNGs.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PHASE_COLORS = {
    "Compression": "#cfe8ff",  # calm blue
    "Expansion":   "#ffe0b3",  # warming orange
    "Exhaustion":  "#ffb3b3",  # hot red
    "Recovery":    "#d6f5d6",  # cooling green
}


def _shade_phases(ax, phase: pd.Series):
    """Shade the background of an axis by contiguous phase runs."""
    vals = phase.to_numpy(dtype=object)
    idx = phase.index
    i, n = 0, len(vals)
    while i < n:
        v = vals[i]
        if not isinstance(v, str):
            i += 1
            continue
        j = i
        while j + 1 < n and vals[j + 1] == v:
            j += 1
        ax.axvspan(idx[i], idx[j], color=PHASE_COLORS.get(v, "#eeeeee"),
                   alpha=0.55, linewidth=0)
        i = j + 1


def plot_asset(zoned: pd.DataFrame, bt: dict, name: str, out_path: str):
    """Three-panel figure: price+phases+trades, HV cycle, equity curve."""
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2, 2]})
    phase = zoned["PhaseSmooth"]

    # --- Panel 1: price with phase shading + entries/exits ---
    ax = axes[0]
    _shade_phases(ax, phase)
    ax.plot(zoned.index, zoned["Close"], color="#222", lw=1.0, label="Close")
    trades = bt.get("trades")
    if trades is not None and len(trades):
        for _, t in trades.iterrows():
            c = "green" if t["dir"] > 0 else "red"
            mk = "^" if t["dir"] > 0 else "v"
            ax.scatter(t["entry"], zoned["Close"].get(t["entry"], np.nan),
                       marker=mk, color=c, s=45, zorder=5)
            ax.scatter(t["exit"], zoned["Close"].get(t["exit"], np.nan),
                       marker="x", color="black", s=35, zorder=5)
    ax.set_title(f"{name} — price with volatility phases  "
                 f"(▲ long entry  ▼ short entry  ✕ exit)")
    ax.set_ylabel("Price")
    ax.legend(loc="upper left", fontsize=8)

    # --- Panel 2: HV + percentile ---
    ax = axes[1]
    _shade_phases(ax, phase)
    ax.plot(zoned.index, zoned["HV"], color="#8000a0", lw=1.0, label="Historical Vol")
    ax.set_ylabel("HV (ann.)")
    ax.legend(loc="upper left", fontsize=8)
    axp = ax.twinx()
    axp.plot(zoned.index, zoned["HV_pct"], color="#555", lw=0.7, ls="--",
             label="HV percentile")
    axp.set_ylim(0, 1)
    axp.set_ylabel("percentile")

    # --- Panel 3: equity vs buy & hold ---
    ax = axes[2]
    eq = bt.get("equity")
    if eq is not None and len(eq):
        ax.plot(eq.index, eq.values, color="#0060c0", lw=1.2, label="VE strategy")
    bh = (1 + zoned["Close"].pct_change().fillna(0)).cumprod()
    ax.plot(bh.index, bh.values, color="#999", lw=1.0, ls="--", label="Buy & Hold")
    ax.axhline(1.0, color="k", lw=0.5)
    ax.set_ylabel("equity (x)")
    ax.set_title("Strategy equity vs buy & hold")
    ax.legend(loc="upper left", fontsize=8)

    # phase legend
    handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.55)
               for c in PHASE_COLORS.values()]
    fig.legend(handles, list(PHASE_COLORS.keys()), loc="lower center",
               ncol=4, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
