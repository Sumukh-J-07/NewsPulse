# NewsPulse

Academic research dashboard exploring whether financial news sentiment improves next-session percentage-change estimates compared with a price-history-only baseline.

## Team responsibilities

- Prathyush: frontend, API integration, UI documentation and a small backend integration contribution.
- Sumukh: data ingestion, storage, sentiment, models, evaluation and backend API; a small UI contribution.
- Shared: API contracts, project decisions, reviews, integration and demo.

The initial scope is one market index and 5–10 stocks. Market, providers and exact API schemas remain to be agreed. Python is the anticipated backend language; its framework is not yet fixed.

Feature work is reviewed through pull requests. The initial frontend prototype is developed on `frontend/prototype`.

## Frontend prototype

The `frontend/` directory contains the standalone sample-data dashboard. It uses native HTML, CSS and JavaScript; it does not require a Python backend yet. All forecasts, headlines and evaluation metrics are fictional.

From the repository root, with Node.js 20 or newer installed:

```sh
cd frontend
npm start
```

Open http://127.0.0.1:4173. No dependency installation is needed. Run `npm test` from `frontend/` to check domain logic and fixture scenarios.

See [frontend setup and demo](frontend/README.md), [API proposal](frontend/docs/api-proposal.md) and [Prathyush's checklist](frontend/docs/prathyush-checklist.md). This prototype is not the completed integrated SRS implementation.
