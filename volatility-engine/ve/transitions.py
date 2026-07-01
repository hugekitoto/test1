"""VE v0.2 — Phase Transition modelling.

Positioning (research design v0.2): the valuable thing is not *which* phase the
market is in, but *when it starts moving to the next one*. Identifying a phase
is not a trade signal ("knowing it's winter doesn't mean ski today"). So this
module studies **transitions**, and — following the project's highest
principle — it MEASURES whether the transition can actually be *predicted*
out-of-sample before anyone designs a trading rule.

It answers, per day, using volatility features only (never price direction):
  1. Hazard: given we've been in this phase D days, how likely does it end now?
  2. P(transition within the next `horizon` days), from a model.
  3. Which features drive transitions (candidate "Triggers").
  4. Does the model beat the base rate on a held-out period? (AUC on a time split)

No sklearn dependency — logistic regression, standardisation and AUC are small
numpy routines so this runs anywhere (e.g. Colab) without extra installs.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .config import PHASES, CANONICAL_CYCLE, VEConfig, DEFAULT

# Predictive features — all computable from data up to and including day t
# (no look-ahead). These are volatility + time characteristics, i.e. exactly
# the "波動特徵 / 時間因素" the design flags as Trigger candidates.
FEATURES = [
    "time_in_phase",  # days elapsed in the current phase run
    "hv_pct",         # volatility water level (percentile)
    "hv_mom",         # volatility momentum (EMA fast - slow)
    "hv_accel",       # change in momentum (is the move accelerating?)
    "dhv5",           # 5-day HV rate of change
    "atr_pct",        # ATR percentile
    "range_exp",      # today's range vs its 20-day average
    "vol_z",          # volume z-score (participation surge?)
]


def remaining_days_in_phase(ann: pd.DataFrame) -> pd.Series:
    """Days from each bar until its current PhaseSmooth run ends (0 = last bar)."""
    ps = ann["PhaseSmooth"].to_numpy(dtype=object)
    n = len(ps)
    remaining = np.full(n, np.nan)
    i = 0
    while i < n:
        v = ps[i]
        if not isinstance(v, str):
            i += 1
            continue
        j = i
        while j + 1 < n and ps[j + 1] == v:
            j += 1
        for k in range(i, j + 1):
            remaining[k] = j - k
        i = j + 1
    return pd.Series(remaining, index=ann.index)


def build_transition_features(ann: pd.DataFrame, cfg: VEConfig = DEFAULT) -> pd.DataFrame:
    """Backward-looking feature matrix used to predict transitions."""
    out = pd.DataFrame(index=ann.index)
    out["time_in_phase"] = ann["PhaseDuration"]
    out["hv_pct"] = ann["HV_pct"]
    out["hv_mom"] = ann["VolMomentum"]
    out["hv_accel"] = ann["VolMomentum"].diff()
    out["dhv5"] = ann["HV"].pct_change(5)
    out["atr_pct"] = ann["ATR"].rolling(
        cfg.percentile_window, min_periods=cfg.percentile_window // 2).rank(pct=True)
    dr = ann["DailyRange"]
    out["range_exp"] = dr / dr.rolling(20).mean()
    v = ann["Volume"]
    out["vol_z"] = (v - v.rolling(60).mean()) / v.rolling(60).std()
    return out


def hazard_curve(ann: pd.DataFrame, phase: str) -> pd.DataFrame:
    """Discrete hazard h(d) = P(run ends on day d | it reached day d).

    Rising hazard with d => the longer the phase lasts, the more likely it is to
    transition — a time-based Trigger. Returns a frame indexed by day-in-phase.
    """
    ps = ann["PhaseSmooth"].to_numpy(dtype=object)
    lengths = []
    n = len(ps)
    i = 0
    while i < n:
        v = ps[i]
        if v != phase:
            i += 1
            continue
        j = i
        while j + 1 < n and ps[j + 1] == v:
            j += 1
        lengths.append(j - i + 1)
        i = j + 1
    lengths = np.array(lengths)
    if len(lengths) == 0:
        return pd.DataFrame(columns=["at_risk", "ended", "hazard"])
    max_d = int(lengths.max())
    rows = []
    for d in range(1, max_d + 1):
        at_risk = int((lengths >= d).sum())
        ended = int((lengths == d).sum())
        rows.append({"day_in_phase": d, "at_risk": at_risk, "ended": ended,
                     "hazard": ended / at_risk if at_risk else np.nan})
    return pd.DataFrame(rows).set_index("day_in_phase")


# --------------------------- tiny numpy ML kit ---------------------------

def _standardize(X, mu=None, sd=None):
    if mu is None:
        mu = np.nanmean(X, axis=0)
        sd = np.nanstd(X, axis=0)
        sd = np.where(sd == 0, 1.0, sd)
    return (X - mu) / sd, mu, sd


def _fit_logistic(X, y, l2=1.0, iters=800, lr=0.3):
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xb @ w)))
        reg = np.r_[0.0, w[1:]]
        grad = Xb.T @ (p - y) / n + l2 * reg / n
        w -= lr * grad
    return w


def _predict(w, X):
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return 1.0 / (1.0 + np.exp(-(Xb @ w)))


def _auc(y, p):
    """ROC AUC via the Mann-Whitney statistic (tie-aware average ranks)."""
    y = np.asarray(y)
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p))
    s = p[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        avg = (i + j) / 2 + 1  # average rank (1-indexed)
        ranks[order[i:j + 1]] = avg
        i = j + 1
    r_pos = ranks[y == 1].sum()
    return float((r_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


# --------------------------- transition model ---------------------------

def fit_transition_model(ann: pd.DataFrame, phase: str, horizon: int = 5,
                         train_frac: float = 0.7, cfg: VEConfig = DEFAULT) -> Optional[dict]:
    """Predict P(current `phase` ends within `horizon` days) from features.

    Trains on the first `train_frac` of that phase's bars and tests on the rest
    (a strict time split — no shuffling, no leakage). Returns AUC on the held-out
    tail, the base rate to beat, and standardised-feature coefficients (the
    candidate Triggers). None if there isn't enough data.
    """
    feats = build_transition_features(ann, cfg)
    rem = remaining_days_in_phase(ann)
    mask = ann["PhaseSmooth"] == phase

    label = (rem <= (horizon - 1)).astype(float)
    df = feats[mask].copy()
    df["y"] = label[mask].to_numpy()
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < 80 or df["y"].nunique() < 2:
        return None

    split = int(len(df) * train_frac)
    Xtr = df[FEATURES].iloc[:split].to_numpy()
    ytr = df["y"].iloc[:split].to_numpy()
    Xte = df[FEATURES].iloc[split:].to_numpy()
    yte = df["y"].iloc[split:].to_numpy()
    if ytr.sum() == 0 or (yte == 1).sum() == 0 or (yte == 0).sum() == 0:
        return None

    Xtr_s, mu, sd = _standardize(Xtr)
    w = _fit_logistic(Xtr_s, ytr)
    Xte_s, _, _ = _standardize(Xte, mu, sd)
    p_te = _predict(w, Xte_s)

    return {
        "phase": phase,
        "next_phase": CANONICAL_CYCLE.get(phase, "?"),
        "horizon": horizon,
        "n_train": split,
        "n_test": len(df) - split,
        "base_rate": float(yte.mean()),
        "auc": _auc(yte, p_te),
        "coefs": dict(zip(FEATURES, w[1:])),
    }


def _time_split_auc(feat_df: pd.DataFrame, y: np.ndarray, train_frac: float = 0.7,
                    permute: bool = False, seed: int = 0) -> float:
    """Generic: fit logistic on the first `train_frac`, return AUC on the tail.

    `permute=True` shuffles labels (a placebo) — a healthy pipeline then scores
    ~0.50. Reused for full / time-only / external-target / placebo checks.
    """
    df = feat_df.replace([np.inf, -np.inf], np.nan).copy()
    df["_y"] = y
    df = df.dropna()
    if len(df) < 100 or df["_y"].nunique() < 2:
        return float("nan")
    cols = [c for c in df.columns if c != "_y"]
    yv = df["_y"].to_numpy().astype(float)
    if permute:
        yv = np.random.default_rng(seed).permutation(yv)
    split = int(len(df) * train_frac)
    Xtr, ytr = df[cols].iloc[:split].to_numpy(), yv[:split]
    Xte, yte = df[cols].iloc[split:].to_numpy(), yv[split:]
    if ytr.sum() == 0 or (yte == 1).sum() == 0 or (yte == 0).sum() == 0:
        return float("nan")
    Xtr_s, mu, sd = _standardize(Xtr)
    w = _fit_logistic(Xtr_s, ytr)
    Xte_s, _, _ = _standardize(Xte, mu, sd)
    return _auc(yte, _predict(w, Xte_s))


def robustness_check(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT) -> dict:
    """Separate genuine predictive power from mechanical artifact.

    Returns mean out-of-sample AUCs for:
      full            : all features -> self-defined phase-end (the headline)
      placebo         : same, labels shuffled (should be ~0.50)
      time_only       : only time_in_phase (pure duration/hazard structure)
      external_target : features -> "future 10d realised vol > past 10d" — a
                        target NOT derived from our phase definition, so high AUC
                        here means the predictability is genuine, not circular.
      external_placebo: external target with shuffled labels (~0.50 sanity).
    """
    feats = build_transition_features(ann, cfg)
    rem = remaining_days_in_phase(ann)
    y_phase = (rem <= (horizon - 1)).astype(float).to_numpy()
    phase_arr = ann["PhaseSmooth"].to_numpy(dtype=object)

    full, placebo, timeonly = [], [], []
    for ph in PHASES:
        mask = np.array([p == ph for p in phase_arr])
        if mask.sum() < 100:
            continue
        fdf = feats[mask]
        yy = y_phase[mask]
        for acc, kwargs, cols in (
            (full, {}, FEATURES),
            (placebo, {"permute": True}, FEATURES),
            (timeonly, {}, ["time_in_phase"]),
        ):
            a = _time_split_auc(fdf[cols], yy, **kwargs)
            if not np.isnan(a):
                acc.append(a)

    # External, non-self-referential target: future realised-vol regime.
    logret = ann["LogRet"]
    past_rv = logret.rolling(10).std()
    fut_rv = logret.rolling(10).std().shift(-10)
    y_ext = (fut_rv > past_rv).astype(float).to_numpy()
    a_ext = _time_split_auc(feats[FEATURES], y_ext)
    a_ext_p = _time_split_auc(feats[FEATURES], y_ext, permute=True)

    mean = lambda x: float(np.mean(x)) if x else float("nan")
    return {
        "full": mean(full),
        "placebo": mean(placebo),
        "time_only": mean(timeonly),
        "external_target": a_ext,
        "external_placebo": a_ext_p,
    }


def study_asset(ann: pd.DataFrame, horizon: int = 5, cfg: VEConfig = DEFAULT) -> dict:
    """Run the transition study for every phase of one asset."""
    models = {}
    hazards = {}
    for ph in PHASES:
        m = fit_transition_model(ann, ph, horizon=horizon, cfg=cfg)
        if m is not None:
            models[ph] = m
        hazards[ph] = hazard_curve(ann, ph)
    return {"models": models, "hazards": hazards, "horizon": horizon}


def predictive_verdict(models: dict) -> dict:
    """Summarise out-of-sample skill across phases.

    AUC ~0.50 = no skill; >0.55 = weak; >0.60 = usable; >0.65 = strong.
    The design's gate: only build trading rules once the model *predicts*.
    """
    aucs = {ph: m["auc"] for ph, m in models.items() if not np.isnan(m["auc"])}
    if not aucs:
        return {"mean_auc": float("nan"), "verdict": "insufficient data", "per_phase": {}}
    mean_auc = float(np.mean(list(aucs.values())))
    if mean_auc > 0.60:
        v = "PREDICTIVE — model beats base rate out-of-sample; trading rules justified"
    elif mean_auc > 0.55:
        v = "WEAK signal — some skill, needs stronger Triggers before trading"
    else:
        v = "NOT predictive yet — do NOT design trading rules (per §highest principle)"
    return {"mean_auc": mean_auc, "verdict": v, "per_phase": aucs}
