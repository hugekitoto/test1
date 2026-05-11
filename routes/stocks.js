const express = require('express');
const axios = require('axios');
const router = express.Router();

const MIS_BASE = 'https://mis.twse.com.tw';
const TWSE_BASE = 'https://www.twse.com.tw';
const OPENAPI_BASE = 'https://openapi.twse.com.tw';
const TPEX_BASE = 'https://www.tpex.org.tw';

const ax = {
  timeout: 12000,
  headers: { 'User-Agent': 'Mozilla/5.0 (compatible; StockDashboard/1.0)' },
};

// ── In-memory cache ────────────────────────────────────────
const _cache = {};
function getCache(key) {
  const e = _cache[key];
  return e && Date.now() - e.ts < 5 * 60 * 1000 ? e.data : null;
}
function setCache(key, data) { _cache[key] = { data, ts: Date.now() }; }

// ── Helpers ────────────────────────────────────────────────
function twToISO(twDate) {
  const [y, m, d] = twDate.replace(/\//g, '-').split('-');
  return `${parseInt(y) + 1911}-${m}-${d}`;
}

function todayStr() {
  const n = new Date();
  return `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, '0')}${String(n.getDate()).padStart(2, '0')}`;
}

function twYearMonth() {
  const n = new Date();
  return `${n.getFullYear() - 1911}/${String(n.getMonth() + 1).padStart(2, '0')}`;
}

async function fetchTseList() {
  const cached = getCache('tse_list');
  if (cached) return cached;
  const r = await axios.get(`${OPENAPI_BASE}/v1/exchangeReport/STOCK_DAY_ALL`, { ...ax, timeout: 20000 });
  setCache('tse_list', r.data);
  return r.data;
}

async function fetchOtcList() {
  const cached = getCache('otc_list');
  if (cached) return cached;
  const r = await axios.get(`${TPEX_BASE}/openapi/v1/tpex_mainboard_daily_close_quotes`, { ...ax, timeout: 20000 });
  setCache('otc_list', r.data);
  return r.data;
}

function num(s) { return parseFloat((s || '').toString().replace(/,/g, '')); }

// ── Quote (auto-detect TSE / OTC) ─────────────────────────
router.get('/quote/:code', async (req, res) => {
  const { code } = req.params;

  async function tryMarket(market) {
    const r = await axios.get(
      `${MIS_BASE}/stock/api/getStockInfo.jsp?ex_ch=${market}_${code}.tw&json=1&delay=0`, ax
    );
    return r.data;
  }

  try {
    let data = await tryMarket('tse');
    let market = 'tse';
    if (!data.msgArray?.length) { data = await tryMarket('otc'); market = 'otc'; }
    if (!data.msgArray?.length) return res.status(404).json({ error: '找不到股票代號' });

    const s = data.msgArray[0];
    const price = parseFloat(s.z) || parseFloat(s.y);
    const prev = parseFloat(s.y);
    const chg = parseFloat((price - prev).toFixed(2));

    res.json({
      code: s.c, name: s.n, market,
      price, open: num(s.o), high: num(s.h), low: num(s.l), close: prev,
      change: chg,
      changePercent: ((chg / prev) * 100).toFixed(2),
      volume: parseInt(s.v) || 0,
      time: s.t, date: s.d,
    });
  } catch (e) {
    res.status(500).json({ error: '無法取得即時報價', detail: e.message });
  }
});

// ── History (TSE or OTC) ──────────────────────────────────
router.get('/history/:code', async (req, res) => {
  const { code } = req.params;
  const market = req.query.market || 'tse';

  try {
    if (market === 'otc') {
      const url = `${TPEX_BASE}/web/stock/aftertrading/daily_trading_info/st43_result.php` +
        `?l=zh-tw&d=${twYearMonth()}&stkno=${code}&s=0,asc,0`;
      const r = await axios.get(url, ax);
      const rows = r.data?.aaData || [];
      if (!rows.length) return res.status(404).json({ error: '無歷史資料' });

      const history = rows.map(row => ({
        date: twToISO(row[0]),
        volume: parseInt((row[1] || '0').replace(/,/g, '')),
        open: num(row[3]), high: num(row[4]), low: num(row[5]), close: num(row[6]),
      })).filter(r => !isNaN(r.close) && r.close > 0);

      return res.json({ code, history });
    }

    // TSE
    const url = `${TWSE_BASE}/rwd/zh/afterTrading/STOCK_DAY?stockNo=${code}&date=${todayStr()}&response=json`;
    const r = await axios.get(url, ax);
    const data = r.data;
    if (data.stat !== 'OK' || !data.data) return res.status(404).json({ error: '無歷史資料' });

    const history = data.data.map(row => ({
      date: twToISO(row[0]),
      volume: parseInt((row[1] || '0').replace(/,/g, '')),
      open: num(row[3]), high: num(row[4]), low: num(row[5]), close: num(row[6]),
    })).filter(r => !isNaN(r.close) && r.close > 0);

    res.json({ code, history });
  } catch (e) {
    res.status(500).json({ error: '無法取得歷史資料', detail: e.message });
  }
});

// ── TAIEX Index ───────────────────────────────────────────
router.get('/index', async (req, res) => {
  try {
    const r = await axios.get(`${MIS_BASE}/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0`, ax);
    const idx = r.data?.msgArray?.[0];
    if (!idx) return res.status(404).json({ error: '無法取得大盤資料' });

    const price = parseFloat(idx.z) || parseFloat(idx.y);
    const prev = parseFloat(idx.y);
    const chg = price - prev;

    res.json({
      name: idx.n, price, close: prev,
      change: chg.toFixed(2),
      changePercent: ((chg / prev) * 100).toFixed(2),
      volume: idx.v, time: idx.t,
    });
  } catch (e) {
    res.status(500).json({ error: '無法取得大盤資料', detail: e.message });
  }
});

// ── Search (TSE + OTC) ────────────────────────────────────
router.get('/search', async (req, res) => {
  const { q } = req.query;
  if (!q) return res.status(400).json({ error: '請輸入搜尋關鍵字' });

  try {
    const [tse, otc] = await Promise.allSettled([fetchTseList(), fetchOtcList()]);
    const kw = q.toLowerCase();
    const results = [];

    if (tse.status === 'fulfilled') {
      tse.value
        .filter(s => s.Code?.includes(kw) || s.Name?.toLowerCase().includes(kw))
        .slice(0, 10)
        .forEach(s => results.push({ code: s.Code, name: s.Name, market: 'tse', close: s.ClosingPrice }));
    }

    if (otc.status === 'fulfilled') {
      otc.value
        .filter(s => {
          const code = s.SecuritiesCompanyCode || s.Code || '';
          const name = s.CompanyName || s.Name || '';
          return code.includes(kw) || name.toLowerCase().includes(kw);
        })
        .slice(0, 10)
        .forEach(s => results.push({
          code: s.SecuritiesCompanyCode || s.Code,
          name: s.CompanyName || s.Name,
          market: 'otc',
          close: s.Close || s.ClosingPrice,
        }));
    }

    res.json(results.slice(0, 20));
  } catch (e) {
    res.status(500).json({ error: '搜尋失敗', detail: e.message });
  }
});

// ── Ranking (top gainers / losers) ────────────────────────
router.get('/ranking', async (req, res) => {
  try {
    const [tse, otc] = await Promise.allSettled([fetchTseList(), fetchOtcList()]);
    const stocks = [];

    if (tse.status === 'fulfilled') {
      tse.value.forEach(s => {
        const close = num(s.ClosingPrice);
        const change = num(s.Change);
        if (!isNaN(close) && close > 0 && !isNaN(change)) {
          const prev = close - change;
          stocks.push({
            code: s.Code, name: s.Name, market: 'tse',
            close, change,
            changePercent: prev > 0 ? +((change / prev) * 100).toFixed(2) : 0,
          });
        }
      });
    }

    if (otc.status === 'fulfilled') {
      otc.value.forEach(s => {
        const code = s.SecuritiesCompanyCode || s.Code;
        const name = s.CompanyName || s.Name;
        const close = num(s.Close || s.ClosingPrice);
        const change = num(s.Change || s.PriceChange);
        if (code && !isNaN(close) && close > 0 && !isNaN(change)) {
          const prev = close - change;
          stocks.push({
            code, name, market: 'otc',
            close, change,
            changePercent: prev > 0 ? +((change / prev) * 100).toFixed(2) : 0,
          });
        }
      });
    }

    const sorted = [...stocks].sort((a, b) => b.changePercent - a.changePercent);

    res.json({
      gainers: sorted.slice(0, 10),
      losers: sorted.slice(-10).reverse(),
    });
  } catch (e) {
    res.status(500).json({ error: '無法取得排行資料', detail: e.message });
  }
});

module.exports = router;
