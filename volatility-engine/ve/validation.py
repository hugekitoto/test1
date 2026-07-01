"""VE v0.2 — the six-layer validation framework.

Layers 1-2 (existence + not-self-referential) live in transitions.py. This
module adds layers 3-6, the ones that decide whether VE is a real, tradeable,
universal phenomenon rather than a high-AUC classifier:

  Layer 3  generality   : cross_time, cross_asset, regime_auc
  Layer 4  new info      : information_gain
  Layer 5  trading value : oracle_test        (the most important gate)
  Layer 6  mechanism     : liquidity_test      (is it a liquidity lifecycle?)

Everything reuses the tiny numpy ML kit in transitions.py, so no new deps.
Guiding question (design v0.2): is there a volatility lifecycle that recurs
across time, assets and regimes AND carries trading value?
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .config import PHASES, VEConfig, DEFAULT
from . import regimes
from .transitions import (
    FEATURES, build_transition_features, remaining_days_in_phase,
    _standardize, _fit_logistic, _predict, _auc,
)

BASELINE_FEATURES = ["time_in_phase", "hv_pct"]          # "already known" info
PRICE_VOL_FEATURES = [f for f in FEATURES if f != "vol_z"]  # excludes liquidity


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def _pooled_xy(ann: pd.DataFrame, horizon: int, cfg: VEConfig) -> pd.DataFrame:
    """All bars pooled: features + label _y (current phase ends within horizon)."""
    feats = build_transition_features(ann, cfg)
    rem = remaining_days_in_phase(ann)
    df = feats.copy()
    df["_y"] = (rem <= (horizon - 1)).astype(float)
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def _fit_auc(Xtr, ytr, Xte, yte) -> float:
    if len(Xtr) < 80 or len(Xte) < 40:
        return float("nan")
    if ytr.sum() == 0 or (yte == 1).sum() == 0 or (yte == 0).sum() == 0:
        return float("nan")
    Xtr_s, mu, sd = _standardize(Xtr)
    w = _fit_logistic(Xtr_s, ytr)
    Xte_s, _, _ = _standardize(Xte, mu, sd)
    return _auc(yte, _predict(w, Xte_s))


def _split_auc(df: pd.DataFrame, cols: List[str], train_frac: float = 0.7) -> float:
    split = int(len(df) * train_frac)
    tr, te = df.iloc[:split], df.iloc[split:]
    return _fit_auc(tr[cols].to_numpy(), tr["_y"].to_numpy(),
                    te[cols].to_numpy(), te["_y"].to_numpy())


def _phase_runs(ann: pd.DataFrame):
    ps = ann["PhaseSmooth"].to_numpy(dtype=object)
    runs, i, n = [], 0, len(ps)
    while i < n:
        v = ps[i]
        if not isinstance(v, str):
            i += 1
            continue
        j = i
        while j + 1 < n and ps[j + 1] == v:
            j += 1
        runs.append({"phase": v, "start_i": i, "end_i": j})
        i = j + 1
    return runs


# --------------------------------------------------------------------------
# Layer 3 — generality
# --------------------------------------------------------------------------

def cross_time(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT,
               test_block: int = 2, min_train_years: int = 3) -> List[dict]:
    """Walk-forward: train on all years up to Y, test the next `test_block`.

    Stable AUC across eras => a long-run regularity, not a fit to one market.
    """
    df = _pooled_xy(ann, horizon, cfg)
    years = df.index.year
    y0, y1 = int(years.min()), int(years.max())
    out = []
    ty = y0 + min_train_years
    while ty + test_block - 1 <= y1:
        tr = df[years < ty]
        te = df[(years >= ty) & (years < ty + test_block)]
        auc = _fit_auc(tr[FEATURES].to_numpy(), tr["_y"].to_numpy(),
                       te[FEATURES].to_numpy(), te["_y"].to_numpy())
        out.append({"train": f"{y0}-{ty - 1}", "test": f"{ty}-{ty + test_block - 1}",
                    "auc": auc})
        ty += test_block
    return out


def cross_asset(anns: Dict[str, pd.DataFrame], horizon: int = 5,
                cfg: VEConfig = DEFAULT) -> pd.DataFrame:
    """Train on each asset, test on every asset (features scaled per-asset).

    Off-diagonal AUC high => the volatility structure transfers across names /
    industries (a market-wide phenomenon). Diagonal is in-sample (optimistic).
    """
    data = {name: _pooled_xy(ann, horizon, cfg) for name, ann in anns.items()}
    names = list(data)
    mat = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        tr = data[a]
        ytr = tr["_y"].to_numpy()
        if ytr.sum() == 0:
            continue
        Xtr_s, _, _ = _standardize(tr[FEATURES].to_numpy())
        w = _fit_logistic(Xtr_s, ytr)
        for b in names:
            te = data[b]
            yte = te["_y"].to_numpy()
            Xte_s, _, _ = _standardize(te[FEATURES].to_numpy())  # b's own scale
            if (yte == 1).sum() == 0 or (yte == 0).sum() == 0:
                mat.loc[a, b] = np.nan
            else:
                mat.loc[a, b] = _auc(yte, _predict(w, Xte_s))
    return mat


def regime_auc(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT) -> dict:
    """Fit on the training period; report test AUC sliced by Bull/Bear/Range."""
    df = _pooled_xy(ann, horizon, cfg)
    reg = regimes.tag_regime(ann["Close"]).reindex(df.index)
    split = int(len(df) * 0.7)
    tr, te = df.iloc[:split], df.iloc[split:]
    reg_te = reg.iloc[split:]
    ytr = tr["_y"].to_numpy()
    if ytr.sum() == 0:
        return {}
    Xtr_s, mu, sd = _standardize(tr[FEATURES].to_numpy())
    w = _fit_logistic(Xtr_s, ytr)
    out = {}
    for rg in ["ALL", "Bull", "Bear", "Range"]:
        mask = np.ones(len(te), bool) if rg == "ALL" else (reg_te == rg).to_numpy()
        sub = te[mask]
        ysub = sub["_y"].to_numpy()
        if len(sub) < 40 or (ysub == 1).sum() == 0 or (ysub == 0).sum() == 0:
            out[rg] = np.nan
            continue
        Xs, _, _ = _standardize(sub[FEATURES].to_numpy(), mu, sd)
        out[rg] = _auc(ysub, _predict(w, Xs))
    return out


# --------------------------------------------------------------------------
# Layer 4 — information gain
# --------------------------------------------------------------------------

def information_gain(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT) -> dict:
    """Does adding features beyond {time_in_phase, hv_pct} really add skill?

    Reports baseline vs full AUC and each feature's leave-one-out contribution
    (how much AUC drops when it is removed). Near-zero LOO => that feature is
    repackaging existing info, not new alpha.
    """
    df = _pooled_xy(ann, horizon, cfg)
    base = _split_auc(df, BASELINE_FEATURES)
    full = _split_auc(df, FEATURES)
    loo = {}
    for f in FEATURES:
        cols = [c for c in FEATURES if c != f]
        loo[f] = full - _split_auc(df, cols)
    return {"baseline_auc": base, "full_auc": full, "gain": full - base, "loo": loo}


# --------------------------------------------------------------------------
# Layer 5 — Oracle decision test (trading value)
# --------------------------------------------------------------------------

def oracle_test(ann: pd.DataFrame, cfg: VEConfig = DEFAULT,
                straddle_cost: float = 0.02) -> pd.DataFrame:
    """With PERFECT phase timing, is a phase even tradeable?

    Per phase, over each run:
      avg_abs_move     : average |cumulative return| — the raw opportunity
      directional_best : upper bound if you also knew direction (= |move|)
      long_only        : always-long return (~0 if the phase is direction-neutral)
      straddle_net     : |move| - straddle_cost — value of a pure volatility trade
      straddle_winrate : share of runs whose move exceeds the cost

    If directional_best is tiny -> no opportunity at all. If it's large but
    long_only ~0 and straddle_net <= 0 -> the phase has CLASSIFICATION value but
    not TRADING value (you can't monetise it directionally, and the move doesn't
    pay for a straddle). This is the key Phase-vs-Trade verdict.
    """
    logret = ann["LogRet"]
    runs = _phase_runs(ann)
    rows = []
    for ph in PHASES:
        moves = np.array([logret.iloc[r["start_i"]:r["end_i"] + 1].sum()
                          for r in runs if r["phase"] == ph])
        if len(moves) == 0:
            rows.append({"phase": ph, "n": 0})
            continue
        absmove = np.abs(moves)
        rows.append({
            "phase": ph, "n": len(moves),
            "avg_abs_move": float(absmove.mean()),
            "directional_best": float(absmove.mean()),
            "long_only": float(moves.mean()),
            "straddle_net": float((absmove - straddle_cost).mean()),
            "straddle_winrate": float((absmove > straddle_cost).mean()),
        })
    return pd.DataFrame(rows).set_index("phase")


# --------------------------------------------------------------------------
# Layer 6 — Liquidity hypothesis
# --------------------------------------------------------------------------

def _liquidity_features(ann: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=ann.index)
    v = ann["Volume"]
    out["vol_z"] = (v - v.rolling(60).mean()) / v.rolling(60).std()
    out["vol_trend"] = v.rolling(5).mean() / v.rolling(20).mean()
    if "Turnover" in ann.columns:
        t = ann["Turnover"]
        out["turnover_z"] = (t - t.rolling(60).mean()) / t.rolling(60).std()
        # Amihud illiquidity: |return| per unit turnover (higher = more illiquid)
        out["amihud"] = (ann["LogRet"].abs() / t.replace(0, np.nan)).rolling(20).mean()
    return out


def liquidity_test(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT,
                   max_lag: int = 10) -> dict:
    """Does liquidity LEAD volatility, and does it add predictive info?

    (a) Lead-lag: cross-correlation of volume change vs HV change. A positive
        best-lag (past volume ~ current HV) supports liquidity -> volatility.
    (b) Info gain: AUC(price-vol features) vs AUC(price-vol + liquidity features)
        for predicting the next transition.
    """
    dvol = ann["Volume"].pct_change()
    dhv = ann["HV"].diff()
    xcorr = {}
    for L in range(0, max_lag + 1):
        # dvol from L days ago vs today's dHV: L>0 means volume leads volatility
        xcorr[L] = float(dvol.shift(L).corr(dhv))
    valid = {L: c for L, c in xcorr.items() if not np.isnan(c)}
    best_lag = max(valid, key=lambda k: abs(valid[k])) if valid else 0

    df = _pooled_xy(ann, horizon, cfg)
    liq = _liquidity_features(ann).reindex(df.index)
    liq_cols = list(liq.columns)
    # vol_z already lives in df (it's a base feature); add only the extras to
    # avoid a column collision, then reference all liquidity cols by name.
    extra = liq[[c for c in liq.columns if c not in df.columns]]
    dff = pd.concat([df, extra], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    auc_pv = _split_auc(dff, PRICE_VOL_FEATURES)
    auc_all = _split_auc(dff, PRICE_VOL_FEATURES + liq_cols)
    return {
        "xcorr": xcorr,
        "best_lag": best_lag,
        "best_xcorr": xcorr.get(best_lag, float("nan")),
        "auc_price_vol": auc_pv,
        "auc_with_liquidity": auc_all,
        "liquidity_gain": auc_all - auc_pv,
        "liquidity_features": liq_cols,
    }
