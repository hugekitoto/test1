const API_BASE = '/api/stocks';
let priceChart = null;
let currentCode = null;

// ── 大盤指數 ──────────────────────────────────────────────
async function loadIndex() {
  try {
    const res = await fetch(`${API_BASE}/index`);
    const data = await res.json();
    if (data.error) return;

    const price = data.price.toLocaleString('zh-TW', { minimumFractionDigits: 2 });
    const change = parseFloat(data.change);
    const pct = parseFloat(data.changePercent);

    document.getElementById('taiex-price').textContent = price;
    const changeEl = document.getElementById('taiex-change');
    changeEl.textContent = `${change >= 0 ? '+' : ''}${change} (${pct >= 0 ? '+' : ''}${pct}%)`;
    changeEl.className = `index-change ${change >= 0 ? 'up' : 'down'}`;

    document.getElementById('taiex-meta').textContent = `更新時間：${data.time}`;
    document.getElementById('taiex-card').className = `index-card ${change >= 0 ? 'up' : 'down'}`;
  } catch (e) {
    document.getElementById('taiex-meta').textContent = '無法取得大盤資料';
  }

  updateClock();
}

function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  document.getElementById('market-time').textContent = timeStr;
}

// ── 搜尋 ──────────────────────────────────────────────────
async function search(query) {
  if (!query.trim()) return;

  const resultsEl = document.getElementById('search-results');
  resultsEl.innerHTML = '<div class="search-loading">搜尋中...</div>';
  resultsEl.classList.remove('hidden');

  // If it's a pure number code, query directly
  if (/^\d{4,6}$/.test(query.trim())) {
    resultsEl.classList.add('hidden');
    await loadStock(query.trim());
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
    const list = await res.json();

    if (!list.length) {
      resultsEl.innerHTML = '<div class="search-empty">找不到相符的股票</div>';
      return;
    }

    resultsEl.innerHTML = list.map(s =>
      `<div class="search-item" data-code="${s.code}">
        <span class="search-code">${s.code}</span>
        <span class="search-name">${s.name}</span>
        <span class="search-price">${s.close || '--'}</span>
      </div>`
    ).join('');

    resultsEl.querySelectorAll('.search-item').forEach(el => {
      el.addEventListener('click', () => {
        resultsEl.classList.add('hidden');
        document.getElementById('search-input').value = el.dataset.code;
        loadStock(el.dataset.code);
      });
    });
  } catch (e) {
    resultsEl.innerHTML = '<div class="search-empty">搜尋失敗，請稍後再試</div>';
  }
}

// ── 個股查詢 ──────────────────────────────────────────────
async function loadStock(code) {
  currentCode = code;
  const section = document.getElementById('stock-section');
  section.classList.remove('hidden');

  document.getElementById('stock-price').textContent = '載入中...';
  document.getElementById('stock-change').textContent = '';

  try {
    const [quoteRes, histRes] = await Promise.all([
      fetch(`${API_BASE}/quote/${code}`),
      fetch(`${API_BASE}/history/${code}`),
    ]);

    const quote = await quoteRes.json();
    const hist = await histRes.json();

    if (quote.error) {
      document.getElementById('stock-price').textContent = '查無資料';
      return;
    }

    renderQuote(quote);
    if (!hist.error && hist.history) renderChart(hist.history);
  } catch (e) {
    document.getElementById('stock-price').textContent = '查詢失敗';
  }
}

function renderQuote(q) {
  const change = parseFloat(q.change);
  const pct = parseFloat(q.changePercent);
  const isUp = change >= 0;

  document.getElementById('stock-name').textContent = q.name;
  document.getElementById('stock-code').textContent = q.code;

  const priceEl = document.getElementById('stock-price');
  priceEl.textContent = q.price.toFixed(2);
  priceEl.className = `stock-price ${isUp ? 'up' : 'down'}`;

  const changeEl = document.getElementById('stock-change');
  changeEl.textContent = `${isUp ? '▲' : '▼'} ${Math.abs(change).toFixed(2)} (${isUp ? '+' : ''}${pct}%)`;
  changeEl.className = `stock-change ${isUp ? 'up' : 'down'}`;

  document.getElementById('m-open').textContent = q.open?.toFixed(2) ?? '--';
  document.getElementById('m-high').textContent = q.high?.toFixed(2) ?? '--';
  document.getElementById('m-low').textContent = q.low?.toFixed(2) ?? '--';
  document.getElementById('m-close').textContent = q.close?.toFixed(2) ?? '--';
  document.getElementById('m-volume').textContent = q.volume ? q.volume.toLocaleString() : '--';
  document.getElementById('m-time').textContent = q.time || '--';
}

function renderChart(history) {
  const labels = history.map(d => d.date);
  const prices = history.map(d => d.close);
  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? '#e53e3e' : '#38a169';

  if (priceChart) priceChart.destroy();

  const ctx = document.getElementById('price-chart').getContext('2d');
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '收盤價',
        data: prices,
        borderColor: color,
        backgroundColor: color + '22',
        borderWidth: 2,
        fill: true,
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `收盤：${ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 10, color: '#718096' },
          grid: { color: '#2d3748' },
        },
        y: {
          ticks: { color: '#718096' },
          grid: { color: '#2d3748' },
        },
      },
    },
  });
}

// ── 事件綁定 ──────────────────────────────────────────────
document.getElementById('search-btn').addEventListener('click', () => {
  search(document.getElementById('search-input').value);
});

document.getElementById('search-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') search(e.target.value);
});

document.addEventListener('click', e => {
  if (!e.target.closest('.search-section')) {
    document.getElementById('search-results').classList.add('hidden');
  }
});

document.querySelectorAll('.watchlist-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById('search-input').value = btn.dataset.code;
    loadStock(btn.dataset.code);
  });
});

// ── 初始化 ────────────────────────────────────────────────
loadIndex();
setInterval(updateClock, 1000);
setInterval(loadIndex, 60000);
