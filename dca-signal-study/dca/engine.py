"""DCA backtest engine.

Common rules for every strategy (research design G1):
  * fixed monthly budget (default 50,000), added to a cash pool at each new month
  * unused budget carries forward with no cap
  * signal-based buys are 5,000 each, executed at the NEXT day's OPEN (no
    look-ahead); a buy only happens if the pool can afford it
  * benchmark A deploys the whole pool once a month; B spreads 10x5,000

Budget model: pool += monthly_budget at the first trading day of each month;
signal strategies spend 5,000 per firing while pool >= 5,000. This matches the
design's carry-forward example (July spends 30k -> August pool = 70k).

Fair comparison: every strategy receives the same 50,000/month, so differences
come only from *when* capital is deployed and how much sits idle (Cash Drag).
Final Assets always include leftover cash, and IRR treats the 50,000/month as
committed capital — so idle cash is correctly penalised.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import signals as S


# --------------------------------------------------------------------------
# desired-buy schedules per strategy  (amount to attempt at each day's OPEN)
# --------------------------------------------------------------------------

def _first_trading_days(index: pd.DatetimeIndex, k: int = 1) -> pd.DatetimeIndex:
    """First k trading days of each calendar month."""
    grp = pd.Series(index, index=index).groupby([index.year, index.month])
    return pd.DatetimeIndex(sorted(d for _, g in grp for d in g.iloc[:k]))


def desired_lump(target: pd.DataFrame, monthly_budget: float, **_) -> pd.Series:
    """Benchmark A: spend the whole pool on the first trading day of the month."""
    d = pd.Series(0.0, index=target.index)
    d.loc[_first_trading_days(target.index, 1)] = np.inf   # inf => drain pool
    return d


def desired_spread(target: pd.DataFrame, monthly_budget: float,
                   buy_size: float = 5000, n: int = 10, **_) -> pd.Series:
    """Benchmark B: 5,000 on each of the first 10 trading days of the month."""
    d = pd.Series(0.0, index=target.index)
    d.loc[_first_trading_days(target.index, n)] = buy_size
    return d


def desired_from_signal(target: pd.DataFrame, sig: pd.Series,
                        buy_size: float = 5000) -> pd.Series:
    """Signal fires at close of t -> buy `buy_size` at OPEN of t+1."""
    fire = sig.reindex(target.index).fillna(False).astype(bool).shift(1, fill_value=False)
    d = pd.Series(0.0, index=target.index)
    d[fire.to_numpy()] = buy_size
    return d


def build_strategies(signal_close: pd.Series, target: pd.DataFrame,
                     buy_size: float = 5000, monthly_budget: float = 50000) -> dict:
    """Return {name: desired-amount Series} for benchmarks A-E + extensions G2-G6."""
    tc = target["Close"]
    strat = {
        "A_monthly_lump":  desired_lump(target, monthly_budget),
        "B_spread_10x":    desired_spread(target, monthly_budget, buy_size),
        "C_0050_blackK":   desired_from_signal(target, S.black_k(signal_close), buy_size),
        "D_0050_down1pct": desired_from_signal(target, S.down_pct(signal_close, 0.01), buy_size),
        "E_2330_blackK":   desired_from_signal(target, S.black_k(tc), buy_size),
        "G2_0050_down2":   desired_from_signal(target, S.consecutive_down(signal_close, 2), buy_size),
        "G3_0050_down3":   desired_from_signal(target, S.consecutive_down(signal_close, 3), buy_size),
        "G5_0050_below_ma20": desired_from_signal(target, S.below_ma(signal_close, 20), buy_size),
        "G6_both_blackK":  desired_from_signal(
            target, S.black_k(signal_close) & S.black_k(tc), buy_size),
    }
    return strat


# --------------------------------------------------------------------------
# simulation + metrics
# --------------------------------------------------------------------------

@dataclass
class Result:
    name: str
    equity: pd.Series
    idle: pd.Series
    buys: pd.DataFrame
    metrics: dict = field(default_factory=dict)


def _irr_monthly(cfs: np.ndarray) -> float:
    """Money-weighted monthly IRR via bisection; NaN if no sign change.

    Bracket kept at [-0.5, 0.5]/month so (1+r)**t stays finite (a wider bracket
    underflows to zero and divides by zero).
    """
    t = np.arange(len(cfs))

    def npv(r):
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            return float(np.sum(cfs / (1.0 + r) ** t))

    lo, hi = -0.5, 0.5
    flo, fhi = npv(lo), npv(hi)
    if not (np.isfinite(flo) and np.isfinite(fhi)) or flo * fhi > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if not np.isfinite(fm):
            return float("nan")
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def simulate(name: str, target: pd.DataFrame, desired: pd.Series,
             monthly_budget: float = 50000, buy_size: float = 5000,
             min_buy: float = 1.0) -> Result:
    dates = target.index
    open_ = target["Open"].to_numpy()
    close = target["Close"].to_numpy()
    want = desired.reindex(dates).fillna(0.0).to_numpy()

    pool = 0.0
    shares = 0.0
    prev_month = None
    equity, idle = np.empty(len(dates)), np.empty(len(dates))
    buys = []
    n_months = 0
    for i, d in enumerate(dates):
        m = (d.year, d.month)
        if m != prev_month:
            pool += monthly_budget
            prev_month = m
            n_months += 1
        amt = min(want[i], pool)
        if amt >= min_buy and open_[i] > 0:
            sh = amt / open_[i]
            shares += sh
            pool -= amt
            buys.append({"date": d, "price": open_[i], "amount": amt, "shares": sh})
        equity[i] = shares * close[i] + pool
        idle[i] = pool

    eq = pd.Series(equity, index=dates)
    idle_s = pd.Series(idle, index=dates)
    bdf = pd.DataFrame(buys)

    total_contributed = n_months * monthly_budget
    total_invested = float(bdf["amount"].sum()) if len(bdf) else 0.0
    final_assets = float(eq.iloc[-1])
    years = len(dates) / 252.0

    # money-weighted IRR: -monthly_budget each month, +final at the end
    cfs = np.array([-monthly_budget] * n_months + [final_assets], dtype=float)
    irr_m = _irr_monthly(cfs)
    irr_ann = (1 + irr_m) ** 12 - 1 if not np.isnan(irr_m) else float("nan")

    avg_cost = (total_invested / bdf["shares"].sum()) if len(bdf) and bdf["shares"].sum() else float("nan")
    # drawdown / vol on the mark-to-market equity
    mdd = float((eq / eq.cummax() - 1).min())
    vol = float(eq.pct_change().std() * np.sqrt(252))
    # wait days between consecutive buys (calendar days)
    if len(bdf) >= 2:
        gaps = bdf["date"].diff().dropna().dt.days
        avg_wait = float(gaps.mean())
    else:
        avg_wait = float("nan")

    metrics = {
        "final_assets": final_assets,
        "total_contributed": total_contributed,
        "total_invested": total_invested,
        "cagr": (final_assets / total_contributed) ** (1 / years) - 1 if total_contributed > 0 else float("nan"),
        "irr_annual": irr_ann,
        "avg_cost": avg_cost,
        "n_buys": len(bdf),
        "avg_buys_per_month": len(bdf) / n_months if n_months else float("nan"),
        "avg_wait_days": avg_wait,
        "avg_idle_cash": float(idle_s.mean()),
        "max_idle_cash": float(idle_s.max()),
        "final_idle_cash": float(idle_s.iloc[-1]),
        "mdd": mdd,
        "vol": vol,
        "n_months": n_months,
    }
    return Result(name=name, equity=eq, idle=idle_s, buys=bdf, metrics=metrics)


def run_all(signal_df: pd.DataFrame, target_df: pd.DataFrame,
            monthly_budget: float = 50000, buy_size: float = 5000) -> dict:
    """Align the two assets on common dates and run every strategy."""
    common = signal_df.index.intersection(target_df.index)
    sig = signal_df.loc[common]
    tgt = target_df.loc[common]
    strategies = build_strategies(sig["Close"], tgt, buy_size, monthly_budget)
    return {name: simulate(name, tgt, desired, monthly_budget, buy_size)
            for name, desired in strategies.items()}
