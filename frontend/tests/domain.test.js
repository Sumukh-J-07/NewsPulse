import test from 'node:test';
import assert from 'node:assert/strict';
import { percent, points, outlook, absoluteError, rankSignals, filterHistory } from '../src/domain.js';
import { loadDashboard } from '../src/data.js';

test('percent units preserve zero and never turn missing data into zero', () => {
  assert.equal(percent(1.25), '+1.25%');
  assert.equal(percent(0), '0.00%');
  for (const value of [null, undefined, NaN, Infinity]) assert.equal(percent(value), 'Unavailable');
  assert.equal(points(null), 'Pending');
});
test('outlook boundaries are inclusive neutral, with configurable threshold', () => {
  assert.equal(outlook(0.25), 'Neutral');
  assert.equal(outlook(-0.25), 'Neutral');
  assert.equal(outlook(0.2501), 'Bullish');
  assert.equal(outlook(-0.2501), 'Bearish');
  assert.equal(outlook(0.4, 0.5), 'Neutral');
  assert.equal(outlook(null), 'Unavailable');
});
test('error uses percentage points and unresolved actuals stay missing', () => {
  assert.equal(points(absoluteError(1.2, 0.8)), '0.40 pp');
  assert.equal(absoluteError(1.2, null), null);
  assert.equal(absoluteError(1.2, 0), 1.2);
});
test('negative moves rank by magnitude, ticker resolves ties, null sorts last', () => {
  const stocks = [{ticker:'Z',estimate:1},{ticker:'B',estimate:-2},{ticker:'A',estimate:2},{ticker:'X',estimate:null}];
  assert.deepEqual(rankSignals(stocks).map(s => s.ticker), ['A','B','Z','X']);
  assert.equal(stocks[0].ticker, 'Z');
});
test('history filters are inclusive and compose', () => {
  const rows = [{ticker:'A',session:'2026-10-14'}, {ticker:'B',session:'2026-10-15'}, {ticker:'A',session:'2026-10-16'}];
  assert.deepEqual(filterHistory(rows, {asset:'A',from:'2026-10-14',to:'2026-10-14'}), [rows[0]]);
  assert.deepEqual(filterHistory(rows, {from:'2026-10-17'}), []);
});
test('required-input failures withhold estimates and preserve prior history', async () => {
  for (const scenario of ['stale','provider','pipeline']) {
    const data = await loadDashboard(scenario);
    assert.equal(data.index.estimate, null);
    assert.ok(data.stocks.every(stock => stock.estimate === null));
    assert.ok(data.history.every(row => row.session < data.session));
    assert.ok(data.history.length > 0);
  }
});
test('sample evidence precedes cutoff and pending outcomes resolve explicitly', async () => {
  const pending = await loadDashboard('ready');
  assert.ok(pending.stocks.every(stock => stock.actual === null && stock.published <= pending.cutoff));
  const resolved = await loadDashboard('resolved');
  assert.ok(resolved.stocks.every(stock => typeof stock.actual === 'number'));
  const noNews = await loadDashboard('no-news');
  assert.ok(noNews.stocks.every(stock => stock.articles === 0 && stock.headline === null));
});
