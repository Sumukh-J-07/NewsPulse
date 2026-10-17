# Frontend API proposal awaiting agreement

This document records frontend needs. It does not freeze field names or direct Sumukh to use a particular backend implementation. The internal fields in `src/data.js` are a view model, not wire-format promises.

## Proposed endpoint mapping

| Suggested route | Frontend needs |
| --- | --- |
| GET /api/v1/overview | Asset identity, reference close/session, estimate or explicit unavailable state, forecast session, cutoff, generation time, market timezone, model/version, freshness and threshold |
| GET /api/v1/stocks?date=YYYY-MM-DD | Same prediction context per asset, news-aware estimate, baseline estimate where available, headline evidence/count, actual/error when resolved |
| GET /api/v1/predictions?asset=&from=&to= | Target session, asset, model/version, estimate, nullable outcome and error, documented filters |
| GET /api/v1/metrics?from=&to= | Both models, MAE in pp, directional accuracy with documented units, sample counts, identical eligible test rows, test dates and exclusions |
| GET /api/v1/status | Safe run status, ingestion/prediction times, source freshness and failure reason |

## Decisions to settle before real integration

1. Exact JSON schemas, versioning, error code/message and HTTP status behavior.
2. Percent values: 1.25 means 1.25%; errors are pp. Decide whether directional accuracy is a fraction or a percentage.
3. Nullable outcomes, explicitly unavailable forecasts, stale retained inputs versus valid published predictions, and no-news policy.
4. Server-provided target session and market timezone; UTC/offset timestamps; price adjustment policy.
5. Configurable threshold, exact boundary neutrality and deterministic ranking ties (prototype proposes ascending ticker).
6. Query validation, date meaning, inclusive boundaries, pagination if needed, and model selection.
7. Allowed source URLs, attribution, headline retention and evidence for the exact prediction cutoff.
8. How both model estimates are exposed. The prototype currently displays news-aware estimates and a comparison metric table.

Required agreed fixtures: one index, at least two stocks, pending and resolved outcomes, no news, empty results, stale required input, provider failure and pipeline failure. The prototype offers five fictional stocks for frontend review. Sumukh validates the real contract before integration.

## Ownership boundary

Prathyush implements presentation, client data mapping, filtering, accessible states and a bounded integration test. Sumukh supplies backend validation, ingestion, models, calendar logic, predictions, reconciliation and metric calculation. Provider credentials never belong in browser code.
