# NewsPulse API Specification (v1.0)

Base URL: `http://127.0.0.1:8000/api/v1`

All read endpoints accept an optional `?mode=live` or `?mode=sample` query parameter. If omitted, the server defaults to the mode configured in `NEWSPULSE_MODE` (or `sample` by default).

---

### 1. `GET /overview?mode=[live|sample]`
Returns the latest market index prediction, reference close, generated timestamp, cutoff, horizon, outlook label, and input data freshness.

**Response (200 OK — Live Mode):**
```json
{
  "mode": "live",
  "data_origin": "live",
  "index": {
    "asset_id": "^NSEI",
    "ticker": "^NSEI",
    "name": "NIFTY 50",
    "exchange": "NSE",
    "close": 22888.95,
    "estimate": 0.34
  },
  "reference_session": "2026-10-19",
  "session": "2026-10-20",
  "horizon": "next_regular_session",
  "outlook": "Bullish",
  "threshold_pp": 0.25,
  "cutoff": "2026-10-19T10:30:00Z",
  "generated": "2026-10-20T12:16:34Z",
  "model": "news_aware_ridge (1.0.0+151e8e93)",
  "data_status": "ready",
  "scenario": "ready",
  "blocked": false,
  "timezone": "Asia/Kolkata",
  "freshness": {
    "latest_price_session": "2026-10-19",
    "latest_news_published": "2026-10-20T12:03:15Z"
  }
}
```

---

### 2. `GET /stocks?date=YYYY-MM-DD&mode=[live|sample]`
Returns configured stocks ranked by descending absolute news-aware estimated change.

**Query Parameters:**
- `date` *(optional)*: Prediction session in `YYYY-MM-DD` format (defaults to latest published session).
- `mode` *(optional)*: `live` or `sample`.

**Response (200 OK):**
```json
[
  {
    "ticker": "TCS",
    "name": "Tata Consultancy Services",
    "close": 2460.9,
    "estimate": -1.45,
    "outlook": "Bearish",
    "actual": null,
    "error": null,
    "articles": 1,
    "sentiment_summary": {
      "mean": -0.15,
      "positive": 0,
      "negative": 1
    },
    "headline": "Global Customer Technical Support Service Market Report 2026-2030...",
    "source": "Yahoo Finance RSS",
    "url": "https://finance.yahoo.com/news/...",
    "published": "2026-10-19T09:35:00Z",
    "model": "news_aware_ridge (1.0.0+151e8e93)"
  }
]
```

---

### 3. `GET /predictions?asset=&from=&to=&mode=[live|sample]`
Returns historical prediction ledger, reference close, estimates, actual outcomes, and signed/absolute errors.

**Query Parameters:**
- `asset` *(optional)*: Asset symbol/ID (e.g., `TCS`, `^NSEI`, `ALFA`).
- `from` *(optional)*: Earliest session in `YYYY-MM-DD`.
- `to` *(optional)*: Latest session in `YYYY-MM-DD`.
- `mode` *(optional)*: `live` or `sample`.

---

### 4. `GET /metrics?from=&to=&mode=[live|sample]`
Returns held-out chronological model evaluation for both the baseline and news-aware models evaluated on identical test observations.

**Response (200 OK — Live Mode):**
```json
{
  "mode": "live",
  "data_origin": "live",
  "metrics": [
    {
      "role": "baseline",
      "name": "Price-only baseline",
      "model_identifier": "baseline_price_ridge (1.0.0+ef575f24)",
      "mae": 1.85,
      "accuracy": 53.7,
      "count": 54
    },
    {
      "role": "news_aware",
      "name": "News-aware model",
      "model_identifier": "news_aware_ridge (1.0.0+151e8e93)",
      "mae": 1.83,
      "accuracy": 55.6,
      "count": 54
    }
  ],
  "evaluation_period": {
    "start": "2026-10-12",
    "end": "2026-10-19",
    "description": "Chronological holdout split (unshuffled 20% test period)"
  }
}
```

---

### 5. `GET /status?mode=[live|sample]`
Returns database record counts, data freshness timestamps, exchange metadata, and execution status of recent pipeline runs.

**Response (200 OK):**
```json
{
  "mode": "live",
  "data_origin": "live",
  "market": "National Stock Exchange of India",
  "exchange": "NSE",
  "timezone": "Asia/Kolkata",
  "counts": {
    "daily_prices": 1620,
    "articles": 108,
    "predictions": 126,
    "outcomes": 108
  },
  "freshness": {
    "latest_price_session": "2026-10-19",
    "price_retrieved_at": "2026-10-20T12:16:27.369314+00:00",
    "latest_news_published": "2026-10-20T12:03:15Z"
  },
  "recent_runs": [...]
}
```

---

### 6. `POST /jobs/refresh?mode=[live|sample]`
Triggers an on-demand data ingestion, feature generation, prediction, and evaluation run. Protected by `X-Operator-Token` header.

**Headers:**
- `X-Operator-Token`: Configured operator token (default: `newspulse-dev-token`).

**Response (200 OK):**
```json
{
  "message": "Pipeline executed successfully",
  "mode": "live",
  "results": {
    "status": "success",
    "ingested_prices": 90,
    "ingested_articles": 85,
    "predictions_generated": 18,
    "outcomes_resolved": 18
  }
}
```
