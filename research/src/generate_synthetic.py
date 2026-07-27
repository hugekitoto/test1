"""
=====================================================================
  SYNTHETIC / ILLUSTRATIVE DATA GENERATOR -- *** NOT REAL PRICES ***
=====================================================================

This module fabricates two correlated daily price series so the whole
backtest pipeline is runnable and reviewable end-to-end **without a live data
feed** (this sandbox's egress policy blocks Yahoo/Stooq/TWSE/FinMind).

The generator hard-codes the two well-documented stylised facts the study
relies on, so the mechanics are exercised realistically:

  * 2330 has a higher long-run drift than 0050 (the study's premise), and
  * 2330 is highly correlated with 0050 (so "0050 black K" is a plausible
    proxy signal for 2330 dips).

Any numbers produced from this data are ILLUSTRATIVE ONLY. To obtain real
research conclusions, replace ``data/0050.csv`` and ``data/2330.csv`` with real
adjusted-price history (see ``data/README.md``) and re-run ``run.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _make_series(dates, seed, mu_annual, vol_annual, market, beta):
    rng = np.random.default_rng(seed)
    n = len(dates)
    mu = mu_annual / 252.0
    idio_vol = vol_annual / np.sqrt(252.0) * np.sqrt(max(1e-6, 1 - beta ** 2))
    idio = rng.normal(0, idio_vol, n)
    ret = mu + beta * market + idio
    close = 100.0 * np.cumprod(1.0 + ret)

    # build a plausible OHLC bar around each close
    prev_close = np.concatenate([[close[0]], close[:-1]])
    gap = rng.normal(0, vol_annual / np.sqrt(252.0) * 0.3, n)
    open_ = prev_close * (1.0 + gap)
    hi_lo = np.abs(rng.normal(0, vol_annual / np.sqrt(252.0) * 0.6, n))
    high = np.maximum(open_, close) * (1.0 + hi_lo)
    low = np.minimum(open_, close) * (1.0 - hi_lo)
    return pd.DataFrame({"date": dates, "open": open_, "high": high,
                         "low": low, "close": close})


def generate(start="2015-01-02", end="2025-07-25", seed=20260727):
    dates = pd.bdate_range(start, end)
    n = len(dates)
    rng = np.random.default_rng(seed)
    # shared market factor drives the cross-correlation between 0050 and 2330
    market = rng.normal(0, 0.011, n)

    etf = _make_series(dates, seed + 1, mu_annual=0.08, vol_annual=0.16,
                       market=market, beta=0.85)
    tsmc = _make_series(dates, seed + 2, mu_annual=0.16, vol_annual=0.26,
                        market=market, beta=0.80)
    return etf, tsmc


def main(out_dir="data"):
    import os
    etf, tsmc = generate()
    os.makedirs(out_dir, exist_ok=True)
    etf.to_csv(os.path.join(out_dir, "0050.csv"), index=False,
               float_format="%.4f")
    tsmc.to_csv(os.path.join(out_dir, "2330.csv"), index=False,
                float_format="%.4f")
    # marker so run.py knows the current CSVs are fabricated, not real
    with open(os.path.join(out_dir, ".synthetic"), "w") as f:
        f.write("Current 0050.csv / 2330.csv are SYNTHETIC illustrative data.\n"
                "Delete this file (and replace the CSVs) when you drop in real prices.\n")
    # correlation sanity check
    r1 = etf["close"].pct_change().dropna()
    r2 = tsmc["close"].pct_change().dropna()
    corr = np.corrcoef(r1, r2)[0, 1]
    print(f"[synthetic] wrote {len(etf)} rows to {out_dir}/0050.csv & 2330.csv")
    print(f"[synthetic] daily-return corr(0050, 2330) = {corr:.2f}")
    print(f"[synthetic] 0050 total return = {etf['close'].iloc[-1]/etf['close'].iloc[0]-1:+.1%}, "
          f"2330 total return = {tsmc['close'].iloc[-1]/tsmc['close'].iloc[0]-1:+.1%}")


if __name__ == "__main__":
    main()
