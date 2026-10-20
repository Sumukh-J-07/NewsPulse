// Data adapter connecting to the live FastAPI backend with fallback to test fixtures.
import { absoluteError } from './domain.js';

const baseStocks = [
  { ticker: 'ALFA', name: 'Alfa Systems', estimate: 1.2, actual: 0.8, close: 142.6, articles: 8, headline: 'Alfa Systems announces a new research partnership', published: '2026-10-15T14:10:00Z' },
  { ticker: 'BRIO', name: 'Brio Energy', estimate: -1.45, actual: -0.9, close: 83.12, articles: 5, headline: 'Brio Energy revises its annual capacity outlook', published: '2026-10-15T13:35:00Z' },
  { ticker: 'CEDR', name: 'Cedar Industries', estimate: 0.25, actual: -0.1, close: 217.9, articles: 3, headline: 'Cedar Industries publishes its quarterly update', published: '2026-10-15T12:20:00Z' },
  { ticker: 'DUNE', name: 'Dune Consumer', estimate: -0.65, actual: -0.4, close: 56.4, articles: 4, headline: 'Dune Consumer reports changing regional demand', published: '2026-10-15T11:45:00Z' },
  { ticker: 'ELIO', name: 'Elio Networks', estimate: 0.48, actual: 0.6, close: 109.75, articles: 6, headline: 'Elio Networks expands its infrastructure programme', published: '2026-10-15T15:00:00Z' },
];

function getFixture(scenario) {
  const blocked = ['stale', 'provider', 'pipeline'].includes(scenario);
  return {
    scenario, blocked, threshold: 0.25,
    referenceSession: '2026-10-15', session: '2026-10-16',
    generated: '2026-10-15T16:15:00Z', cutoff: '2026-10-15T16:00:00Z',
    timezone: 'UTC (fictional demo exchange)', model: 'News-aware demo · v0.1',
    index: { name: 'Demo Market 100', close: 12480.5, estimate: blocked ? null : 0.62 },
    stocks: scenario === 'empty' ? [] : baseStocks.map(stock => ({ ...stock,
      estimate: blocked ? null : stock.estimate,
      actual: scenario === 'resolved' ? stock.actual : null,
      articles: scenario === 'no-news' ? 0 : stock.articles,
      headline: scenario === 'no-news' ? null : stock.headline,
    })),
    history: baseStocks.flatMap(stock => [
      { ticker: stock.ticker, session: '2026-10-14', estimate: stock.estimate, actual: stock.actual, error: absoluteError(stock.estimate, stock.actual), model: 'News-aware demo · v0.1' },
      ...(blocked || scenario === 'empty' ? [] : [{ ticker: stock.ticker, session: '2026-10-16', estimate: stock.estimate, actual: scenario === 'resolved' ? stock.actual : null, error: scenario === 'resolved' ? absoluteError(stock.estimate, stock.actual) : null, model: 'News-aware demo · v0.1' }]),
    ]).sort((a, b) => b.session.localeCompare(a.session)),
    metrics: [ { name: 'Price-only baseline', mae: 0.91, accuracy: 51, count: 100 }, { name: 'News-aware model', mae: 0.84, accuracy: 55, count: 100 } ],
  };
}

export async function loadDashboard(scenario = 'live') {
  // If explicitly requesting a test fixture scenario, return deterministic fixture
  if (['ready', 'resolved', 'no-news', 'stale', 'provider', 'pipeline', 'empty', 'loading'].includes(scenario)) {
    await new Promise(resolve => setTimeout(resolve, 10));
    return getFixture(scenario);
  }

  // Real API integration (FastAPI backend) with mode parameter
  const mode = scenario === 'sample' ? 'sample' : 'live';
  const apiBase = window.location.port === '8000' ? '' : 'http://127.0.0.1:8000';
  const [ovRes, stRes, mtRes, hiRes, statusRes] = await Promise.all([
    fetch(`${apiBase}/api/v1/overview?mode=${mode}`),
    fetch(`${apiBase}/api/v1/stocks?mode=${mode}`),
    fetch(`${apiBase}/api/v1/metrics?mode=${mode}`),
    fetch(`${apiBase}/api/v1/predictions?mode=${mode}`),
    fetch(`${apiBase}/api/v1/status?mode=${mode}`),
  ]);

  if (!ovRes.ok) {
    throw new Error(`Overview API error: ${ovRes.status} ${ovRes.statusText}`);
  }
  if (!stRes.ok) {
    throw new Error(`Stocks API error: ${stRes.status} ${stRes.statusText}`);
  }

  const ov = await ovRes.json();
  const st = await stRes.json();
  const mt = mtRes.ok ? await mtRes.json() : { metrics: [] };
  const hi = hiRes.ok ? await hiRes.json() : [];
  const statusData = statusRes.ok ? await statusRes.json() : {};

  return {
    scenario: mode,
    mode: mode,
    dataOrigin: ov.data_origin || mode,
    provider: ov.provider || (mode === 'live' ? 'yfinance' : 'sample_generator'),
    blocked: ov.blocked || false,
    dataStatus: ov.data_status || 'ready',
    threshold: ov.threshold_pp || 0.25,
    referenceSession: ov.reference_session,
    session: ov.session,
    generated: ov.generated,
    cutoff: ov.cutoff,
    timezone: ov.timezone,
    model: ov.model,
    index: ov.index,
    stocks: st,
    history: hi,
    metrics: mt.metrics || [],
    evaluationPeriod: mt.evaluation_period,
    freshness: ov.freshness || {},
    statusInfo: statusData,
  };
}

export async function refreshPipeline(mode = 'live', token = 'newspulse-dev-token') {
  const apiBase = window.location.port === '8000' ? '' : 'http://127.0.0.1:8000';
  const res = await fetch(`${apiBase}/api/v1/jobs/refresh?mode=${mode}`, {
    method: 'POST',
    headers: {
      'X-Operator-Token': token,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Refresh failed with status ${res.status}`);
  }
  return await res.json();
}
