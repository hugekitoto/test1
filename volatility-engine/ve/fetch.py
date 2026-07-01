"""Optional live-data fetcher for VE.

IMPORTANT: the hosted/cloud research environment blocks outbound access to
market-data providers, so this module is a no-op there. Run it on a machine
with normal internet access (or provide CSVs to ve.data.load_csv instead).

Two backends are supported, both lazy-imported so VE never hard-depends on them:
  * yfinance  -> US & many international tickers (e.g. "2330.TW", "SPY")
  * TWSE open API -> Taiwan listed stocks/ETFs by code (e.g. "0050")
"""

from __future__ import annotations

import pandas as pd


def fetch_yfinance(ticker: str, start: str = "2015-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch daily OHLCV via yfinance. Requires `pip install yfinance` + network."""
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("yfinance not installed. `pip install yfinance`.") from e

    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(
            f"No data for {ticker}. In the hosted VE environment outbound market "
            "data is blocked — run this locally or use load_csv()."
        )
    # Newer yfinance returns a MultiIndex column header (field, ticker) even for
    # a single symbol. Flatten to just the field level so the saved CSV has a
    # clean single header row that load_csv() can read.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.index.name = "Date"
    return df.astype(float)


def fetch_twse(stock_no: str, yyyymm: str) -> pd.DataFrame:
    """Fetch one month of a TWSE-listed code via the public STOCK_DAY endpoint.

    yyyymm e.g. "202401". Returns OHLCV+Turnover. Loop months and concat for a
    full history. Requires network access to www.twse.com.tw.
    """
    try:
        import requests
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("requests not installed. `pip install requests`.") from e

    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
    params = {"response": "json", "date": f"{yyyymm}01", "stockNo": stock_no}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get("stat") != "OK":
        raise RuntimeError(f"TWSE returned: {payload.get('stat')} for {stock_no}/{yyyymm}")

    def _num(s: str) -> float:
        return float(s.replace(",", ""))

    rows = []
    for row in payload["data"]:
        # columns: 日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數
        y, m, d = row[0].split("/")
        date = pd.Timestamp(int(y) + 1911, int(m), int(d))  # ROC year -> AD
        rows.append({
            "Date": date, "Volume": _num(row[1]), "Turnover": _num(row[2]),
            "Open": _num(row[3]), "High": _num(row[4]), "Low": _num(row[5]),
            "Close": _num(row[6]),
        })
    df = pd.DataFrame(rows).set_index("Date").sort_index()
    return df[["Open", "High", "Low", "Close", "Volume", "Turnover"]]
