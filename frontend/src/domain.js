export const present = value => typeof value === 'number' && Number.isFinite(value);
export const percent = value => present(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : 'Unavailable';
export const points = value => present(value) ? `${value.toFixed(2)} pp` : 'Pending';
export const number = value => present(value) ? new Intl.NumberFormat('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) : 'Unavailable';
export const outlook = (value, threshold = 0.25) => !present(value) ? 'Unavailable' : value > threshold ? 'Bullish' : value < -threshold ? 'Bearish' : 'Neutral';
export const absoluteError = (estimate, actual) => present(estimate) && present(actual) ? Math.abs(estimate - actual) : null;
export const rankSignals = stocks => [...stocks].sort((a, b) => {
  const left = present(a.estimate) ? Math.abs(a.estimate) : -Infinity;
  const right = present(b.estimate) ? Math.abs(b.estimate) : -Infinity;
  return (right - left) || (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0);
});
export function filterHistory(rows, { asset = '', from = '', to = '' } = {}) {
  return rows.filter(row => (!asset || row.ticker === asset) && (!from || row.session >= from) && (!to || row.session <= to));
}
export const timestamp = value => value ? new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(value)) + ' UTC' : 'Unavailable';
export const sessionDate = value => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T12:00:00Z'));
