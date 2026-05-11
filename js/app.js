const API_BASE = '/api/stocks';

// ── State ──────────────────────────────────────────────────
let chartInstance = null;
let chartType = 'candlestick';
let currentStock = null;    // { code, name, market }
let rankingData = null;
let activeTab = 'gainers';
let watchlist = (() => { try { return JSON.parse(localStorage.getItem('tw_watchlist') || '[]'); } catch { return []; } })();

// ── Index ──────────────────────────────────────────────────
async function loadIndex() {
  try {
    const d = await fetch(`${API_BASE}/index`).then(r => r.json());
    if (d.error) return;

    const chg = parseFloat(d.change);
    const pct = parseFloat(d.changePercent);
    const isUp = chg >= 0;

    document.getElementById('taiex-price').textContent =
      parseFloat(d.price).toLocaleString('zh-TW', { minimumFractionDigits: 2 });

    const el = document.getElementById('taiex-change');
    el.textContent = `${isUp ? '▲' : '▼'} ${Math.abs(chg).toFixed(2)} (${isUp ? '+' : ''}${pct}%)`;
    el.className = `index-change ${isUp ? 'up' : 'down'}`;

    document.getElementById('taiex-meta').textContent = `更新：${d.time}`;
    document.getElementById('taiex-card').className = `index-card ${isUp ? 'up' : 'down'}`;
  } catch {
    document.getElementById('taiex-meta').textContent = '無法取得大盤資料';
  }
  document.getElementById('market-time').textContent = new Date().toLocaleTimeString('zh-TW');
}

// ── Search ─────────────────────────────────────────────────
async function doSearch(query) {
  query = query.trim();
  if (!query) return;

  const resEl = document.getElementById('search-results');

  if (/^\d{4,6}$/.test(query)) {
    resEl.classList.add('hidden');
    await loadStock(query);
    return;
  }

  resEl.innerHTML = '<div class="search-loading">搜尋中...</div>';
  resEl.classList.remove('hidden');

  try {
    const list = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`).then(r => r.json());
    if (!list.length) { resEl.innerHTML = '<div class="search-empty">找不到股票</div>'; return; }

    resEl.innerHTML = list.map(s =>
      `<div class="search-item" data-code="${s.code}" data-market="${s.market}">
        <span class="si-code">${s.code}</span>
        <span class="si-name">${s.name}</span>
        <span class="si-market ${s.market}">${s.market === 'tse' ? '上市' : '上櫃'}</span>
        <span class="si-price">${s.close || '--'}</span>
      </div>`
    ).join('');

    resEl.querySelectorAll('.search-item').forEach(el =>
      el.addEventListener('click', () => {
        resEl.classList.add('hidden');
        document.getElementById('search-input').value = el.dataset.code;
        loadStock(el.dataset.code, el.dataset.market);
      })
    );
  } catch {
    resEl.innerHTML = '<div class="search-empty">搜尋失敗，請稍後重試</div>';
  }
}

// ── Load stock ─────────────────────────────────────────────
async function loadStock(code, market = null) {
  const section = document.getElementById('stock-section');
  section.classList.remove('hidden');
  document.getElementById('stock-price').textContent = '載入中...';
  document.getElementById('stock-change').textContent = '';

  destroyChart();

  try {
    const url = market ? `${API_BASE}/quote/${code}?market=${market}` : `${API_BASE}/quote/${code}`;
    const quote = await fetch(url).then(r => r.json());
    if (quote.error) { document.getElementById('stock-price').textContent = quote.error; return; }

    currentStock = { code: quote.code, name: quote.name, market: quote.market };
    renderQuote(quote);
    updateWatchlistBtn();
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    const hist = await fetch(`${API_BASE}/history/${code}?market=${quote.market}`).then(r => r.json());
    if (!hist.error && hist.history?.length) renderChart(hist.history);
  } catch {
    document.getElementById('stock-price').textContent = '查詢失敗';
  }
}

function renderQuote(q) {
  const chg = parseFloat(q.change);
  const pct = parseFloat(q.changePercent);
  const isUp = chg >= 0;

  document.getElementById('stock-name').textContent = q.name;
  document.getElementById('stock-code-badge').textContent = q.code;

  const mBadge = document.getElementById('stock-market-badge');
  mBadge.textContent = q.market === 'tse' ? '上市' : '上櫃';
  mBadge.className = `badge badge-market ${q.market}`;

  const priceEl = document.getElementById('stock-price');
  priceEl.textContent = q.price?.toFixed(2);
  priceEl.className = `stock-price ${isUp ? 'up' : 'down'}`;

  const chgEl = document.getElementById('stock-change');
  chgEl.textContent = `${isUp ? '▲' : '▼'} ${Math.abs(chg).toFixed(2)} (${isUp ? '+' : ''}${pct}%)`;
  chgEl.className = `stock-change ${isUp ? 'up' : 'down'}`;

  document.getElementById('m-open').textContent = q.open?.toFixed(2) ?? '--';
  document.getElementById('m-high').textContent = q.high?.toFixed(2) ?? '--';
  document.getElementById('m-low').textContent = q.low?.toFixed(2) ?? '--';
  document.getElementById('m-close').textContent = q.close?.toFixed(2) ?? '--';
  document.getElementById('m-volume').textContent = q.volume?.toLocaleString() ?? '--';
  document.getElementById('m-time').textContent = q.time ?? '--';
}

// ── Chart ──────────────────────────────────────────────────
function destroyChart() {
  if (chartInstance) { chartInstance.remove(); chartInstance = null; }
}

function renderChart(history) {
  destroyChart();
  const container = document.getElementById('price-chart');

  chartInstance = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 340,
    layout: { background: { color: '#0f1117' }, textColor: '#718096' },
    grid: { vertLines: { color: '#1e2230' }, horzLines: { color: '#1e2230' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#2d3748' },
    timeScale: { borderColor: '#2d3748' },
  });

  const data = history.map(d => ({
    time: d.date, open: d.open, high: d.high, low: d.low, close: d.close,
  }));

  if (chartType === 'candlestick') {
    const s = chartInstance.addCandlestickSeries({
      upColor: '#e53e3e', downColor: '#38a169',
      borderVisible: false,
      wickUpColor: '#e53e3e', wickDownColor: '#38a169',
    });
    s.setData(data);
  } else {
    const s = chartInstance.addAreaSeries({
      lineColor: '#4a90d9',
      topColor: 'rgba(74,144,217,0.25)',
      bottomColor: 'rgba(74,144,217,0)',
      lineWidth: 2,
    });
    s.setData(data.map(d => ({ time: d.time, value: d.close })));
  }

  chartInstance.timeScale().fitContent();

  new ResizeObserver(() => {
    if (chartInstance) chartInstance.applyOptions({ width: container.clientWidth });
  }).observe(container);
}

// ── Watchlist ──────────────────────────────────────────────
function saveWatchlist() { localStorage.setItem('tw_watchlist', JSON.stringify(watchlist)); }
const inWatchlist = code => watchlist.some(s => s.code === code);

function updateWatchlistBtn() {
  const btn = document.getElementById('watchlist-btn');
  if (currentStock && inWatchlist(currentStock.code)) {
    btn.textContent = '★ 已加入自選';
    btn.classList.add('active');
  } else {
    btn.textContent = '☆ 加入自選';
    btn.classList.remove('active');
  }
}

function toggleWatchlist() {
  if (!currentStock) return;
  if (inWatchlist(currentStock.code)) {
    watchlist = watchlist.filter(s => s.code !== currentStock.code);
  } else {
    watchlist.push({ ...currentStock });
  }
  saveWatchlist();
  updateWatchlistBtn();
  renderWatchlist();
}

function renderWatchlist() {
  const el = document.getElementById('watchlist-list');
  if (!watchlist.length) {
    el.innerHTML = '<p class="empty-hint">查詢股票後點「☆ 加入自選」即可儲存</p>';
    return;
  }

  el.innerHTML = watchlist.map(s =>
    `<div class="wi">
      <div class="wi-info" data-code="${s.code}" data-market="${s.market}">
        <span class="wi-code">${s.code}</span>
        <span class="wi-name">${s.name}</span>
        <span class="wi-market ${s.market}">${s.market === 'tse' ? '上市' : '上櫃'}</span>
      </div>
      <button class="wi-remove" data-code="${s.code}" title="移除">×</button>
    </div>`
  ).join('');

  el.querySelectorAll('.wi-info').forEach(e =>
    e.addEventListener('click', () => loadStock(e.dataset.code, e.dataset.market))
  );
  el.querySelectorAll('.wi-remove').forEach(btn =>
    btn.addEventListener('click', ev => {
      ev.stopPropagation();
      watchlist = watchlist.filter(s => s.code !== btn.dataset.code);
      saveWatchlist();
      updateWatchlistBtn();
      renderWatchlist();
    })
  );
}

// ── Ranking ────────────────────────────────────────────────
async function loadRanking() {
  const el = document.getElementById('ranking-list');
  el.innerHTML = '<div class="rank-loading">載入排行資料中（首次約需 10–20 秒）...</div>';

  try {
    const data = await fetch(`${API_BASE}/ranking`).then(r => r.json());
    if (data.error) { el.innerHTML = `<div class="rank-loading">${data.error}</div>`; return; }
    rankingData = data;
    renderRanking(activeTab);
  } catch {
    el.innerHTML = '<div class="rank-loading">無法載入排行資料</div>';
  }
}

function renderRanking(tab) {
  activeTab = tab;
  if (!rankingData) return;

  const list = tab === 'gainers' ? rankingData.gainers : rankingData.losers;
  const el = document.getElementById('ranking-list');

  if (!list?.length) { el.innerHTML = '<div class="rank-loading">無資料</div>'; return; }

  el.innerHTML = `
    <table class="rank-table">
      <thead><tr><th>#</th><th>代號</th><th>名稱</th><th>市場</th><th>收盤</th><th>漲跌幅</th><th>漲跌</th></tr></thead>
      <tbody>
        ${list.map((s, i) => {
          const isUp = s.change >= 0;
          const cls = isUp ? 'up' : 'down';
          return `<tr class="rank-row" data-code="${s.code}" data-market="${s.market}">
            <td class="rank-num">${i + 1}</td>
            <td class="rank-code">${s.code}</td>
            <td>${s.name}</td>
            <td><span class="badge-market ${s.market}">${s.market === 'tse' ? '上市' : '上櫃'}</span></td>
            <td>${s.close?.toFixed(2)}</td>
            <td class="${cls}">${isUp ? '+' : ''}${s.changePercent}%</td>
            <td class="${cls}">${isUp ? '+' : ''}${s.change?.toFixed(2)}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;

  el.querySelectorAll('.rank-row').forEach(row =>
    row.addEventListener('click', () => {
      document.getElementById('search-input').value = row.dataset.code;
      loadStock(row.dataset.code, row.dataset.market);
    })
  );
}

// ── Events ─────────────────────────────────────────────────
document.getElementById('search-btn').addEventListener('click', () =>
  doSearch(document.getElementById('search-input').value)
);
document.getElementById('search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch(e.target.value);
});
document.addEventListener('click', e => {
  if (!e.target.closest('.search-section'))
    document.getElementById('search-results').classList.add('hidden');
});

document.getElementById('watchlist-btn').addEventListener('click', toggleWatchlist);

document.querySelectorAll('.chart-toggle-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    document.querySelectorAll('.chart-toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    chartType = btn.dataset.type;
    if (currentStock) {
      fetch(`${API_BASE}/history/${currentStock.code}?market=${currentStock.market}`)
        .then(r => r.json())
        .then(d => { if (!d.error && d.history?.length) renderChart(d.history); });
    }
  })
);

document.querySelectorAll('.rtab').forEach(tab =>
  tab.addEventListener('click', () => {
    document.querySelectorAll('.rtab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    renderRanking(tab.dataset.tab);
  })
);

document.getElementById('ranking-refresh').addEventListener('click', loadRanking);

document.querySelectorAll('.qp-btn').forEach(btn =>
  btn.addEventListener('click', () => {
    document.getElementById('search-input').value = btn.dataset.code;
    loadStock(btn.dataset.code);
  })
);

// ── Init ───────────────────────────────────────────────────
loadIndex();
renderWatchlist();
loadRanking();
setInterval(() => {
  document.getElementById('market-time').textContent = new Date().toLocaleTimeString('zh-TW');
}, 1000);
setInterval(loadIndex, 60000);
