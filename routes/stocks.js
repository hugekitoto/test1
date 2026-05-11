const express = require('express');
const axios = require('axios');
const router = express.Router();

const TWSE_BASE = 'https://www.twse.com.tw';
const MIS_BASE = 'https://mis.twse.com.tw';
const OPENAPI_BASE = 'https://openapi.twse.com.tw';

const axiosConfig = {
  timeout: 10000,
  headers: {
    'User-Agent': 'Mozilla/5.0 (compatible; StockDashboard/1.0)',
    'Accept': 'application/json',
  },
};

// GET /api/stocks/quote/:code
// 取得個股即時報價 (上市用 tse, 上櫃用 otc)
router.get('/quote/:code', async (req, res) => {
  const { code } = req.params;
  const market = req.query.market || 'tse';

  try {
    const url = `${MIS_BASE}/stock/api/getStockInfo.jsp?ex_ch=${market}_${code}.tw&json=1&delay=0`;
    const response = await axios.get(url, axiosConfig);
    const data = response.data;

    if (!data.msgArray || data.msgArray.length === 0) {
      return res.status(404).json({ error: '找不到股票代號' });
    }

    const stock = data.msgArray[0];
    const result = {
      code: stock.c,
      name: stock.n,
      price: parseFloat(stock.z) || parseFloat(stock.y),
      open: parseFloat(stock.o),
      high: parseFloat(stock.h),
      low: parseFloat(stock.l),
      close: parseFloat(stock.y),
      change: parseFloat(stock.z) - parseFloat(stock.y),
      changePercent: (((parseFloat(stock.z) - parseFloat(stock.y)) / parseFloat(stock.y)) * 100).toFixed(2),
      volume: parseInt(stock.v),
      time: stock.t,
      date: stock.d,
    };

    res.json(result);
  } catch (err) {
    res.status(500).json({ error: '無法取得即時報價', detail: err.message });
  }
});

// GET /api/stocks/history/:code
// 取得個股近月歷史資料 (上市)
router.get('/history/:code', async (req, res) => {
  const { code } = req.params;
  const date = req.query.date || formatDate(new Date());

  try {
    const url = `${TWSE_BASE}/rwd/zh/afterTrading/STOCK_DAY?stockNo=${code}&date=${date}&response=json`;
    const response = await axios.get(url, axiosConfig);
    const data = response.data;

    if (data.stat !== 'OK' || !data.data) {
      return res.status(404).json({ error: '無歷史資料' });
    }

    const history = data.data.map(row => ({
      date: row[0].replace(/\//g, '-'),
      open: parseFloat(row[3].replace(/,/g, '')),
      high: parseFloat(row[4].replace(/,/g, '')),
      low: parseFloat(row[5].replace(/,/g, '')),
      close: parseFloat(row[6].replace(/,/g, '')),
      volume: parseInt(row[1].replace(/,/g, '')),
    }));

    res.json({ code, title: data.title, history });
  } catch (err) {
    res.status(500).json({ error: '無法取得歷史資料', detail: err.message });
  }
});

// GET /api/stocks/index
// 取得加權指數
router.get('/index', async (req, res) => {
  try {
    const url = `${MIS_BASE}/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0`;
    const response = await axios.get(url, axiosConfig);
    const data = response.data;

    if (!data.msgArray || data.msgArray.length === 0) {
      return res.status(404).json({ error: '無法取得大盤資料' });
    }

    const idx = data.msgArray[0];
    res.json({
      name: idx.n,
      price: parseFloat(idx.z) || parseFloat(idx.y),
      close: parseFloat(idx.y),
      change: (parseFloat(idx.z) - parseFloat(idx.y)).toFixed(2),
      changePercent: (((parseFloat(idx.z) - parseFloat(idx.y)) / parseFloat(idx.y)) * 100).toFixed(2),
      volume: idx.v,
      time: idx.t,
    });
  } catch (err) {
    res.status(500).json({ error: '無法取得大盤資料', detail: err.message });
  }
});

// GET /api/stocks/search?q=2330
// 從上市股票清單搜尋
router.get('/search', async (req, res) => {
  const { q } = req.query;
  if (!q) return res.status(400).json({ error: '請輸入搜尋關鍵字' });

  try {
    const url = `${OPENAPI_BASE}/v1/exchangeReport/STOCK_DAY_ALL`;
    const response = await axios.get(url, { ...axiosConfig, timeout: 15000 });
    const list = response.data;

    const keyword = q.toLowerCase();
    const results = list
      .filter(s => s.Code.includes(keyword) || s.Name.toLowerCase().includes(keyword))
      .slice(0, 20)
      .map(s => ({ code: s.Code, name: s.Name, close: s.ClosingPrice }));

    res.json(results);
  } catch (err) {
    res.status(500).json({ error: '搜尋失敗', detail: err.message });
  }
});

function formatDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

module.exports = router;
