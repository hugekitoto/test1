#!/usr/bin/env python3
"""Generate synthetic sample data with *planted* volatility cycles.

Each asset gets a different cycle length so the research runner can check that
VE recovers the right period per asset. Writes one CSV per asset under
data/sample/. This exists so VE runs end-to-end offline (the hosted environment
blocks live market data).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ve import data  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample")

# (name, planted cycle length in days, base vol, seed) — distinct periods on
# purpose: ETFs slow/smooth, AI & semis fast/violent, high-dividend calm.
SPECS = [
    ("ETF_0050",       140, 0.010, 1),
    ("AI_STOCK",        70, 0.022, 2),
    ("SEMICONDUCTOR",   95, 0.018, 3),
    ("HIGH_DIVIDEND",  180, 0.008, 4),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, cyc, bvol, seed in SPECS:
        df = data.generate_sample(name, n_days=1500, cycle_len=cyc,
                                  base_vol=bvol, seed=seed)
        # drop the hidden ground-truth column before writing (engine must not see it)
        out = df.drop(columns=["_true_vol"])
        path = os.path.join(OUT_DIR, f"{name}.csv")
        out.to_csv(path)
        print(f"wrote {path}  ({len(out)} rows, planted cycle {cyc}d)")


if __name__ == "__main__":
    main()
