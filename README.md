# NewsPulse

Financial-news-informed market research terminal exploring whether headline sentiment adds predictive value over a price-history-only baseline for next-trading-session percentage changes.

---

## 1. Project Overview & Scope

NewsPulse ingests permitted financial headlines and daily price history, deduplicates and links articles to companies, performs transparent financial sentiment analysis in Python, constructs time-series features with strict no-look-ahead controls, trains both a price-only baseline and a news-aware Ridge regression model, and serves predictions, signals, evidence, and evaluation metrics through an interactive, human-designed financial research terminal.

- **Prediction Horizon**: The next regular exchange trading session close-to-close percentage change ($y_{i, t+1} = 100 \times \frac{P_{t+1} - P_t}{P_t}$), not the next calendar day.
- **Signal Threshold**: $\theta = \pm 0.25\text{ percentage points}$ (configurable). Estimates $> +0.25$ pp are Bullish, $< -0.25$ pp are Bearish, and in between $[-0.25, +0.25]$ pp are Neutral.
- **Dual Operational Modes**:
  - **LIVE Mode**: Sourced from actual external market feeds (`yfinance` for NIFTY 50 `^NSEI` + 8 NSE large-cap stocks) and verified Indian financial RSS feeds (*The Economic Times Stocks* & *LiveMint Markets*). Strictly separated database (`data/newspulse_live.db`). Never silently falls back to fictional data.
  - **SAMPLE Mode**: Fully deterministic, reproducible offline synthetic market generator (`DM100` index + 8 fictional equities) running in `data/newspulse_sample.db`. Prominently labelled fictional. Requires zero network access or credentials.
- **Market Universe (NSE Watchlist)**:
  - Index: `NIFTY 50` (`^NSEI`)
  - Equities: `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`, `ICICIBANK.NS`, `HINDUNILVR.NS`, `ITC.NS`, `BHARTIARTL.NS`.
- **Market Timezone**: `Asia/Kolkata`; all stored timestamps normalized to UTC.
- **Boundaries**: Informational academic research tool only. No order execution, no automated trading, no personalized financial advice, and no claims of guaranteed returns.

---

## 2. Technology Stack & Design Architecture

- **Backend**: Python 3.11+ / Python 3.13, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), [scikit-learn](https://scikit-learn.org/), [pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/).
- **Sentiment Analysis**: Transparent VADER-style financial lexicon sentiment scorer with phrase matching, negation detection, and intensifiers (`newspulse-fin-lexicon` v1.0.0). Documented baseline lexicon scorer, not a pretrained LLM.
- **Data Providers**:
  - Sample mode: Fully deterministic offline generator (no API keys or network required).
  - Live mode: `yfinance` adapter with nominal `close` policy, per-symbol success/failure tracking, bounded requests, and timeout handling; plus standard RSS feed parser using Python `urllib` with `certifi` SSL context.
- **Persistence**: SQLite with WAL mode, foreign key integrity, and isolated databases per mode (`data/newspulse_live.db` and `data/newspulse_sample.db`).
- **Frontend**: Editorial Financial Research Terminal. Light-first warm neutral palette (`#f8fafc`), high-contrast slate typography (`#0f172a`), tabular numerals, 1px neutral borders (`#e2e8f0`), compact financial tables, responsive layout, built with vanilla JavaScript, modern CSS, and semantic HTML5. Zero generic AI clichés (no neon cyan glows, glassmorphism, or bubble cards).

---

## 3. Installation & Local Setup

### Prerequisites
- Python 3.11 or newer (tested on Python 3.13)
- Node.js 20 or newer (for frontend testing and optional dedicated static server)

### 1. Clone & Setup Python Environment
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies and package in editable mode
pip install -e backend
pip install pytest httpx certifi
```

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
# NEWSPULSE_MODE=live or NEWSPULSE_MODE=sample
# NEWSPULSE_OPERATOR_TOKEN=newspulse-dev-token
```

---

## 4. Running the Application

### Option A: Run Backend & Frontend Combined (FastAPI — Recommended)
The FastAPI server serves both the REST API and the frontend dashboard:
```bash
source .venv/bin/activate
uvicorn newspulse.api:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000/`** or **`http://127.0.0.1:8000/static/index.html`** in your browser.

### Option B: Run Frontend via Dedicated Node Server
```bash
# Terminal 1 (Backend API):
source .venv/bin/activate
uvicorn newspulse.api:app --host 127.0.0.1 --port 8000

# Terminal 2 (Frontend Dev Server):
cd frontend
npm start
```
Open **`http://127.0.0.1:4173`** in your browser.

---

## 5. Live Ingestion & Smoke Testing

### Standalone Live Provider Smoke Test
NewsPulse includes an automated live smoke test script that verifies network connectivity, provider symbol mappings, rate limits, and response parsing against genuine market and RSS providers:
```bash
source .venv/bin/activate
python scripts/smoke_test_live.py
```
This script queries yfinance for `^NSEI` and the 8 configured NSE stocks, fetches live headlines from Economic Times and LiveMint, and outputs a per-symbol, per-source status report.

### Triggering Manual Live Pipeline Refresh
To trigger a manual pipeline run from the CLI:
```bash
# Live mode refresh (requires valid operator token)
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/refresh?mode=live" \
  -H "X-Operator-Token: newspulse-dev-token"

# Sample mode refresh
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/refresh?mode=sample" \
  -H "X-Operator-Token: newspulse-dev-token"
```

---

## 6. Running Automated Tests

### Python Backend & Model Tests (pytest)
```bash
source .venv/bin/activate
pytest tests/ -v
```
*Executes 19 unit and integration tests covering provider normalization, RSS date parsing, error handling, formulas, deduplication, sentiment analysis, time-series leakage prevention, multi-mode API switching, and token-based refresh security.*

### Frontend Tests (Node.js Test Runner)
```bash
cd frontend
npm test
```
*Executes 7 frontend domain tests covering percentage point formatting, outlook boundaries, ranking logic, history filters, required-input failure withholding, and sample evidence cutoff handling.*

---

## 7. Key Documentation

- [REST API Specification](docs/API.md)
- [System Architecture & Dataflow](docs/ARCHITECTURE.md)
- [Model Methodology & Chronological Evaluation](docs/MODEL_EVALUATION.md)
- [Demonstration & Operator Guide](docs/DEMO_GUIDE.md)
- [SRS Acceptance Checklist](docs/ACCEPTANCE_CHECKLIST.md)
- [Implementation Audit & Inventory](docs/IMPLEMENTATION_AUDIT.md)

---

## 8. Known Limitations & Research Integrity

1. **Daily Returns Volatility**: Daily stock percentage moves have high noise-to-signal ratios. While sentiment features provide directional information, they do not guarantee profitability.
2. **Provider Delays & Limits**: Public RSS feeds and Yahoo Finance are subject to external rate limits, upstream outages, and session delays. If an upstream outage occurs, NewsPulse flags the affected assets as stale or partial-failure and withholds predictions rather than inventing prices.
3. **Attribution & Entity Linking**: Entity linking associates verified headlines with companies via aliases, but does not assert causal relationships. Headlines without timestamps preceding the daily cutoff are excluded to prevent look-ahead bias.
4. **Lexicon Baseline**: The sentiment model uses an explainable financial lexicon, not a black-box deep learning model. All scoring rules are deterministic and transparent.
