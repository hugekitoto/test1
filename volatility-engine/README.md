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
| `ve/regimes.py`  | **(Phase 2)** Bull/Bear/Range tagging — *only* to stratify results, never to classify phases. |
| `ve/profile.py`  | **(Phase 2)** Per-phase forward-vol / move / duration profiles + time-consistency across regimes. |
| `ve/zones.py`    | **(Phase 3)** Build Zone / Exit Zone + imbalance direction, derived from the cycle. |
| `ve/backtest.py` | **(Phase 3)** Event-driven backtest of the zones (long-only & long/short) with metrics. |
| `ve/evaluate.py` | **(Phase 3)** Scores the six success criteria (design §11). |
| `ve/plotting.py` | Phase-shaded price, HV cycle, and equity charts (headless PNG). |
| `ve/fetch.py`    | *Optional* live data (yfinance / TWSE) — for local use only (see note). |

---

## Run from a phone (iPhone/iPad) — Google Colab

No local install needed. Open [colab.research.google.com](https://colab.research.google.com)
in Safari, then **File → Open notebook → GitHub**, paste this repo, and open
`volatility-engine/notebooks/VE_Colab.ipynb`. Run the cells top-to-bottom — it
clones the repo, fetches **real Taiwan ETF/stock data** (Colab has internet),
runs the full VE pipeline, and shows the charts inline on your phone.

Direct Colab link (fill the repo/branch in Colab's GitHub tab if the repo is
private, or set a token in the first cell):
`github.com/hugekitoto/test1` → `volatility-engine/notebooks/VE_Colab.ipynb`

## Quick start (desktop)

```bash
cd volatility-engine
pip install -r requirements.txt

# 1. generate offline sample data (planted volatility cycles)
python scripts/generate_sample_data.py

# 2. Phase-1 research report only
python scripts/run_research.py

# 3. FULL run — Phase 1 + 2 + 3, success scorecard, and charts in output/
python scripts/run_full.py

# 4. ask a single asset which phase it's in right now
python scripts/current_phase.py data/sample/ETF_0050.csv

# tests (no network needed)
python tests/test_pipeline.py
```

`run_full.py` writes per-asset charts (`output/<asset>.png`) showing price with
phase shading, the HV cycle, and strategy-vs-buy&hold equity.

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

## Phase 2 — what each phase means

For every asset VE measures, per phase, the **forward** 10-day realised
volatility, the forward move magnitude (direction-neutral), the average
duration, and the canonical-follow rate. The core predictions it checks:

* **Compression** is the *quietest* phase now but has *positive* forward-vol
  change → quiet, about to expand.
* **Exhaustion** is the *loudest* now but *negative* forward-vol change →
  loud, about to cool.

It also recomputes the cycle **within Bull / Bear / Range regimes** to test
time-consistency (§11.3).

## Phase 3 — Build/Exit zones, trading layer, backtest

Zones come from the cycle, not from hand-set prices:

* **Build Zone** = Compression (low, coiling vol). Direction from *imbalance*
  (position-in-range): stretched **down → long**, stretched **up → short**.
* **Exit Zone** = Exhaustion (vol climaxed); also flatten on Recovery or an
  ATR stop.

`backtest.py` runs this long-only and long/short (no look-ahead: decide at
close *t*, hold from *t+1*), reporting return, Sharpe, drawdown, win rate and
long-vs-short breakdown. `evaluate.py` turns it all into a **§11 scorecard**.

### Honest status of the scorecard

On the bundled synthetic sample the engine scores **4 / 6**:

* ✅ 1,2,3,6 — the **volatility cycle** is real, reproducible, regime-consistent
  and independent of trend. This is Phase 1's question, answered YES.
* ⚠️ 4,5 — the **trading layer** (long/short symmetry, net-positive zones) is
  marginal. Two names are strongly profitable and long-side expectancy is
  positive, but shorts lag because the sample assets drift upward. This is the
  design's own last and hardest stage and **must be validated / tuned on real
  data** — the synthetic sample was deliberately *not* over-fitted to force a
  pass.

## Mapping to the research design

| Design section | Where it lives |
| --- | --- |
| §2 volatility cycle | `config.PHASES`, `phases.py` |
| §5 time (cycle duration, time since peak, time in compression) | `cycles.cycle_lengths`, `phases.PhaseDuration` / `DaysSinceCompression` |
| §6 direction neutral | phase logic uses volatility only |
| §8 data fields | `features.compute_features` |
| §9 research questions 1–8 | `report.answer_research_questions` |
| §10 "which phase am I in?" | `scripts/current_phase.py` |
| §11 six success criteria | `evaluate.evaluate` |

---

## Roadmap (per the design)

- **Phase 1:** does the cycle exist? → engine + evidence. ✅
- **Phase 2:** formalise each phase (forward-vol profile) + regime consistency. ✅
- **Phase 3:** Build/Exit zones, trading layer, backtest, §11 scorecard. ✅
  *(framework complete; trading edge to be validated/tuned on real market data)*
- **Next:** feed real Taiwan ETFs / large caps, then stage-2/3 assets
  (mid/small caps, US ETFs) for cross-market confirmation.

VE is **independent from momentum/trend strategies** by design, so it can become
a separate Alpha Engine (design §11).
