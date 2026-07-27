# 資料格式與取得方式

## CSV 格式

每個標的一個檔案：`0050.csv`、`2330.csv`。需要表頭列，欄位（大小寫不拘）：

```
date,open,high,low,close[,adj_close][,volume]
2015-01-05,140.00,141.50,139.00,141.00,120.30,12345678
```

* `date`：`YYYY-MM-DD`。
* `open,high,low,close`：當日 OHLC。
* `adj_close`（**強烈建議**）：**還原**收盤價（已調整除權息 / 分割）。
  * 若提供 `adj_close`，載入器會用 `adj_close/close` 的比例把整根 OHLC 一起換算成
    還原價。**這很重要**：沒有還原，除息當天的跳空下跌會被誤判成假的「黑K」訊號。
  * 若沒有 `adj_close`，直接用 `close`（訊號可能被除權息污染，請自行斟酌）。
* `volume`：選填，回測不使用。

兩個檔案的交易日會自動取交集對齊，並在交集日曆上重算「昨收」。

## 如何取得真實資料（在可連網的機器上）

此沙箱環境**無法連外抓資料**。請在可連網的環境準備好 CSV 後放進本資料夾。常見來源：

* **Yahoo Finance**：代碼 `0050.TW`、`2330.TW`（用 `yfinance` 抓 `Adj Close`）。

  ```python
  import yfinance as yf
  for sym, name in [("0050.TW", "0050"), ("2330.TW", "2330")]:
      df = yf.download(sym, start="2010-01-01", auto_adjust=False)
      df = df.rename(columns=str.lower).reset_index()
      df = df.rename(columns={"index": "date", "adj close": "adj_close"})
      df[["date","open","high","low","close","adj_close","volume"]].to_csv(f"{name}.csv", index=False)
  ```

* **台灣證交所（TWSE）** 個股日成交 API、或 **FinMind**（`TaiwanStockPrice`）。
  注意證交所原始資料為**未還原**價，需另行還原或改用還原資料源。

## 換上真實資料後

1. 覆蓋 `0050.csv`、`2330.csv`。
2. 刪除本資料夾的 `.synthetic` 標記檔（若存在）。
3. `cd research && python run.py`。

報表最上方的「合成資料」警告會自動消失，`results/report.md` 即為真實結論。
