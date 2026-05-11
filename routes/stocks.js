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

// ── Cache ──────────────────────────────────────────────────
const _cache = {};
function getCache(key) {
  const e = _cache[key];
  return e && Date.now() - e.ts < 5 * 60 * 1000 ? e.data : null;
}
function setCache(key, data) { _cache[key] = { data, ts: Date.now() }; }

// ── Date helpers ───────────────────────────────────────────
function twToISO(twDate) {
  const [y, m, d] = twDate.replace(/\//g, '-').split('-');
  return `${parseInt(y) + 1911}-${m}-${d}`;
}

function todayStr() {
  const n = new Date();
  return `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, '0')}${String(n.getDate()).padStart(2, '0')}`;
}

function prevMonthStr() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}01`;
}

function dateToTwYM(yyyymm) {
  const y = parseInt(yyyymm.slice(0, 4)) - 1911;
  const m = yyyymm.slice(4, 6);
  return `${y}/${m}`;
}

function num(s) { return parseFloat((s || '').toString().replace(/,/g, '')); }

// ── Stock list fetchers (cached) ───────────────────────────
async function fetchTseList() {
  const c = getCache('tse_list'); if (c) return c;
  const r = await axios.get(`${OPENAPI_BASE}/v1/exchangeReport/STOCK_DAY_ALL`, { ...ax, timeout: 20000 });
  setCache('tse_list', r.data); return r.data;
}

async function fetchOtcList() {
  const c = getCache('otc_list'); if (c) return c;
  const r = await axios.get(`${TPEX_BASE}/openapi/v1/tpex_mainboard_daily_close_quotes`, { ...ax, timeout: 20000 });
  setCache('otc_list', r.data); return r.data;
}

// ── Shared history fetcher ─────────────────────────────────
async function fetchHistData(code, market, yyyymmdd) {
  if (market === 'otc') {
    const twYM = dateToTwYM(yyyymmdd);
    const url = `${TPEX_BASE}/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d=${twYM}&stkno=${code}&s=0,asc,0`;
    const r = await axios.get(url, ax);
    return (r.data?.aaData || []).map(row => ({
      date: twToISO(row[0]),
      volume: parseInt((row[1] || '0').replace(/,/g, '')),
      open: num(row[3]), high: num(row[4]), low: num(row[5]), close: num(row[6]),
    })).filter(d => !isNaN(d.close) && d.close > 0);
  }

  const url = `${TWSE_BASE}/rwd/zh/afterTrading/STOCK_DAY?stockNo=${code}&date=${yyyymmdd}&response=json`;
  const r = await axios.get(url, ax);
  if (r.data.stat !== 'OK' || !r.data.data) return [];
  return r.data.data.map(row => ({
    date: twToISO(row[0]),
    volume: parseInt((row[1] || '0').replace(/,/g, '')),
    open: num(row[3]), high: num(row[4]), low: num(row[5]), close: num(row[6]),
  })).filter(d => !isNaN(d.close) && d.close > 0);
}

async function fetchTwoMonths(code, market) {
  const [curr, prev] = await Promise.allSettled([
    fetchHistData(code, market, todayStr()),
    fetchHistData(code, market, prevMonthStr()),
  ]);
  const rows = [
    ...(prev.status === 'fulfilled' ? prev.value : []),
    ...(curr.status === 'fulfilled' ? curr.value : []),
  ];
  // Deduplicate and sort
  const seen = new Set();
  return rows
    .filter(d => { if (seen.has(d.date)) return false; seen.add(d.date); return true; })
    .sort((a, b) => a.date.localeCompare(b.date));
}

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
      change: chg, changePercent: ((chg / prev) * 100).toFixed(2),
      volume: parseInt(s.v) || 0, time: s.t, date: s.d,
    });
  } catch (e) {
    res.status(500).json({ error: '無法取得即時報價', detail: e.message });
  }
});

// ── History (supports ?months=1|2) ────────────────────────
router.get('/history/:code', async (req, res) => {
  const { code } = req.params;
  const market = req.query.market || 'tse';
  const months = parseInt(req.query.months) || 1;

  try {
    const history = months >= 2
      ? await fetchTwoMonths(code, market)
      : await fetchHistData(code, market, todayStr());

    if (!history.length) return res.status(404).json({ error: '無歷史資料' });
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
      change: chg.toFixed(2), changePercent: ((chg / prev) * 100).toFixed(2),
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

// ── Ranking ───────────────────────────────────────────────
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
            code: s.Code, name: s.Name, market: 'tse', close, change,
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
            code, name, market: 'otc', close, change,
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

// ── Alert Check ───────────────────────────────────────────
// GET /api/stocks/alert-check/:code?market=tse|otc
// Returns: { code, price, ma20, above }
router.get('/alert-check/:code', async (req, res) => {
  const { code } = req.params;
  const market = req.query.market || 'tse';

  try {
    const [histResult, quoteResult] = await Promise.allSettled([
      fetchTwoMonths(code, market),
      (async () => {
        const r = await axios.get(
          `${MIS_BASE}/stock/api/getStockInfo.jsp?ex_ch=${market}_${code}.tw&json=1&delay=0`, ax
        );
        const s = r.data?.msgArray?.[0];
        if (!s) throw new Error('no data');
        return parseFloat(s.z) || parseFloat(s.y);
      })(),
    ]);

    if (quoteResult.status !== 'fulfilled') {
      return res.status(500).json({ error: '無法取得即時報價' });
    }

    const price = quoteResult.value;
    let ma20 = null;

    if (histResult.status === 'fulfilled' && histResult.value.length >= 20) {
      const last20 = histResult.value.slice(-20);
      ma20 = parseFloat((last20.reduce((s, d) => s + d.close, 0) / 20).toFixed(2));
    }

    res.json({
      code,
      price,
      ma20,
      above: ma20 !== null ? price > ma20 : null,
    });
  } catch (e) {
    res.status(500).json({ error: '警報檢查失敗', detail: e.message });
  }
});

module.exports = router;
