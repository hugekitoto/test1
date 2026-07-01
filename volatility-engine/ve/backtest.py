"""VE Phase 3 — event-driven backtest of the cycle-derived zones.

Rules (all from the volatility cycle, no hand-set prices):
  * ENTER in the Build Zone (Compression) in the imbalance direction.
  * EXIT in the Exit Zone (Exhaustion), when the cycle rolls to Recovery, or on
    an ATR-based protective stop.

Decisions are made on bar t's close and executed as a held position from t+1
(via position.shift(1)) so there is no look-ahead. Supports long-only and
long/short so we can test directional symmetry (§11.4).

This is a research backtest (single-name, full-notional, simple costs). It
measures whether the *cycle* carries an edge, not a production trading system.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .config import VEConfig, DEFAULT


def run_backtest(zoned: pd.DataFrame, cfg: VEConfig = DEFAULT, *,
                 long_short: bool = True, atr_stop: float = 3.0,
                 cost_bps: float = 5.0) -> Dict[str, object]:
    """Backtest the zone signals on one asset. Returns metrics + artifacts."""
    idx = zoned.index
    close = zoned["Close"].to_numpy(dtype=float)
    atr = zoned["ATR"].to_numpy(dtype=float)
    phase = zoned["PhaseSmooth"].to_numpy(dtype=object)
    in_build = zoned["InBuildZone"].to_numpy()
    in_exit = zoned["InExitZone"].to_numpy()
    bdir = zoned["BuildDir"].to_numpy(dtype=float)

    n = len(idx)
    position = np.zeros(n)
    trades = []
    pos, entry_price, entry_i = 0.0, None, None

    for i in range(n):
        if not isinstance(phase[i], str):  # warmup / NaN
            position[i] = 0.0
            continue
        if pos == 0.0:
            if in_build[i] and bdir[i] != 0.0:
                d = bdir[i]
                if long_short or d > 0:
                    pos, entry_price, entry_i = d, close[i], i
        else:
            stop_hit = False
            if atr_stop and entry_i is not None and atr[entry_i] > 0:
                adverse = (close[i] - entry_price) * pos
                if adverse < -atr_stop * atr[entry_i]:
                    stop_hit = True
            if in_exit[i] or phase[i] == "Recovery" or stop_hit:
                ret = pos * (close[i] - entry_price) / entry_price
                trades.append({
                    "dir": int(pos), "entry": idx[entry_i], "exit": idx[i],
                    "hold": i - entry_i, "ret": ret,
                    "reason": "stop" if stop_hit else "zone",
                })
                pos, entry_price, entry_i = 0.0, None, None
        position[i] = pos

    position = pd.Series(position, index=idx)
    asset_ret = zoned["Close"].pct_change().fillna(0.0)
    held = position.shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * (cost_bps / 1e4)
    strat_ret = held * asset_ret - cost
    equity = (1 + strat_ret).cumprod()

    metrics = _metrics(strat_ret, equity, trades, asset_ret)
    return {
        "metrics": metrics,
        "trades": pd.DataFrame(trades),
        "equity": equity,
        "position": position,
        "strat_ret": strat_ret,
    }


def _metrics(strat_ret: pd.Series, equity: pd.Series, trades: list,
             asset_ret: pd.Series) -> dict:
    td = DEFAULT.trading_days
    n_years = max(len(strat_ret) / td, 1e-9)
    total_ret = float(equity.iloc[-1] - 1) if len(equity) else 0.0
    cagr = float(equity.iloc[-1] ** (1 / n_years) - 1) if len(equity) and equity.iloc[-1] > 0 else float("nan")
    vol = float(strat_ret.std() * np.sqrt(td))
    sharpe = float(strat_ret.mean() / strat_ret.std() * np.sqrt(td)) if strat_ret.std() > 0 else float("nan")
    dd = float((equity / equity.cummax() - 1).min()) if len(equity) else float("nan")

    tdf = pd.DataFrame(trades)
    if len(tdf):
        wins = tdf["ret"] > 0
        win_rate = float(wins.mean())
        gross_win = tdf.loc[wins, "ret"].sum()
        gross_loss = -tdf.loc[~wins, "ret"].sum()
        profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
        avg_hold = float(tdf["hold"].mean())
        n_long = int((tdf["dir"] > 0).sum())
        n_short = int((tdf["dir"] < 0).sum())
        long_ret = float(tdf.loc[tdf["dir"] > 0, "ret"].mean()) if n_long else float("nan")
        short_ret = float(tdf.loc[tdf["dir"] < 0, "ret"].mean()) if n_short else float("nan")
    else:
        win_rate = profit_factor = avg_hold = float("nan")
        n_long = n_short = 0
        long_ret = short_ret = float("nan")

    # buy & hold benchmark
    bh = float((1 + asset_ret).prod() - 1)

    return {
        "n_trades": len(tdf), "win_rate": win_rate, "profit_factor": profit_factor,
        "total_return": total_ret, "cagr": cagr, "ann_vol": vol, "sharpe": sharpe,
        "max_drawdown": dd, "avg_hold_days": avg_hold,
        "n_long": n_long, "n_short": n_short,
        "avg_long_ret": long_ret, "avg_short_ret": short_ret,
        "buy_hold_return": bh,
    }
