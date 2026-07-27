"""
Performance / cost / efficiency / risk metrics for one simulated strategy.

All metrics are computed from the daily ledger and the buy log produced by
``engine.run``. Definitions are chosen so that strategies with different
deployment schedules remain comparable on the SAME committed-capital schedule
(50,000 NTD/month for everyone), which is the only way to make Cash Drag show
up honestly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _xirr(dates, amounts, guess=0.1):
    """Money-weighted annual return (XIRR) via bisection.

    ``amounts`` are signed cashflows from the investor's perspective:
    contributions are negative, terminal portfolio value is positive.
    """
    dates = pd.DatetimeIndex(dates)
    t0 = dates[0]
    years = np.array([(d - t0).days / 365.25 for d in dates])
    amounts = np.asarray(amounts, dtype=float)

    def npv(r):
        return np.sum(amounts / (1.0 + r) ** years)

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if np.isnan(f_lo) or np.isnan(f_hi) or f_lo * f_hi > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def compute(ledger: pd.DataFrame, buys: pd.DataFrame) -> dict:
    idx = ledger.index
    start, end = idx[0], idx[-1]
    years = (end - start).days / 365.25

    final_assets = float(ledger["equity"].iloc[-1])
    total_contributed = float(ledger["contribution"].sum())
    total_deployed = float(buys["amount"].sum()) if len(buys) else 0.0
    total_shares = float(buys["shares"].sum()) if len(buys) else 0.0
    end_cash = float(ledger["cash"].iloc[-1])

    multiple = final_assets / total_contributed if total_contributed else float("nan")
    cagr_on_contrib = multiple ** (1 / years) - 1 if multiple > 0 and years > 0 else float("nan")

    # ---- money-weighted IRR: monthly contributions out, terminal value in ---
    contrib_days = ledger[ledger["contribution"] > 0]
    cf_dates = list(contrib_days.index) + [end]
    cf_amts = list(-contrib_days["contribution"].values) + [final_assets]
    irr = _xirr(cf_dates, cf_amts)

    # ---- cost -------------------------------------------------------------
    avg_cost = total_deployed / total_shares if total_shares else float("nan")   # 平均買進成本 (share-weighted)
    avg_price = float(buys["price"].mean()) if len(buys) else float("nan")        # 平均成交價格 (simple mean)

    # ---- trade statistics -------------------------------------------------
    num_buys = int(len(buys))
    num_months = int((contrib_days.shape[0]))
    avg_buys_per_month = num_buys / num_months if num_months else float("nan")
    if num_buys >= 2:
        pos = np.array([idx.get_loc(d) for d in buys["date"]])
        avg_wait_days = float(np.mean(np.diff(np.sort(pos))))   # trading-day gap between buys
    else:
        avg_wait_days = float("nan")

    # ---- cash efficiency / drag ------------------------------------------
    avg_idle_cash = float(ledger["cash"].mean())            # 平均閒置現金 (time-weighted, daily)
    max_idle_cash = float(ledger["cash"].max())             # 最大閒置現金
    # cumulative capital that has been committed by each day
    committed = ledger["contribution"].cumsum()
    avg_committed = float(committed.mean())
    cash_drag_ratio = avg_idle_cash / avg_committed if avg_committed else float("nan")

    # ---- risk (time-weighted return curve; strip external contributions) --
    eq = ledger["equity"].values
    contrib = ledger["contribution"].values
    twr = [1.0]
    for i in range(1, len(eq)):
        prev = eq[i - 1]
        if prev <= 0:
            twr.append(twr[-1])
            continue
        r = (eq[i] - contrib[i]) / prev - 1.0
        twr.append(twr[-1] * (1.0 + r))
    twr = np.array(twr)
    peak = np.maximum.accumulate(twr)
    dd = twr / peak - 1.0
    mdd = float(dd.min())

    daily_ret = np.diff(twr) / twr[:-1]
    vol = float(np.nanstd(daily_ret) * np.sqrt(252)) if len(daily_ret) else float("nan")

    return {
        # performance
        "Final Assets": final_assets,
        "Total Contributed": total_contributed,
        "Total Deployed": total_deployed,
        "End Idle Cash": end_cash,
        "Multiple (x)": multiple,
        "CAGR (on contrib)": cagr_on_contrib,
        "IRR (money-weighted)": irr,
        # cost
        "Avg Buy Cost": avg_cost,
        "Avg Exec Price": avg_price,
        # trades
        "Num Buys": num_buys,
        "Avg Buys/Month": avg_buys_per_month,
        "Avg Wait (trading days)": avg_wait_days,
        # cash efficiency
        "Avg Idle Cash": avg_idle_cash,
        "Max Idle Cash": max_idle_cash,
        "Cash Drag Ratio": cash_drag_ratio,
        # risk
        "MDD": mdd,
        "Volatility (ann.)": vol,
    }
