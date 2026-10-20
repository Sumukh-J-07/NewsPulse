# NewsPulse Acceptance Checklist & Sign-Off

This document maps all authoritative acceptance criteria from `NewsPulse_SRS.docx` v1.0 and `NewsPulse_Team_Build_Checklist.docx` to concrete implementation and test evidence.

---

| ID | Acceptance Criterion | Status | Evidence & Test Verification |
| :--- | :--- | :--- | :--- |
| **AC-01** | Produces one next-session index estimate and one estimate per configured stock when valid inputs exist. | **Verified** | Verified in `test_api_overview` and `test_api_stocks` in `tests/test_api.py`. Predictions generated for NIFTY 50 (`^NSEI`) + 8 NSE stocks in LIVE mode, and `DM100` + 8 fictional stocks in SAMPLE mode. |
| **AC-02** | Estimates include explicit percent unit, reference close, horizon, generated time, model version, and outlook label. | **Verified** | Verified in `/api/v1/overview` and `/api/v1/stocks`. Units are `%` for estimated returns and `pp` for errors. |
| **AC-03** | Stocks rank consistently by absolute news-aware estimate with headline evidence or no-news explanation. | **Verified** | Enforced by `ORDER BY ABS(estimated_change_pct) DESC` in `newspulse/api.py`; verified in `test_api_stocks` and browser verification. Stocks without eligible news display explicit *"No eligible news in cutoff window"*. |
| **AC-04** | Actual outcomes and errors use the same reference close and target formula as the original estimate. | **Verified** | Verified in `test_forecast_errors` and `reconcile_pending_predictions` using $100 \times \frac{P_{t+1} - P_t}{P_t}$. Future outcomes are explicitly displayed as **Pending**, never zero. |
| **AC-05** | Evaluation reports MAE, directional accuracy, sample count, and date range on chronological holdout. | **Verified** | Verified on both datasets: LIVE mode evaluated on 54 held-out observations (1.85 pp vs 1.83 pp MAE, 53.7% vs 55.6% accuracy); SAMPLE mode evaluated on 720 observations (1.2942 pp vs 1.2953 pp MAE, 48.9% vs 49.7% accuracy). Verified in `test_api_metrics`. |
| **AC-06** | Provider failures and stale data are visible; missing required inputs do not produce normal forecasts. | **Verified** | Handled in `pipeline_runner.py` via `price_max_age_days` and missing input assertions; tested in `test_adapters_mock.py` and `frontend/tests/domain.test.js`. |
| **AC-07** | Timestamps demonstrate that post-cutoff news and future prices are excluded from prediction features. | **Verified** | Verified in `tests/test_features_leakage.py` (`test_no_future_news_leakage`) and hard leakage assertions in `features.py`. |
| **AC-08** | App can be set up and demoed end-to-end with permitted live data or documented sample dataset. | **Verified** | Verified via `scripts/smoke_test_live.py` (9/9 yfinance symbols and 85 real RSS articles), isolated SQLite databases, and deterministic offline sample mode. |
| **AC-09** | Responsible presentation: no automated trading, personalized financial advice, or claims of certainty. | **Verified** | Explicit "Signals to Watch" and "Market Outlook" phrasing; academic disclaimers present in dashboard and documentation. |
| **AC-10** | Python implementation of data engineering, sentiment analysis, ML modeling, and backend REST API. | **Verified** | 100% Python backend (`FastAPI`, `scikit-learn`, `pandas`, `numpy`, `newspulse-fin-lexicon`). |
| **AC-11** | Frontend completeness: navigation, tables, filters, status indicators, and error states all function. | **Verified** | Human-designed editorial financial research terminal with light-first warm neutral styling, tabular numerals, mode switcher, and clean status badges; 7/7 Node tests pass; visually verified in browser. |
| **AC-12** | Testing and documentation: unit, API, time-series, and UI tests pass; comprehensive documentation provided. | **Verified** | 19/19 pytest backend tests pass; 7/7 frontend domain tests pass; live smoke test passes; full documentation updated. |
