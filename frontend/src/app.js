import { loadDashboard } from './data.js';
import { percent, points, number, outlook, absoluteError, rankSignals, filterHistory, timestamp, sessionDate, present } from './domain.js';

const content = document.querySelector('#content');
const titles = { overview: ['A clearer view of the next session.', 'Explore estimates, inspect the evidence, and measure what holds up.'], signals: ['Signals worth a closer look.', 'Ranked by the size of the estimated move, in either direction.'], history: ['Every estimate has a record.', 'Compare forecasts with outcomes as each trading session resolves.'], evaluation: ['Measure the value of news.', 'Compare both models on the same chronological held-out observations.'] };
let data;
let requestId = 0;
let filters = { asset: '', from: '', to: '' };
const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const badge = value => `<span class="badge ${outlook(value).toLowerCase()}">${outlook(value)}</span>`;
const tone = value => !present(value) ? '' : value > 0.25 ? 'positive' : value < -0.25 ? 'negative' : '';
const panelHeading = (title, detail) => `<div class="panel-heading"><h2>${title}</h2><span>${detail}</span></div>`;
function context() {
  return `<details class="context"><summary>Prediction context and assumptions</summary><dl><div><dt>Reference session</dt><dd>${sessionDate(data.referenceSession)}</dd></div><div><dt>Forecast session</dt><dd>${sessionDate(data.session)} · next regular session</dd></div><div><dt>Cutoff</dt><dd>${timestamp(data.cutoff)}</dd></div><div><dt>Generated</dt><dd>${data.blocked ? 'No current forecast' : timestamp(data.generated)}</dd></div><div><dt>Market timezone</dt><dd>${data.timezone}</dd></div><div><dt>Model</dt><dd>${data.model}</dd></div><div><dt>Outlook threshold</dt><dd>±0.25 pp; boundary values are neutral</dd></div><div><dt>Close policy</dt><dd>Demo reference values; real adjustment policy undecided</dd></div></dl></details>`;
}
function stateNotice() {
  const messages = {
    stale: ['Required inputs are stale', 'Current estimates are withheld. Reference prices and headline evidence below are retained sample records; they are not fresh inputs.'],
    provider: ['News provider unavailable', 'Current estimates are withheld. Previously successful sample records are retained and marked stale.'],
    pipeline: ['Prediction pipeline failed', 'No current prediction was published. Retained input records and prior history remain available for inspection.'],
    'no-news': ['No eligible news in this sample', 'This fixture illustrates a possible no-news policy with price inputs available. Whether a real forecast is allowed in this case must be agreed with Sumukh.'],
  };
  const message = messages[data.scenario];
  return message ? `<div class="notice" role="status"><strong>${message[0]}</strong><p>${message[1]}</p></div>` : '';
}
function stockTable() {
  if (!data.stocks.length) return '<div class="empty"><h2>No predictions yet</h2><p>Stock signals will appear when a prediction run publishes results.</p></div>';
  return `<div class="table-scroll"><table><caption class="sr-only">Sample stock signals, sorted by descending absolute estimated change. Equal estimates are ordered by ticker.</caption><thead><tr><th scope="col">Asset / reference close</th><th scope="col">Estimate</th><th scope="col">Outlook</th><th scope="col">News</th><th scope="col">Actual</th><th scope="col">Abs. error</th></tr></thead><tbody>${rankSignals(data.stocks).map(stock => `<tr><th scope="row"><span class="ticker">${escape(stock.ticker)}</span><span class="cell-note">${escape(stock.name)} · ${number(stock.close)}</span></th><td class="numeric ${tone(stock.estimate)}">${percent(stock.estimate)}</td><td>${badge(stock.estimate)}</td><td>${stock.articles} <span class="cell-note">eligible articles${data.blocked ? ' · retained/stale' : ''}</span></td><td class="numeric">${data.blocked ? 'Unavailable' : stock.actual === null ? 'Pending' : percent(stock.actual)}</td><td class="numeric">${data.blocked ? 'Unavailable' : points(absoluteError(stock.estimate, stock.actual))}</td></tr>`).join('')}</tbody></table></div>`;
}
function evidence() {
  return `<section class="panel evidence">${panelHeading('Behind the signals', 'Fictional headline evidence')}<div class="headline-grid">${rankSignals(data.stocks).map(stock => `<article><span class="eyebrow">${escape(stock.ticker)}</span><h3>${stock.headline ? escape(stock.headline) : 'No eligible news'}</h3><p>${stock.headline ? `Demo News Desk · ${timestamp(stock.published)}` : 'No linked headlines were available before the sample cutoff.'}</p>${stock.headline ? '<span class="cell-note">Sample headline · no external source link</span>' : ''}</article>`).join('')}</div></section>`;
}
function overview() {
  if (data.scenario === 'empty') return '<section class="panel empty"><h2>No current predictions</h2><p>A completed prediction run will populate this overview. Previous records are available in Prediction history.</p></section>';
  return `<section class="hero"><div><p class="eyebrow">INDEX OUTLOOK · FICTIONAL EXCHANGE</p><h2>${data.index.name}</h2><div class="hero-estimate">${percent(data.index.estimate)} ${badge(data.index.estimate)}</div><p>Estimated close-to-close change</p><span class="hero-horizon">Next regular session · ${sessionDate(data.session)}</span></div><dl><div><dt>Reference close</dt><dd>${number(data.index.close)}</dd></div><div><dt>Data status</dt><dd>${data.blocked ? 'Unavailable · retained inputs' : 'Sample inputs ready'}</dd></div><div><dt>Generated</dt><dd>${data.blocked ? 'No current forecast' : timestamp(data.generated)}</dd></div><div><dt>Model</dt><dd>${data.model}</dd></div></dl></section>
    <div class="stat-grid"><article class="stat"><p>Coverage</p><strong>1 index <span>+ 5 stocks</span></strong><small>Fixed fictional watchlist</small></article><article class="stat"><p>Prediction horizon</p><strong>Next session</strong><small>Daily close-to-close return</small></article><article class="stat"><p>Research question</p><strong>Does news help?</strong><small>Compare with a price-only baseline</small></article></div>
    <section class="panel">${panelHeading('Signals to watch', '<a href="#signals">Explore evidence →</a>')}${stockTable()}</section>${context()}`;
}
function history() {
  return `<section class="panel">${panelHeading('Prediction ledger', 'Sample records · news-aware demo v0.1')}<form id="history-filters" class="filters"><label>Asset<select name="asset"><option value="">All assets</option>${['ALFA', 'BRIO', 'CEDR', 'DUNE', 'ELIO'].map(ticker => `<option ${filters.asset === ticker ? 'selected' : ''}>${ticker}</option>`).join('')}</select></label><label>From session<input type="date" name="from" value="${escape(filters.from)}"></label><label>To session<input type="date" name="to" value="${escape(filters.to)}"></label><button type="submit">Apply filters</button><button type="button" id="clear-filters" class="secondary">Reset</button></form><div id="history-results" aria-live="polite"></div></section><p class="helper">Session dates identify the forecast target. Pending means the next-session outcome has not been recorded. Error is measured in percentage points (pp).</p>`;
}
function renderHistoryRows() {
  const target = document.querySelector('#history-results');
  if (!target) return;
  if (filters.from && filters.to && filters.from > filters.to) { target.innerHTML = '<p class="notice" role="alert">From session must be on or before To session.</p>'; return; }
  const rows = filterHistory(data.history, filters);
  target.innerHTML = rows.length ? `<div class="table-scroll"><table><caption class="sr-only">${rows.length} matching sample predictions</caption><thead><tr><th scope="col">Target session</th><th scope="col">Asset</th><th scope="col">Estimate</th><th scope="col">Actual</th><th scope="col">Abs. error</th><th scope="col">Model</th></tr></thead><tbody>${rows.map(row => `<tr><td>${sessionDate(row.session)}</td><th scope="row">${row.ticker}</th><td>${percent(row.estimate)}</td><td>${row.actual === null ? 'Pending' : percent(row.actual)}</td><td>${points(row.error)}</td><td>${row.model}</td></tr>`).join('')}</tbody></table></div><p class="result-count">${rows.length} matching sample records</p>` : '<div class="empty"><h3>No matching predictions</h3><p>Try another asset or widen the session range.</p></div>';
}
function evaluation() {
  return `<div class="notice"><strong>Illustrative metrics only</strong><p>These fixed sample values demonstrate the interface. They are not training results and do not establish that news improves predictions.</p></div><section class="panel">${panelHeading('Baseline versus news-aware', 'Same 100 fictional observations')}<div class="table-scroll"><table><caption class="sr-only">Illustrative model comparison on the same sample held-out period</caption><thead><tr><th scope="col">Model</th><th scope="col">MAE ↓</th><th scope="col">Directional accuracy</th><th scope="col">Sample count</th></tr></thead><tbody>${data.metrics.map(model => `<tr><th scope="row">${model.name}<span class="cell-note">Demo version 0.1</span></th><td class="numeric">${points(model.mae)}</td><td>${model.accuracy}%</td><td>${model.count}</td></tr>`).join('')}</tbody></table></div><div class="evaluation-period"><strong>Sample held-out dates</strong><span>1 September – 30 September 2026 · chronological split</span><p>Target: next regular session close-to-close percentage change. Real partitions, exclusions and eligible rows must be supplied by the backend.</p></div></section><div class="definition-grid"><article class="panel"><h2>Mean absolute error</h2><p>The average distance between estimates and actual changes. Lower is better.</p><p>Estimated +1.20%, actual +0.80% → error <strong>0.40 pp</strong>.</p></article><article class="panel"><h2>Directional accuracy</h2><p>The share of estimates whose sign matches the actual change. Zero is treated as neutral.</p><p>This uses signs, not the ±0.25 pp outlook threshold.</p></article></div>`;
}
function render() {
  const route = location.hash.slice(1);
  const view = Object.hasOwn(titles, route) ? route : 'overview';
  document.querySelectorAll('[data-view]').forEach(link => { if (link.dataset.view === view) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
  document.querySelector('#page-title').textContent = titles[view][0];
  document.querySelector('#page-subtitle').textContent = titles[view][1];
  document.querySelector('#breadcrumb').textContent = document.querySelector(`[data-view="${view}"]`).firstChild.textContent.trim();
  if (!data) return;
  if (data.scenario === 'loading') { content.innerHTML = '<section class="panel empty" aria-busy="true"><div class="loader"></div><h2>Loading sample predictions…</h2><p>This scenario stays loading so you can inspect it. Choose another scenario to continue.</p></section>'; return; }
  content.innerHTML = stateNotice() + ({ overview, signals: () => `<section class="panel">${panelHeading('Signals to watch', `Forecast session: ${sessionDate(data.session)}`)}${stockTable()}</section>${context()}${data.stocks.length ? evidence() : ''}`, history, evaluation }[view])();
  if (view === 'history') {
    renderHistoryRows();
    document.querySelector('#history-filters').addEventListener('submit', event => { event.preventDefault(); filters = Object.fromEntries(new FormData(event.currentTarget)); renderHistoryRows(); });
    document.querySelector('#clear-filters').addEventListener('click', () => { filters = { asset: '', from: '', to: '' }; render(); });
  }
}
async function reload() {
  const current = ++requestId;
  content.setAttribute('aria-busy', 'true');
  content.innerHTML = '<section class="panel empty" role="status">Loading sample data…</section>';
  try {
    const result = await loadDashboard(document.querySelector('#scenario').value);
    if (current !== requestId) return;
    data = result;
    render();
    document.querySelector('#announcement').textContent = `Sample scenario: ${document.querySelector('#scenario').selectedOptions[0].textContent}`;
  } catch {
    if (current !== requestId) return;
    content.innerHTML = '<div class="notice" role="alert"><strong>Unable to load dashboard data.</strong><p>Choose a scenario to retry.</p></div>';
  } finally { if (current === requestId) content.removeAttribute('aria-busy'); }
}
document.querySelector('.skip').addEventListener('click', event => {
  event.preventDefault();
  document.querySelector('#main').focus();
  document.querySelector('#main').scrollIntoView();
});
window.addEventListener('hashchange', () => { render(); document.querySelector('#main').focus(); });
document.querySelector('#scenario').addEventListener('change', reload);
render();
reload();
