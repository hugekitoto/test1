"""
Unified backtest engine.

A single simulator runs EVERY strategy so that the budget framework is held
constant and only the buy-order schedule varies. This is what makes the
comparison fair and what lets Cash Drag emerge naturally from the mechanics
rather than being modelled separately.

Mechanics (per the research design)
------------------------------------
* Capital schedule: 50,000 NTD is credited to a cash pool on the first trading
  day of every calendar month. Unused cash **carries over with no cap**.
* Each strategy supplies buy orders (amount, execution date). Orders fill
  **all-or-nothing** at that day's OPEN, and only if the cash pool can cover
  them. An order that cannot be covered is simply skipped (its budget stays in
  the pool and carries over) -- this is exactly the "已投入本月預算就停買 /
  未用完就累積" rule, reproduced by the shared pool.
* Idle cash optionally earns ``idle_annual_rate`` (default 0% -> pure Cash
  Drag). Fractional shares are allowed by default (TW 零股); set a ``lot_size``
  to force whole-lot buys.

The engine returns a daily ledger (mark-to-market equity, cash, contributions)
and the list of executed buys, which ``metrics.py`` turns into the report
figures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies import PER_BUY, MONTHLY_BUDGET


def _month_starts(index: pd.DatetimeIndex) -> set:
    s = pd.Series(index, index=index)
    firsts = s.groupby([index.year, index.month]).first().values
    return set(pd.DatetimeIndex(firsts))


def run(tsmc: pd.DataFrame,
        orders: pd.Series,
        monthly_budget: float = MONTHLY_BUDGET,
        per_buy: float = PER_BUY,
        idle_annual_rate: float = 0.0,
        lot_size: float | None = None) -> dict:
    """Simulate one strategy.

    Parameters
    ----------
    tsmc : DataFrame with columns open, close indexed by trading date.
    orders : Series of requested NTD amounts indexed by execution date.
    """
    index = tsmc.index
    orders = orders.reindex(index).fillna(0.0)
    month_starts = _month_starts(index)
    daily_rate = (1.0 + idle_annual_rate) ** (1 / 252.0) - 1.0

    cash = 0.0
    shares = 0.0
    rows = []
    buys = []

    for dt in index:
        o = tsmc.at[dt, "open"]
        c = tsmc.at[dt, "close"]

        # 1) accrue interest on idle cash (0 by default)
        if daily_rate:
            cash *= (1.0 + daily_rate)

        # 2) monthly contribution credited at the start of the month
        contribution = monthly_budget if dt in month_starts else 0.0
        cash += contribution

        # 3) attempt to fill the day's order at the OPEN, all-or-nothing
        want = float(orders.at[dt])
        filled = 0.0
        bought_shares = 0.0
        if want > 0 and cash + 1e-9 >= want and o > 0:
            if lot_size:
                # buy the largest whole number of lots that fits within `want`
                lots = int((want / o) // lot_size)
                bought_shares = lots * lot_size
                filled = bought_shares * o
                if filled > cash + 1e-9:
                    bought_shares, filled = 0.0, 0.0
            else:
                bought_shares = want / o
                filled = want
            cash -= filled
            shares += bought_shares
            if filled > 0:
                buys.append({"date": dt, "price": o, "amount": filled,
                             "shares": bought_shares})

        equity = shares * c + cash
        rows.append({"date": dt, "open": o, "close": c,
                     "contribution": contribution, "cash": cash,
                     "shares": shares, "buy_amount": filled,
                     "equity": equity})

    ledger = pd.DataFrame(rows).set_index("date")
    buys_df = pd.DataFrame(buys) if buys else pd.DataFrame(
        columns=["date", "price", "amount", "shares"])
    return {"ledger": ledger, "buys": buys_df}
