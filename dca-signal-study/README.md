# 0050 黑 K → 台積電(2330) 定期定額擇時研究

Does using **0050 down days (black-K)** as an entry signal improve a
dollar-cost-averaging plan into **2330 (TSMC)** — after paying for cash drag?

This is **not** a low-point predictor and **not** an optimiser. It answers one
practical question for an investor who has *already decided* to hold TSMC
long-term: with a fixed monthly budget and no knowledge of the future, does
timing entries on market pullbacks beat plain DCA?

## Rules (Strategy G1)

- Buy target **2330**; signal from **0050**.
- Signal: `today close < yesterday close` (0050 black-K).
- Execution: **next day's open** (no look-ahead).
- **5,000** per buy; **50,000**/month budget; unused budget **carries forward,
  no cap** (July spends 30k → August pool = 70k).
- No signal all month → buy nothing, keep the cash.

## Benchmarks

| | strategy |
| --- | --- |
| A | monthly lump — deploy 50,000 once a month |
| B | spread — 10 × 5,000 over the first 10 trading days, ignore price |
| **C** | **0050 black-K → buy 2330** (the study strategy) |
| D | 0050 down ≥ 1% → buy |
| E | 2330's own black-K → buy |
| G2 / G3 | 0050 down 2 / 3 consecutive days |
| G5 | 0050 below its 20-day MA |
| G6 | 0050 black-K **and** 2330 black-K |

*(G4 = D. G7 needs a "Freshness" definition and is not yet implemented.)*

## Metrics

Performance (Final Assets, CAGR, money-weighted **IRR**), cost (average buy
cost), cash efficiency (avg / max idle cash — the Cash Drag), trade stats
(#buys, buys/month, avg wait days), risk (MDD, volatility). Final Assets always
include leftover cash, and IRR treats 50,000/month as *committed* capital, so
idle cash is properly penalised.

## Core questions

- **Q1** Does black-K actually lower the average buy cost?
- **Q2** Does cash drag cancel any cost advantage?
- **Q3** Is 0050 a useful timing signal for 2330 (vs A/B, and vs 2330's own)?

## Run it

**Phone / Colab (recommended — has network for real data):** open
`dca-signal-study/notebooks/DCA_Colab.ipynb` from GitHub in
[Colab](https://colab.research.google.com) and run top to bottom. It fetches
0050 + 2330 and prints the comparison table + Q1–Q3 answers.

**Local / desktop:**

```bash
cd dca-signal-study
pip install pandas numpy
python scripts/run_dca.py                                   # offline synthetic demo
python scripts/run_dca.py --signal data/0050.csv --target data/2330.csv   # real CSVs
python tests/test_dca.py
```

CSVs need `Date, Open, Close` (case-insensitive). The hosted research
environment blocks market data, so real data must come from Colab or your own
files; the synthetic demo lets the code run anywhere.

## A note on interpretation

On a pure rising series, waiting for dips can only *hurt* (cash sits idle in an
up-market → cash drag), and demanding *bigger* dips (D/G3) hurts more. Any real
edge must come from genuine short-term mean-reversion in the actual data — which
is exactly what running this on real 0050/2330 tests.
