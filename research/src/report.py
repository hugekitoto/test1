"""Assemble the results table and a narrative report answering H1-H3 / Q1-Q3."""

from __future__ import annotations

import pandas as pd

PCT = {"CAGR (on contrib)", "IRR (money-weighted)", "Cash Drag Ratio",
       "MDD", "Volatility (ann.)"}
MONEY = {"Final Assets", "Total Contributed", "Total Deployed", "End Idle Cash",
         "Avg Idle Cash", "Max Idle Cash"}
PRICE = {"Avg Buy Cost", "Avg Exec Price"}


def _fmt(metric, v):
    if v != v:            # NaN
        return "-"
    if metric in PCT:
        return f"{v:+.2%}" if metric in {"CAGR (on contrib)", "IRR (money-weighted)"} else f"{v:.2%}"
    if metric in MONEY:
        return f"{v:,.0f}"
    if metric in PRICE:
        return f"{v:,.2f}"
    if metric in {"Avg Buys/Month", "Avg Wait (trading days)"}:
        return f"{v:.2f}"
    return f"{v:g}"


def summary_table(results: dict, labels: dict) -> pd.DataFrame:
    df = pd.DataFrame(results).T
    df.insert(0, "Description", [labels[k] for k in df.index])
    return df


def to_markdown(results: dict, labels: dict, synthetic: bool,
                data_note: str) -> str:
    order = list(results.keys())
    metrics = list(next(iter(results.values())).keys())

    lines = []
    lines.append("# 研究結果：0050 黑K 作為 2330 定期定額進場訊號\n")
    if synthetic:
        lines.append("> ⚠️ **本報告使用合成(SYNTHETIC)示範資料，非真實股價。**\n"
                     "> 數字僅用於驗證回測流程與報表格式，**不可作為投資結論**。\n"
                     "> 請以真實還原股價替換 `data/0050.csv`、`data/2330.csv` 後重跑 `run.py`。\n")
    lines.append(f"_資料期間 / 來源：{data_note}_\n")

    # ---- main results table (metrics as rows, strategies as columns) ----
    lines.append("## 一、完整指標表\n")
    header = "| 指標 | " + " | ".join(order) + " |"
    sep = "|" + "---|" * (len(order) + 1)
    lines.append(header)
    lines.append(sep)
    for m in metrics:
        row = "| " + m + " | " + " | ".join(_fmt(m, results[k][m]) for k in order) + " |"
        lines.append(row)
    lines.append("")

    # ---- ranked leaderboards ----
    def rank(metric, reverse=True):
        vals = [(k, results[k][metric]) for k in order if results[k][metric] == results[k][metric]]
        return sorted(vals, key=lambda x: x[1], reverse=reverse)

    lines.append("## 二、排名\n")
    lines.append("**依 Final Assets（最終資產）排名：**\n")
    for i, (k, v) in enumerate(rank("Final Assets"), 1):
        lines.append(f"{i}. `{k}` — {v:,.0f}  ({labels[k]})")
    lines.append("\n**依 IRR（money-weighted）排名：**\n")
    for i, (k, v) in enumerate(rank("IRR (money-weighted)"), 1):
        lines.append(f"{i}. `{k}` — {v:+.2%}")
    lines.append("\n**依 平均買進成本（越低越好）排名：**\n")
    for i, (k, v) in enumerate(rank("Avg Buy Cost", reverse=False), 1):
        lines.append(f"{i}. `{k}` — {v:,.2f}")
    lines.append("")

    # ---- hypothesis tests, computed from the numbers ----
    C = results["C_0050_blackk"]
    B = results["B_spread_10"]
    A = results["A_monthly_lump"]
    E = results["E_2330_blackk"]
    D = results["D_0050_down1pct"]

    lines.append("## 三、假設檢定與核心問題\n")

    # H1 / Q1
    h1 = C["Avg Buy Cost"] < B["Avg Buy Cost"]
    lines.append("### H1 / Q1 — 0050 黑K 是否降低 2330 平均買進成本？\n")
    lines.append(f"- 策略 C（0050 黑K）平均買進成本：**{C['Avg Buy Cost']:,.2f}**")
    lines.append(f"- 基準 B（不看漲跌、平均分散）平均買進成本：**{B['Avg Buy Cost']:,.2f}**")
    diff = (C["Avg Buy Cost"] / B["Avg Buy Cost"] - 1)
    lines.append(f"- 差異：**{diff:+.2%}** → **{'支持 H1（成本較低）' if h1 else '不支持 H1（成本未降低）'}**\n")

    # H2 / Q2
    h2 = C["Final Assets"] >= B["Final Assets"]
    lines.append("### H2 / Q2 — 成本優勢是否大於 Cash Drag（現金閒置成本）？\n")
    lines.append(f"- C 平均閒置現金：**{C['Avg Idle Cash']:,.0f}**，最大閒置現金：**{C['Max Idle Cash']:,.0f}**，"
                 f"Cash Drag Ratio：**{C['Cash Drag Ratio']:.2%}**")
    lines.append(f"- C 最終資產：**{C['Final Assets']:,.0f}**　vs　B 最終資產：**{B['Final Assets']:,.0f}**")
    net = (C["Final Assets"] / B["Final Assets"] - 1)
    lines.append(f"- 淨效果（C 相對 B）：**{net:+.2%}** → "
                 f"**{'成本優勢勝過 Cash Drag' if h2 else 'Cash Drag 抵銷了成本優勢'}**\n")

    # H3 / Q3
    lines.append("### H3 / Q3（核心）— 0050 是否能作為 2330 有效的 Timing Signal？\n")
    lines.append(f"- 用 0050 訊號 (C) 最終資產 **{C['Final Assets']:,.0f}** / IRR **{C['IRR (money-weighted)']:+.2%}**")
    lines.append(f"- 用 2330 自己訊號 (E) 最終資產 **{E['Final Assets']:,.0f}** / IRR **{E['IRR (money-weighted)']:+.2%}**")
    lines.append(f"- 不看漲跌 (B) 最終資產 **{B['Final Assets']:,.0f}** / IRR **{B['IRR (money-weighted)']:+.2%}**")
    lines.append(f"- 每月一次 (A) 最終資產 **{A['Final Assets']:,.0f}** / IRR **{A['IRR (money-weighted)']:+.2%}**")
    beats_b = C["Final Assets"] >= B["Final Assets"]
    beats_e = C["Final Assets"] >= E["Final Assets"]
    verdict = ("0050 黑K 為有效訊號（同時勝過不擇時 B 與自身訊號 E）" if beats_b and beats_e
               else "0050 黑K 相對不擇時有優勢，但未明顯優於 2330 自身訊號" if beats_b
               else "0050 黑K 未展現優於不擇時買進的擇時能力")
    lines.append(f"- 判定：**{verdict}**\n")

    lines.append("> 指標定義與方法學細節見 `research/README.md`。\n")
    return "\n".join(lines)
