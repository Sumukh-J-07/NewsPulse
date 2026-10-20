# NewsPulse Demonstration & Operator Guide

This guide walks through demonstrating NewsPulse locally, executing live market and news refreshes, running smoke tests, and inspecting both LIVE and SAMPLE operational modes in the research terminal.

---

## 1. Quick Start

### Start the Application
From the repository root:
```bash
source .venv/bin/activate
uvicorn newspulse.api:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000/`** (or `http://127.0.0.1:4173` if running the dedicated Node frontend server via `npm start` in `frontend/`).

---

## 2. Step-by-Step Demonstration Sequence

### Scenario A: Real Live Data Demonstration (NSE Equities + Financial RSS)
1. **Activate LIVE Mode**:
   - In the top header bar, click the **`Live Data`** button (green indicator dot).
   - Observe the live banner update: `LIVE MARKET DATA — Sourced from National Stock Exchange of India (NSE) via Yahoo Finance and verified financial RSS feeds`.
2. **Inspect Index Outlook**:
   - The primary card displays **NIFTY 50 (`^NSEI`)**, with its real reference close (e.g. `22,888.95`), estimated next-session change (`+0.34%`), and outlook label (`BULLISH`).
   - Cutoff timestamp shows the 10:30 UTC regular session cutoff; Forecasting model displays `news_aware_ridge` with commit hash.
3. **Inspect Watchlist Signals & Evidence**:
   - Click **`Signals to Watch`** in the navigation.
   - The watchlist table ranks 8 active NSE large-cap equities (TCS, INFY, RELIANCE, BHARTIARTL, ITC, ICICIBANK, HINDUNILVR, HDFCBANK) by estimated move magnitude.
   - Look at the **Headline Evidence** cards below:
     - Real headlines from *The Economic Times* and *LiveMint* are displayed with publication timestamps and clickable source links (e.g., *"HDFC Bank vs ICICI Bank..."*).
     - Stocks without eligible news in the cutoff window clearly state *"No eligible news in cutoff window"*, proving that no synthetic headlines are fabricated.
4. **Inspect Prediction Ledger**:
   - Click **`Prediction Ledger`**.
   - Notice that next-session forecasts (for tomorrow's session) show **Pending** for Realized Outcome and Abs Error. Historical sessions (yesterday and prior) display reconciled realized percentage changes and signed errors in percentage points.
5. **Inspect Model Evaluation**:
   - Click **`Model Evaluation`**.
   - Review side-by-side empirical performance comparing the baseline vs news-aware Ridge model on 54 held-out test observations.

---

### Scenario B: Offline Deterministic Demonstration (SAMPLE Mode)
1. **Activate SAMPLE Mode**:
   - In the header, click the **`Sample Data (Fictional)`** button (amber indicator dot).
   - Observe the banner update: `SAMPLE DATA — FICTIONAL: Deterministic synthetic market prices and simulated news headlines for demonstration purposes only`.
2. **Review Deterministic Output**:
   - Index updates to **Demo Market 100 (`DM100`)**, with reference close `18,296.77`.
   - Asset table updates to the 8 fictional benchmark stocks (`ALFA`, `BRIO`, `CEDR`, `DUNE`, `ELIO`, `FERN`, `GALE`, `HALO`).
   - Fully runnable without internet connection or external API keys.

---

### Scenario C: Live Pipeline Refresh Demonstration
1. **Frontend Button**:
   - Click the **`↻ Refresh`** button in the top right header.
   - The client dispatches a secure POST to `/api/v1/jobs/refresh?mode=live` with the operator authentication header.
   - An alert banner confirms pipeline execution, updating timestamps and counts.
2. **CLI Live Smoke Test**:
   - In a terminal, run:
     ```bash
     python scripts/smoke_test_live.py
     ```
   - Verifies all 9 yfinance symbols and 2 RSS feeds in under 3 seconds, logging HTTP status and sample headlines.

---

### Scenario D: Edge Cases & Graceful Degradation
- **Stale Price Simulation**: When prices are older than `price_max_age_days` (default 5 trading sessions), the pipeline halts new prediction generation and withholds estimates, flagging inputs as stale.
- **Provider Outage / Missing News**: If RSS feeds fail or contain no articles matching an asset before the cutoff, the asset is predicted using price-only features with news indicators set to zero; no synthetic news is ever injected into LIVE mode.
