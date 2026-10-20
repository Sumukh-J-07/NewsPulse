# NewsPulse Architecture and System Design

NewsPulse is an academic financial research prototype designed to estimate next-trading-session percentage changes for an index and a watchlist of stocks, evaluate whether news sentiment improves on a price-history baseline, and display signals, evidence, and evaluation metrics in a responsive web dashboard.

---

## 1. High-Level Architecture

```
[ Financial News RSS / Sample Data ]       [ Market Prices (yfinance / Sample) ]
                  │                                         │
                  ▼                                         ▼
       [ News Ingestion & Dedup ]               [ Price Ingestion & DB Cache ]
                  │                                         │
                  ▼                                         ▼
      [ Entity Linking (FR-05) ]                  [ Normalized OHLCV (FR-03) ]
                  │                                         │
                  ▼                                         │
    [ Lexicon Sentiment Scorer (FR-06) ]                    │
                  │                                         │
                  └─────────────────┬───────────────────────┘
                                    ▼
                    [ Feature Engineering (FR-07, FR-08) ]
                    (Trailing returns, vol, news count, mean/recency sentiment)
                    Strict No-Look-Ahead Cutoff Enforcement
                                    │
                                    ▼
             [ Chronological Train/Val/Test Split (SRS §4.3) ]
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
        [ Baseline Ridge Model ]            [ News-Aware Ridge Model ]
        (Price-history features)            (Price + News sentiment)
                  │                                   │
                  └─────────────────┬─────────────────┘
                                    ▼
            [ SQLite Persistence: Predictions & Outcomes (FR-13, 14) ]
                                    │
                                    ▼
                   [ Python FastAPI REST API (SRS §5.2) ]
                   (/overview, /stocks, /predictions, /metrics, /status)
                                    │
                                    ▼
                [ Web Dashboard (HTML5, Vanilla CSS & JS) ]
```

---

## 2. Core Modules

1. **`newspulse.settings`**: Configures runtime settings, watchlist JSON loader, and parameter boundaries.
2. **`newspulse.calendar`**: Exchange calendar managing session arithmetic, holiday filtering, local/UTC timezones, and regular-session cutoffs.
3. **`newspulse.formulas`**: Mathematical functions for close-to-close percentage change, outlook signal classification (±0.25 pp default threshold), signed and absolute errors, MAE, and directional accuracy.
4. **`newspulse.db`**: Schema migrations and SQLite connection management for assets, daily prices, articles, article links, model runs, forecast runs, predictions, outcomes, and pipeline audit logs.
5. **`newspulse.processing.dedup`**: Deduplication using source IDs, normalized URLs (stripping query tracking parameters), and normalized headlines.
6. **`newspulse.processing.linking`**: Multi-tier company linking using trusted provider tags, ticker symbols, full names, and weak aliases with conflict-avoidance rules.
7. **`newspulse.processing.sentiment`**: VADER-style financial lexicon sentiment scorer handling phrases, negations, intensifiers, and neutral defaults.
8. **`newspulse.processing.features`**: Daily feature snapshot generation combining trailing returns and time-decayed recency-weighted sentiment. Hard assertions prevent future data leakage.
9. **`newspulse.modeling.models`**: Ridge regressions fitted on chronological splits (60% train, 20% validation, 20% test) with validation-based regularization parameter selection.
10. **`newspulse.api`**: FastAPI REST server exposing documented endpoints with CORS and static file serving, supporting dynamic dispatch between `live` and `sample` contexts.

---

## 3. Multi-Mode Architecture & Data Isolation

NewsPulse implements strict physical data isolation between operational modes:

| Dimension | LIVE Mode | SAMPLE Mode |
| :--- | :--- | :--- |
| **Database File** | `data/newspulse_live.db` | `data/newspulse_sample.db` |
| **Market Coverage** | NIFTY 50 (`^NSEI`) + 8 NSE Equities | Demo Market 100 (`DM100`) + 8 Fictional Equities |
| **Market Data Provider**| `yfinance` daily OHLCV (unadjusted close for nominal levels; bounded retries) | Deterministic synthetic geometric Brownian motion generator |
| **News Provider** | Verified public RSS feeds (*Economic Times*, *LiveMint*) | Deterministic synthetic headline generator |
| **Provenance Label** | `LIVE MARKET DATA` (green indicator dot) | `SAMPLE DATA — FICTIONAL` (amber indicator dot) |
| **Network Requirement**| Requires outbound HTTPS access to yfinance & RSS | Fully offline; zero external network access required |
| **Degradation Policy** | Partial symbol failures logged; affected forecasts withheld | Fully deterministic; guaranteed 100% completion |

Both modes share identical mathematical formulas, entity linking logic, feature engineering routines, and Ridge regression pipelines, ensuring consistent evaluation behavior.

---

## 4. Live Ingestion & Pipeline Orchestration

The live ingestion workflow follows an audited 10-step sequence:
1. **Pipeline Run Initialization**: Allocates unique `run_id`, records start timestamp and requested mode.
2. **Provider Data Retrieval**: Fetches historical OHLCV from yfinance with timeout/retry bounds, plus recent XML feeds from configured RSS sources with SSL context validation.
3. **Price Normalization & Deduplication**: Cleans numeric fields, verifies trading day alignment, and persists nominal close and return-adjusted close.
4. **Article Normalization & Deduplication**: Canonicalizes URLs (stripping query parameters), verifies publication timestamps, and indexes source IDs.
5. **Entity Linking**: Maps articles to assets via ticker symbols, exact company names, and high-confidence aliases.
6. **Sentiment Scoring**: Applies `newspulse-fin-lexicon` v1.0.0 to eligible headlines.
7. **Feature Construction**: Assembles trailing returns and news sentiment with strict chronological cutoff enforcement ($T \le \text{cutoff}$).
8. **Forecasting**: Generates next-session percentage change estimates using trained Ridge models only when all required feature inputs are present.
9. **Outcome Reconciliation**: Evaluates previous predictions against realized session closing prices, recording signed error and absolute error.
10. **Evaluation & Audit Logging**: Updates holdout test MAE and directional accuracy metrics and persists pipeline execution summaries.
