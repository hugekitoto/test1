# Volatility Engine (VE) — v0.1

A **direction-neutral volatility-cycle research engine**, independent from any
trend/momentum strategy. VE does not try to find hot stocks or predict price
direction. It asks one question first:

> **Does a repeatable volatility cycle exist?**

If it does, trade locations come from *where you are in the cycle*, not from the
price. This repo implements **Phase 1** of the research design (v0.1): building
the engine and answering that question — **no trading strategy yet**.

---

## The volatility cycle

VE models every asset as moving through four volatility phases:

```
Compression ─▶ Expansion ─▶ Exhaustion ─▶ Recovery ─▶ (back to Compression)
   收縮           擴張          耗盡           恢復
```

Phases are decided from **two volatility axes only** — never price direction:

| water level (HV percentile) ＼ momentum (HV rising/falling) | rising | falling |
| --- | --- | --- |
| **low**  | **Expansion** | **Compression** |
| **high** | **Exhaustion** | **Recovery** |

This is symmetric by construction: an up-shock and a down-shock of equal size
produce the *same* phase. Whether shorts are enabled is a decision for a later
trading layer, not the research layer (design §6).

---

## Architecture

```
data (OHLCV) ─▶ features (volatility) ─▶ phases ─▶ cycles ─▶ report
```

| Module | Role |
| --- | --- |
| `ve/config.py`   | All tunable research parameters (one source of truth). |
| `ve/data.py`     | Canonical OHLCV schema, CSV loader, synthetic sample generator. |
| `ve/features.py` | Volatility features: True Range, ATR, Daily Range, Historical Volatility, HV percentile, vol momentum, distance-from-extreme (design §8). |
| `ve/phases.py`   | Phase classification (with hysteresis + de-speckling) and phase durations. |
| `ve/cycles.py`   | Cycle length, transition matrix, inertia/persistence, canonical-follow rates. |
| `ve/report.py`   | Answers the 8 research questions (design §9) in plain text. |
| `ve/fetch.py`    | *Optional* live data (yfinance / TWSE) — for local use only (see note). |

---

## Quick start

```bash
cd volatility-engine
pip install -r requirements.txt

# 1. generate offline sample data (planted volatility cycles)
python scripts/generate_sample_data.py

# 2. run the Phase-1 research report across all assets
python scripts/run_research.py

# 3. ask a single asset which phase it's in right now
python scripts/current_phase.py data/sample/ETF_0050.csv

# tests (no network needed)
python tests/test_pipeline.py
```

### Using your own data
Drop daily OHLCV CSVs (columns `Date,Open,High,Low,Close,Volume[,Turnover]`,
case-insensitive) into a folder and point the runner at it:

```bash
python scripts/run_research.py --data path/to/your/csvs
```

---

## ⚠️ Data / network note

The hosted (cloud) research environment **blocks outbound access to market-data
providers** (TWSE, Yahoo Finance, FinMind all unreachable). So:

* `ve/fetch.py` will not work in that environment — run it on a normal machine,
  or supply CSVs via `ve.data.load_csv`.
* The bundled **synthetic sample data has a *planted* volatility cycle**, so the
  strong "YES" answers you see out of the box confirm the engine correctly
  *detects a known cycle*. **Real conclusions require real market data.**

---

## Example output (synthetic sample)

Run-to-run transition matrix `P(next | current)` — a clean cycle emerges:

```
             Compression  Expansion  Exhaustion  Recovery
Compression        0.00       0.84        0.14      0.02
Expansion          0.04       0.00        0.96      0.00
Exhaustion         0.13       0.00        0.00      0.87
Recovery           0.77       0.00        0.23      0.00
```

Read the diagonal-shifted structure: each phase overwhelmingly hands off to the
*next* phase in the canonical cycle. On real data, how close this stays to the
canonical pattern is the empirical test of the whole hypothesis.

---

## Mapping to the research design

| Design section | Where it lives |
| --- | --- |
| §2 volatility cycle | `config.PHASES`, `phases.py` |
| §5 time (cycle duration, time since peak, time in compression) | `cycles.cycle_lengths`, `phases.PhaseDuration` / `DaysSinceCompression` |
| §6 direction neutral | phase logic uses volatility only |
| §8 data fields | `features.compute_features` |
| §9 research questions 1–8 | `report.answer_research_questions` |
| §10 "which phase am I in?" | `scripts/current_phase.py` |

---

## Roadmap (per the design)

- **Phase 1 (this repo):** does the cycle exist? → engine + evidence. ✅
- **Phase 2:** if it holds on real data, formalise each phase per asset class.
- **Phase 3:** derive **Build Zone** / **Exit Zone** from the cycle (not hand-set
  prices), enable the trading layer, add cross-market (US ETFs) validation.

VE is designed to stay **independent from momentum/trend strategies** so it can
become a separate Alpha Engine (design §11).
