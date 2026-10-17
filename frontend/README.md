# NewsPulse frontend prototype

Prathyush's independently buildable frontend for the NewsPulse academic project. All market names, companies, headlines, prices, forecasts and evaluation metrics are fictional fixtures. This is not a connected prediction system.

## Run locally

Requires Node.js with ES modules and the built-in test runner (Node 20 or newer). No package installation is needed.

```powershell
cd frontend
node server.mjs
```

Open http://127.0.0.1:4173. Stop with Ctrl+C. Run checks with `node --test` from the same folder. The development server binds only to localhost.

## What is implemented

- Overview, signals and fictional headline evidence, prediction history with asset/date filters, and illustrative model evaluation.
- Responsive layout, semantic tables, navigation, keyboard focus, skip link, status announcements and reduced-motion support.
- Scenarios for ready, resolved, no eligible news, stale required inputs, provider failure, pipeline failure, empty current predictions and persistent loading.
- Pure helpers for percentages, percentage-point errors, outlook boundaries, ranking and history filtering.
- A separate asynchronous fixture loader, including protection against an older request overwriting a newer selection.

Run these commands from the repository root. If port 4173 is already occupied, stop the other local prototype or set `PORT` before starting (PowerShell: `$env:PORT = '4174'`).

HTML, CSS and native JavaScript modules are a reversible prototype choice, not an agreed final team stack. Python is the anticipated backend language. Its framework, the market, providers and API schemas remain undecided.

## Files

- `src/app.js`: views, navigation, filters and scenario switching.
- `src/styles.css`: responsive styling.
- `src/domain.js`: formatting and domain helpers.
- `src/data.js`: fictional fixtures and asynchronous data adapter.
- `tests/domain.test.js`: domain boundaries and fixture behavior.
- `docs/api-proposal.md`: proposed integration decisions, not a finalized API schema.
- `docs/prathyush-checklist.md`: completed frontend work and remaining responsibilities.

## Demo

1. Open Overview and inspect the reference close, forecast session, generated timestamp and model identity.
2. Open Signals to watch. BRIO ranks first because its negative estimate has the largest absolute magnitude. CEDR is neutral at exactly +0.25%.
3. Open Prediction history, apply an asset/date filter, then inspect pending outcomes. Reset the filters.
4. Select Resolved outcomes; ALFA's +1.20% estimate and +0.80% actual give 0.40 pp error.
5. Inspect the sample evaluation. The sample values do not demonstrate real model improvement.
6. Select stale or provider failure: current estimates are withheld, retained inputs are labelled, and old history remains.
7. Inspect no news, empty and loading scenarios, plus narrow-screen layout and keyboard navigation.

## Glossary

Reference close is the price used as the forecast starting point. Target session is the next regular exchange session supplied by the backend, never a date the browser computes by adding one day. Estimate and actual are percentage changes. Absolute error and MAE use percentage points. Outlook is derived using a configurable dead band; the prototype uses 0.25 pp. Baseline means the price-only comparison model. Pending means the outcome is unresolved, not zero.

## Remaining integration work

Agree the real market, timezone, calendar, close policy, freshness limits, threshold configuration and API schemas with Sumukh. Map real responses into the view model in `src/data.js` and replace the artificial scenario selector with development-only controls. Add permitted real headline URLs and attribution. Wire baseline estimates as well as metrics when supplied. Validate real HTTP failures and all displayed values against backend responses. Complete an API integration test as Prathyush's small backend contribution. Sumukh still owns the real freshness UI contribution; the current placeholder is not counted as his work.

The retained historical rows in the empty scenario are intentional: there are no current predictions, but previous sessions can still exist. The no-news fixture assumes forecasting can continue with valid prices; this is a proposed policy awaiting agreement. UTC is only a demonstration timezone. The fixed evaluation summary is a separate illustrative fixture, not calculated from the small history sample.
