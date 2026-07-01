"""Volatility Engine (VE) — a direction-neutral volatility-cycle research engine.

Phase 1 goal (research design v0.1): determine whether a repeatable volatility
cycle exists, before building any trading strategy.

Pipeline:
    data (OHLCV)  ->  features (volatility)  ->  phases  ->  cycles  ->  report

Typical use:
    from ve import data, features, phases, cycles
    df    = data.load_csv("data/sample/ETF_0050.csv")
    feat  = features.compute_features(df)
    ann   = phases.classify_phases(feat)
    stats = cycles.analyse(ann["PhaseSmooth"])
"""

from .config import VEConfig, DEFAULT, PHASES, CANONICAL_CYCLE  # noqa: F401

__all__ = ["VEConfig", "DEFAULT", "PHASES", "CANONICAL_CYCLE"]
__version__ = "0.1.0"
