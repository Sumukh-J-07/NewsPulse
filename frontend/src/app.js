import { loadDashboard, refreshPipeline } from './data.js';
import { percent, points, number, outlook, absoluteError, rankSignals, filterHistory, timestamp, sessionDate, present } from './domain.js';

const content = document.querySelector('#content');
const titles = {
  overview: ['Next-Session Market Outlook', 'Inspect close-to-close forecast returns, news evidence, and empirical model accuracy.'],
  signals: ['Signals to Watch', 'Ranked by absolute size of the estimated move in either direction.'],
  history: ['Prediction Ledger', 'Historical record comparing next-session forecasts against realized outcomes.'],
  evaluation: ['Model Evaluation & Backtest', 'Compare price-only baseline versus news-aware model on chronological held-out observations.']
};

let data;
let requestId = 0;
let filters = { asset: '', from: '', to: '' };

const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const badge = value => `<span class="badge ${outlook(value).toLowerCase()}">${outlook(value)}</span>`;
const tone = value => !present(value) ? '' : value > 0.25 ? 'positive' : value < -0.25 ? 'negative' : '';
const panelHeading = (title, detail) => `<div class="panel-heading"><h2>${title}</h2><span>${detail}</span></div>`;

function context() {
  const closePolicy = data.dataOrigin === 'live'
    ? 'Nominal exchange close for prices; split-adjusted close for returns'
    : 'Deterministic sample values (fictional reference)';
  return `<details class="context"><summary>Forecast Context &amp; Research Assumptions</summary><dl>
    <div><dt>Reference Session</dt><dd>${sessionDate(data.referenceSession)}</dd></div>
    <div><dt>Target Forecast Session</dt><dd>${sessionDate(data.session)} (next regular session)</dd></div>
    <div><dt>Cutoff Timestamp</dt><dd>${timestamp(data.cutoff)}</dd></div>
    <div><dt>Generated</dt><dd>${data.blocked ? 'Forecast Withheld' : timestamp(data.generated)}</dd></div>
    <div><dt>Market Timezone</dt><dd>${data.timezone || 'Asia/Kolkata'}</dd></div>
    <div><dt>Active Model</dt><dd>${escape(data.model)}</dd></div>
    <div><dt>Signal Deadband</dt><dd>±0.25 pp (inclusive neutral boundaries)</dd></div>
    <div><dt>Price Series Policy</dt><dd>${closePolicy}</dd></div>
  </dl></details>`;
}

function stateNotice() {
  const messages = {
    stale: ['Required Inputs Are Stale', 'Current forecasts are withheld because reference market data exceeds the freshness threshold. Retained prior records remain available.'],
    provider: ['Market Data Provider Unavailable', 'Current estimates are withheld due to upstream provider outage. Previously verified records remain available for audit.'],
    pipeline: ['Prediction Pipeline Run Failed', 'No current prediction was published. Check backend pipeline logs or trigger a manual refresh.'],
    'no-news': ['Zero Eligible News in Sample Window', 'Neutral sentiment assigned (score = 0.0); forecast relies strictly on technical price momentum inputs.'],
  };
  const message = messages[data.scenario];
  return message ? `<div class="notice" role="status"><strong>${message[0]}</strong><p>${message[1]}</p></div>` : '';
}

function stockTable() {
  if (!data.stocks || !data.stocks.length) {
    return '<div class="empty"><h3>No Predictions Available</h3><p>Stock signals will appear once a forecast pipeline run publishes results.</p></div>';
  }
  return `<div class="table-scroll"><table>
    <caption class="sr-only">Configured stock signals ranked by descending absolute estimated change.</caption>
    <thead>
      <tr>
        <th scope="col">Asset / Reference Close</th>
        <th scope="col" class="numeric">Forecast Return</th>
        <th scope="col">Outlook</th>
        <th scope="col">Eligible News</th>
        <th scope="col" class="numeric">Realized Return</th>
        <th scope="col" class="numeric">Abs. Error</th>
      </tr>
    </thead>
    <tbody>
      ${rankSignals(data.stocks).map(stock => `<tr>
        <th scope="row">
          <span class="ticker">${escape(stock.ticker)}</span>
          <span class="cell-note">${escape(stock.name)} · ${number(stock.close)}</span>
        </th>
        <td class="numeric ${tone(stock.estimate)}">${percent(stock.estimate)}</td>
        <td>${badge(stock.estimate)}</td>
        <td>${stock.articles} <span class="cell-note">eligible headlines${data.blocked ? ' · stale' : ''}</span></td>
        <td class="numeric">${data.blocked ? 'Unavailable' : stock.actual === null ? 'Pending' : percent(stock.actual)}</td>
        <td class="numeric">${data.blocked ? 'Unavailable' : points(absoluteError(stock.estimate, stock.actual))}</td>
      </tr>`).join('')}
    </tbody>
  </table></div>`;
}

function evidence() {
  const isLive = data.dataOrigin === 'live';
  const subtitle = isLive ? 'Eligible ingested headlines with source attribution' : 'Fictional sample evidence';
  return `<section class="panel evidence">
    ${panelHeading('Headline Evidence', subtitle)}
    <div class="headline-grid">
      ${rankSignals(data.stocks).map(stock => `<article>
        <div>
          <span class="eyebrow">${escape(stock.ticker)}</span>
          <h3>${stock.headline ? escape(stock.headline) : 'No eligible news in cutoff window'}</h3>
          <p>${stock.headline ? `${escape(stock.source || 'News Desk')} · ${timestamp(stock.published)}` : 'No verified headlines preceded the prediction cutoff timestamp.'}</p>
        </div>
        <div>
          ${stock.url ? `<a href="${escape(stock.url)}" target="_blank" rel="noopener noreferrer" class="cell-note" style="color:var(--accent-navy);font-weight:600;">Original source link ↗</a>` : stock.headline ? `<span class="cell-note">${isLive ? 'Live ingested news' : 'Sample headline (no external link)'}</span>` : ''}
        </div>
      </article>`).join('')}
    </div>
  </section>`;
}

function overview() {
  if (data.scenario === 'empty') {
    return '<section class="panel empty"><h2>No Current Predictions</h2><p>A completed prediction run will populate this overview. Historical records remain available in the Prediction Ledger.</p></section>';
  }
  const isLive = data.dataOrigin === 'live';
  const marketTag = isLive ? 'NATIONAL STOCK EXCHANGE OF INDIA · NIFTY 50' : 'SAMPLE DEMONSTRATION WATCHLIST · FICTIONAL';
  const coverageNote = isLive ? 'NIFTY 50 + 8 Active NSE Equities' : 'Fixed 5-Stock Fictional Watchlist';
  const dataStatus = data.blocked ? 'Unavailable · Stale Inputs' : isLive ? 'Live Ingested Market Inputs' : 'Sample Deterministic Inputs';

  return `<section class="hero">
    <div>
      <p class="eyebrow">${marketTag}</p>
      <h2>${escape(data.index.name)}</h2>
      <div class="hero-estimate ${tone(data.index.estimate)}">
        ${percent(data.index.estimate)} ${badge(data.index.estimate)}
      </div>
      <p style="margin:0;font-size:13px;color:var(--text-secondary);">Estimated close-to-close change</p>
      <span class="hero-horizon">Target Session: <strong>${sessionDate(data.session)}</strong> (Next Regular Session)</span>
    </div>
    <dl>
      <div><dt>Reference Close</dt><dd>${number(data.index.close)}</dd></div>
      <div><dt>Data Status</dt><dd>${dataStatus}</dd></div>
      <div><dt>Cutoff Timestamp</dt><dd>${timestamp(data.cutoff)}</dd></div>
      <div><dt>Forecasting Model</dt><dd>${escape(data.model)}</dd></div>
    </dl>
  </section>
  <div class="stat-grid">
    <article class="stat">
      <p>Watchlist Coverage</p>
      <strong>1 Index + ${data.stocks ? data.stocks.length : 0} Stocks</strong>
      <small>${coverageNote}</small>
    </article>
    <article class="stat">
      <p>Prediction Horizon</p>
      <strong>Next Regular Session</strong>
      <small>Close-to-close return %</small>
    </article>
    <article class="stat">
      <p>Empirical Question</p>
      <strong>Does Financial News Help?</strong>
      <small>Compare baseline vs news-aware Ridge</small>
    </article>
  </div>
  <section class="panel">
    ${panelHeading('Configured Asset Signals', '<a href="#signals">Inspect Evidence →</a>')}
    ${stockTable()}
  </section>
  ${context()}`;
}

function history() {
  const isLive = data.dataOrigin === 'live';
  const ledgerSubtitle = isLive ? 'Database records · Live NSE Equities' : 'Sample records · news-aware demo v0.1';
  const availableTickers = Array.from(new Set([
    ...(data.history || []).map(r => r.ticker),
    ...(data.stocks || []).map(s => s.ticker)
  ])).filter(Boolean).sort();

  const tickerOptions = availableTickers.length
    ? availableTickers.map(ticker => `<option value="${escape(ticker)}" ${filters.asset === ticker ? 'selected' : ''}>${escape(ticker)}</option>`).join('')
    : ['ALFA', 'BRIO', 'CEDR', 'DUNE', 'ELIO'].map(ticker => `<option ${filters.asset === ticker ? 'selected' : ''}>${ticker}</option>`).join('');

  return `<section class="panel">
    ${panelHeading('Prediction Ledger', ledgerSubtitle)}
    <form id="history-filters" class="filters">
      <label>Asset
        <select name="asset">
          <option value="">All Watchlist Assets</option>
          ${tickerOptions}
        </select>
      </label>
      <label>From Session
        <input type="date" name="from" value="${escape(filters.from)}">
      </label>
      <label>To Session
        <input type="date" name="to" value="${escape(filters.to)}">
      </label>
      <button type="submit">Filter Ledger</button>
      <button type="button" id="clear-filters" class="secondary">Reset</button>
    </form>
    <div id="history-results" aria-live="polite"></div>
  </section>
  <p class="helper">Session dates indicate the target forecast date. Pending indicates that the market session outcome has not yet resolved. Forecast errors are reported in percentage points (pp).</p>`;
}

function renderHistoryRows() {
  const target = document.querySelector('#history-results');
  if (!target) return;
  if (filters.from && filters.to && filters.from > filters.to) {
    target.innerHTML = '<p class="notice" role="alert">From session must be on or before To session.</p>';
    return;
  }
  const rows = filterHistory(data.history, filters);
  target.innerHTML = rows.length ? `<div class="table-scroll"><table>
    <caption class="sr-only">${rows.length} matching predictions</caption>
    <thead>
      <tr>
        <th scope="col">Target Session</th>
        <th scope="col">Asset</th>
        <th scope="col" class="numeric">Estimate</th>
        <th scope="col" class="numeric">Actual Outcome</th>
        <th scope="col" class="numeric">Abs. Error</th>
        <th scope="col">Model Version</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map(row => `<tr>
        <td>${sessionDate(row.session)}</td>
        <th scope="row"><span class="ticker">${escape(row.ticker)}</span></th>
        <td class="numeric ${tone(row.estimate)}">${percent(row.estimate)}</td>
        <td class="numeric">${row.actual === null ? 'Pending' : percent(row.actual)}</td>
        <td class="numeric">${points(row.error)}</td>
        <td>${escape(row.model)}</td>
      </tr>`).join('')}
    </tbody>
  </table></div>
  <p class="result-count">${rows.length} matching records found</p>`
  : '<div class="empty"><h3>No Matching Records</h3><p>Adjust asset or widen the session date filter range.</p></div>';
}

function evaluation() {
  const isLive = data.dataOrigin === 'live';
  const noticeBanner = isLive
    ? '<div class="notice" style="background:#f0fdf4;border-color:#bbf7d0;color:#166534;"><strong>Chronological Holdout Evaluation</strong><p>Evaluated on chronological 20% test partition of market observations without shuffling or data leakage.</p></div>'
    : '<div class="notice"><strong>Illustrative Sample Evaluation</strong><p>These fixed sample metrics demonstrate interface behavior on synthetic data. They are not real market training results.</p></div>';

  const obsDetail = isLive ? 'Chronological held-out test split (real market data)' : 'Deterministic held-out sample partition';
  const datesDetail = data.evaluationPeriod
    ? (typeof data.evaluationPeriod === 'object' ? `${data.evaluationPeriod.start || ''} – ${data.evaluationPeriod.end || ''}` : data.evaluationPeriod)
    : 'Chronological test period';

  return `${noticeBanner}
  <section class="panel">
    ${panelHeading('Comparative Empirical Performance', obsDetail)}
    <div class="table-scroll"><table>
      <caption class="sr-only">Model comparison on chronological held-out period</caption>
      <thead>
        <tr>
          <th scope="col">Model Architecture</th>
          <th scope="col" class="numeric">MAE (pp) ↓</th>
          <th scope="col" class="numeric">Directional Accuracy</th>
          <th scope="col" class="numeric">Sample Count</th>
        </tr>
      </thead>
      <tbody>
        ${data.metrics.map(model => `<tr>
          <th scope="row">
            ${escape(model.name)}
            <span class="cell-note">${escape(model.model_identifier || 'Standard evaluation')}</span>
          </th>
          <td class="numeric">${points(model.mae)}</td>
          <td class="numeric">${model.accuracy !== null && model.accuracy !== undefined ? `${model.accuracy}%` : 'N/A'}</td>
          <td class="numeric">${model.count}</td>
        </tr>`).join('')}
      </tbody>
    </table></div>
    <div class="evaluation-period">
      <strong>Chronological Evaluation Partition</strong>
      <span>${escape(datesDetail)}</span>
      <p>Target: next regular session close-to-close percentage change. Baseline and news-aware models are evaluated on identical test observations.</p>
    </div>
  </section>
  <div class="definition-grid">
    <article class="panel">
      <h2>Mean Absolute Error (MAE)</h2>
      <p>Average absolute distance between forecast estimates and realized session returns in percentage points (pp). Lower values indicate superior calibration.</p>
      <p style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted);">Formula: (1/N) × Σ |Estimate_i − Realized_i|</p>
    </article>
    <article class="panel">
      <h2>Directional Accuracy</h2>
      <p>Share of forecasts whose sign (+/−) strictly matches the realized market return direction. Zero return is treated as neutral.</p>
      <p style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted);">Directional accuracy exceeds random guessing when &gt; 50.0%.</p>
    </article>
  </div>`;
}

function updateModeBanner() {
  const banner = document.querySelector('#mode-banner');
  const badgeEl = document.querySelector('#banner-badge');
  const textEl = document.querySelector('#banner-text');
  const metaEl = document.querySelector('#banner-meta');
  const btnLive = document.querySelector('#btn-mode-live');
  const btnSample = document.querySelector('#btn-mode-sample');

  if (!banner || !data) return;

  const isLive = data.dataOrigin === 'live';
  banner.className = `mode-banner ${isLive ? 'live-mode' : 'sample-mode'}`;
  
  if (btnLive && btnSample) {
    if (isLive) {
      btnLive.classList.add('active');
      btnSample.classList.remove('active');
    } else {
      btnSample.classList.add('active');
      btnLive.classList.remove('active');
    }
  }

  if (isLive) {
    badgeEl.textContent = 'LIVE MARKET DATA';
    textEl.textContent = 'Sourced from National Stock Exchange of India (NSE) via Yahoo Finance and verified financial RSS feeds.';
    const latestPrice = data.freshness?.latest_price_session || data.referenceSession || 'Active';
    metaEl.innerHTML = `Price session: <strong>${sessionDate(latestPrice)}</strong> · Cutoff: <strong>${timestamp(data.cutoff)}</strong>`;
  } else {
    badgeEl.textContent = 'SAMPLE DATA — FICTIONAL';
    textEl.textContent = 'Deterministic synthetic watchlist (ALFA, BRIO, CEDR, DUNE, ELIO) for offline verification. Fictional prices and headlines.';
    metaEl.innerHTML = `Reference session: <strong>${sessionDate(data.referenceSession)}</strong> · Offline mode`;
  }
}

function render() {
  const route = location.hash.slice(1);
  const view = Object.hasOwn(titles, route) ? route : 'overview';
  
  document.querySelectorAll('[data-view]').forEach(link => {
    if (link.dataset.view === view) {
      link.classList.add('active');
      link.setAttribute('aria-current', 'page');
    } else {
      link.classList.remove('active');
      link.removeAttribute('aria-current');
    }
  });

  const titleEl = document.querySelector('#page-title');
  const subEl = document.querySelector('#page-subtitle');
  const breadEl = document.querySelector('#breadcrumb');
  if (titleEl) titleEl.textContent = titles[view][0];
  if (subEl) subEl.textContent = titles[view][1];
  if (breadEl) breadEl.textContent = titles[view][0];

  if (!data) return;
  updateModeBanner();

  if (data.scenario === 'loading') {
    content.innerHTML = '<section class="panel empty" aria-busy="true"><div class="loader"></div><h2>Loading Pipeline Data…</h2><p>This fixture illustrates an active loading state. Select another mode to continue.</p></section>';
    return;
  }

  content.innerHTML = stateNotice() + ({
    overview,
    signals: () => `<section class="panel">${panelHeading('Watchlist Signals &amp; Estimates', `Forecast Session: ${sessionDate(data.session)}`)}${stockTable()}</section>${context()}${data.stocks && data.stocks.length ? evidence() : ''}`,
    history,
    evaluation
  }[view])();

  if (view === 'history') {
    renderHistoryRows();
    document.querySelector('#history-filters')?.addEventListener('submit', event => {
      event.preventDefault();
      filters = Object.fromEntries(new FormData(event.currentTarget));
      renderHistoryRows();
    });
    document.querySelector('#clear-filters')?.addEventListener('click', () => {
      filters = { asset: '', from: '', to: '' };
      render();
    });
  }
}

async function reload() {
  const current = ++requestId;
  content.setAttribute('aria-busy', 'true');
  content.innerHTML = '<section class="panel empty" role="status"><div class="loader"></div><p>Connecting to data provider…</p></section>';
  try {
    const selectedScenario = document.querySelector('#scenario').value;
    const result = await loadDashboard(selectedScenario);
    if (current !== requestId) return;
    data = result;
    render();
    const selText = document.querySelector('#scenario').selectedOptions[0]?.textContent || selectedScenario;
    document.querySelector('#announcement').textContent = data.dataOrigin === 'live'
      ? 'Live market data loaded from FastAPI backend'
      : `Sample scenario loaded: ${selText}`;
  } catch (err) {
    if (current !== requestId) return;
    content.innerHTML = `<div class="notice" role="alert">
      <strong>Unable to Load Pipeline Data</strong>
      <p>${escape(err.message || 'The backend service may be starting or unreachable. Choose another scenario or verify the API server.')}</p>
    </div>`;
  } finally {
    if (current === requestId) content.removeAttribute('aria-busy');
  }
}

// Mode button triggers
document.querySelector('#btn-mode-live')?.addEventListener('click', () => {
  const scenarioSelect = document.querySelector('#scenario');
  if (scenarioSelect) scenarioSelect.value = 'live';
  reload();
});

document.querySelector('#btn-mode-sample')?.addEventListener('click', () => {
  const scenarioSelect = document.querySelector('#scenario');
  if (scenarioSelect) scenarioSelect.value = 'sample';
  reload();
});

// Refresh button trigger
document.querySelector('#btn-refresh')?.addEventListener('click', async () => {
  const btn = document.querySelector('#btn-refresh');
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="refresh-icon">↻</span> Refreshing…';
  try {
    const currentMode = data?.dataOrigin === 'sample' ? 'sample' : 'live';
    await refreshPipeline(currentMode);
    await reload();
  } catch (err) {
    alert(`Refresh Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
});

document.querySelector('.skip')?.addEventListener('click', event => {
  event.preventDefault();
  document.querySelector('#main')?.focus();
  document.querySelector('#main')?.scrollIntoView();
});

window.addEventListener('hashchange', () => {
  render();
  document.querySelector('#main')?.focus();
});

document.querySelector('#scenario')?.addEventListener('change', reload);

// Initial execution
render();
reload();
