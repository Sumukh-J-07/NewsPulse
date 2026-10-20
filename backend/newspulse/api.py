"""FastAPI REST application serving the versioned NewsPulse API contract."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .calendar import UTC, MarketCalendar
from .db import connect, init_db, loads, session, sync_assets
from .formulas import evaluate, signal_label
from .processing.pipeline_runner import reconcile_pending_predictions, run_full_pipeline
from .settings import REPO_ROOT, Settings, Watchlist, load_settings, load_watchlist

CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"

logger = logging.getLogger(__name__)

# Application state
app_settings: Settings | None = None
app_watchlist: Watchlist | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_settings, app_watchlist
    app_settings = load_settings()
    app_watchlist = load_watchlist(app_settings.watchlist_path)

    # Initialize DB & sync assets
    with session(app_settings.db_path) as conn:
        init_db(conn)
        sync_assets(conn, app_watchlist)

    logger.info("NewsPulse API starting in mode: %s", app_settings.mode)

    # Auto-run pipeline in sample mode if database has no predictions yet
    with session(app_settings.db_path) as conn:
        has_pred = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        if has_pred == 0 and app_settings.mode == "sample":
            logger.info("Empty database in sample mode; seeding initial pipeline run...")
            run_full_pipeline(app_settings, app_watchlist)

    yield


app = FastAPI(
    title="NewsPulse API",
    version="1.0.0",
    description="News-informed market outlook and stock change estimation research dashboard.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_settings() -> Settings:
    global app_settings
    if app_settings is None:
        app_settings = load_settings()
    return app_settings


def get_watchlist() -> Watchlist:
    global app_watchlist
    if app_watchlist is None:
        st = get_settings()
        app_watchlist = load_watchlist(st.watchlist_path)
    return app_watchlist


def get_context(mode: Optional[str] = Query(None)):
    """Resolve mode-specific settings, watchlist, and database connection ('live' or 'sample')."""
    base_settings = get_settings()
    target_mode = (mode or base_settings.mode).strip().lower()
    if target_mode not in ("live", "sample"):
        target_mode = base_settings.mode

    target_wl_path = CONFIG_DIR / ("watchlist.nse.json" if target_mode == "live" else "watchlist.sample.json")
    target_db_path = DATA_DIR / f"newspulse_{target_mode}.db"

    st = Settings(
        mode=target_mode,
        db_path=target_db_path,
        watchlist_path=target_wl_path,
        threshold_pp=base_settings.threshold_pp,
        price_max_age_days=base_settings.price_max_age_days,
        news_max_age_hours=base_settings.news_max_age_hours,
        recency_half_life_hours=base_settings.recency_half_life_hours,
        min_train_sessions=base_settings.min_train_sessions,
        min_test_sessions=base_settings.min_test_sessions,
        price_history_days=base_settings.price_history_days,
        http_timeout_seconds=base_settings.http_timeout_seconds,
        http_max_retries=base_settings.http_max_retries,
        refresh_min_interval_seconds=base_settings.refresh_min_interval_seconds,
        operator_token=base_settings.operator_token,
    )
    wl = load_watchlist(target_wl_path)
    conn = connect(target_db_path)
    init_db(conn)
    sync_assets(conn, wl)
    try:
        yield st, wl, conn
    finally:
        conn.close()


@app.get("/api/v1/overview")
def get_overview(ctx=Depends(get_context)):
    """Return market index overview, reference close, estimate, outlook label, horizon and freshness."""
    settings, watchlist, conn = ctx
    index_asset = watchlist.index

    # Get latest published forecast for index
    row = conn.execute(
        """SELECT p.*, o.actual_change_pct, o.absolute_error_pct_points
           FROM predictions p
           LEFT JOIN outcomes o ON o.prediction_id = p.prediction_id
           WHERE p.asset_id = ? AND p.origin = 'forecast' AND p.model_role = 'news_aware'
           ORDER BY p.reference_session DESC, p.created_at DESC
           LIMIT 1""",
        (index_asset.asset_id,)
    ).fetchone()

    # Data freshness checks
    latest_price = conn.execute(
        "SELECT MAX(session_date), MAX(retrieved_at) FROM daily_prices WHERE asset_id = ?",
        (index_asset.asset_id,)
    ).fetchone()

    latest_news = conn.execute(
        "SELECT MAX(published_at_utc) FROM articles WHERE is_duplicate = 0"
    ).fetchone()

    if not row:
        return {
            "index": {
                "asset_id": index_asset.asset_id,
                "ticker": index_asset.ticker,
                "name": index_asset.display_name,
                "exchange": index_asset.exchange,
                "close": None,
                "estimate": None,
            },
            "reference_session": None,
            "session": None,
            "horizon": "next_regular_session",
            "outlook": "Unavailable",
            "threshold_pp": settings.threshold_pp,
            "cutoff": None,
            "generated": None,
            "model": "None",
            "data_status": "empty",
            "scenario": "empty",
            "blocked": True,
            "timezone": watchlist.market.timezone,
            "mode": settings.mode,
            "data_origin": settings.mode,
            "message": "No forecast run published yet. Run ingestion and prediction pipeline."
        }

    return {
        "index": {
            "asset_id": index_asset.asset_id,
            "ticker": index_asset.ticker,
            "name": index_asset.display_name,
            "exchange": index_asset.exchange,
            "close": row["reference_close"],
            "estimate": row["estimated_change_pct"],
        },
        "reference_session": row["reference_session"],
        "session": row["prediction_session"],
        "horizon": row["horizon"],
        "outlook": row["label"].capitalize(),
        "threshold_pp": row["threshold_pp"],
        "cutoff": row["cutoff_at"],
        "generated": row["created_at"],
        "model": f"{row['model_name']} ({row['model_version']})",
        "data_status": row["data_status"],
        "scenario": "ready" if row["data_status"] == "ready" else row["data_status"],
        "blocked": row["data_status"] == "stale",
        "timezone": watchlist.market.timezone,
        "mode": settings.mode,
        "data_origin": row["data_origin"],
        "provider": "yfinance" if settings.mode == "live" else "sample_generator",
        "freshness": {
            "latest_price_session": latest_price[0] if latest_price else None,
            "latest_news_published": latest_news[0] if latest_news else None,
        }
    }


@app.get("/api/v1/stocks")
def get_stocks(date: Optional[str] = Query(None), ctx=Depends(get_context)):
    """Return configured stock signals ranked by descending absolute news-aware estimate."""
    settings, watchlist, conn = ctx
    # Find latest prediction session if date not provided
    if not date:
        s_row = conn.execute(
            "SELECT MAX(prediction_session) FROM predictions WHERE origin = 'forecast'"
        ).fetchone()
        date = s_row[0] if s_row and s_row[0] else None

    if not date:
        return []

    # Query all active stocks for this session
    rows = conn.execute(
        """SELECT p.*, a.display_name, a.ticker as asset_ticker,
                  o.actual_change_pct, o.absolute_error_pct_points
           FROM predictions p
           JOIN assets a ON a.asset_id = p.asset_id
           LEFT JOIN outcomes o ON o.prediction_id = p.prediction_id
           WHERE p.prediction_session = ? AND p.model_role = 'news_aware' AND a.asset_type = 'stock'
           ORDER BY ABS(p.estimated_change_pct) DESC, p.asset_id ASC""",
        (date,)
    ).fetchall()

    results = []
    for r in rows:
        snapshot = loads(r["feature_snapshot"], {})
        news_inputs = snapshot.get("news_inputs", {})

        # Fetch top headline evidence
        top_art = conn.execute(
            """SELECT a.headline, a.source, a.published_at_utc, a.url
               FROM article_links l
               JOIN articles a ON a.article_id = l.article_id
               WHERE l.asset_id = ? AND a.published_at_utc <= ? AND a.is_duplicate = 0
               ORDER BY a.published_at_utc DESC
               LIMIT 1""",
            (r["asset_id"], r["cutoff_at"])
        ).fetchone()

        results.append({
            "ticker": r["asset_id"],
            "name": r["display_name"],
            "close": r["reference_close"],
            "estimate": r["estimated_change_pct"],
            "outlook": r["label"].capitalize(),
            "actual": r["actual_change_pct"],
            "error": r["absolute_error_pct_points"],
            "articles": news_inputs.get("news_count", 0),
            "sentiment_summary": {
                "mean": news_inputs.get("news_mean_sentiment"),
                "positive": news_inputs.get("news_positive_count", 0),
                "negative": news_inputs.get("news_negative_count", 0),
            },
            "headline": top_art["headline"] if top_art else None,
            "source": top_art["source"] if top_art else None,
            "url": top_art["url"] if top_art else None,
            "published": top_art["published_at_utc"] if top_art else None,
            "model": f"{r['model_name']} ({r['model_version']})",
            "data_origin": r["data_origin"],
        })

    return results


@app.get("/api/v1/predictions")
def get_predictions(
    asset: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    ctx=Depends(get_context)
):
    """Return historical prediction ledger and outcomes with validated asset and date filters."""
    settings, watchlist, conn = ctx
    query = """
        SELECT p.prediction_session as session, p.asset_id as ticker, p.reference_close as close,
               p.estimated_change_pct as estimate, p.label, p.model_name, p.model_version,
               o.actual_change_pct as actual, o.absolute_error_pct_points as error, p.data_origin
        FROM predictions p
        LEFT JOIN outcomes o ON o.prediction_id = p.prediction_id
        WHERE p.model_role = 'news_aware'
    """
    params = []
    if asset:
        query += " AND p.asset_id = ?"
        params.append(asset.upper())
    if from_date:
        query += " AND p.prediction_session >= ?"
        params.append(from_date)
    if to_date:
        query += " AND p.prediction_session <= ?"
        params.append(to_date)

    query += " ORDER BY p.prediction_session DESC, p.asset_id ASC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    return [
        {
            "session": r["session"],
            "ticker": r["ticker"],
            "close": r["close"],
            "estimate": r["estimate"],
            "actual": r["actual"],
            "error": r["error"],
            "model": f"{r['model_name']} · {r['model_version']}",
            "data_origin": r["data_origin"],
        }
        for r in rows
    ]


@app.get("/api/v1/metrics")
def get_metrics(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    ctx=Depends(get_context)
):
    """Return comparative evaluation metrics (MAE in pp, directional accuracy) for baseline vs news-aware models."""
    settings, watchlist, conn = ctx
    models = ["baseline", "news_aware"]
    results = []

    # Get held-out date range
    dates_row = conn.execute(
        """SELECT MIN(p.prediction_session), MAX(p.prediction_session)
           FROM predictions p
           JOIN outcomes o ON o.prediction_id = p.prediction_id
           WHERE p.origin = 'holdout_backtest'"""
    ).fetchone()
    min_date = dates_row[0] if dates_row else None
    max_date = dates_row[1] if dates_row else None

    for role in models:
        q = """
            SELECT p.estimated_change_pct, o.actual_change_pct, p.model_name, p.model_version
            FROM predictions p
            JOIN outcomes o ON o.prediction_id = p.prediction_id
            WHERE p.model_role = ? AND p.origin = 'holdout_backtest'
        """
        p_params = [role]
        if from_date:
            q += " AND p.prediction_session >= ?"
            p_params.append(from_date)
        if to_date:
            q += " AND p.prediction_session <= ?"
            p_params.append(to_date)

        rows = conn.execute(q, p_params).fetchall()
        if rows:
            est_list = [r["estimated_change_pct"] for r in rows]
            act_list = [r["actual_change_pct"] for r in rows]
            m_res = evaluate(est_list, act_list)
            m_name = "Price-only baseline" if role == "baseline" else "News-aware model"
            results.append({
                "role": role,
                "name": m_name,
                "model_identifier": f"{rows[0]['model_name']} ({rows[0]['model_version']})",
                "mae": round(m_res["mae_pp"], 4) if m_res["mae_pp"] is not None else None,
                "accuracy": round(m_res["directional_accuracy"] * 100.0, 1) if m_res["directional_accuracy"] is not None else None,
                "count": m_res["sample_count"],
            })
        else:
            results.append({
                "role": role,
                "name": "Price-only baseline" if role == "baseline" else "News-aware model",
                "model_identifier": "Not trained",
                "mae": None,
                "accuracy": None,
                "count": 0,
            })

    return {
        "metrics": results,
        "mode": settings.mode,
        "data_origin": settings.mode,
        "evaluation_period": {
            "start": min_date,
            "end": max_date,
            "description": f"Chronological holdout split ({settings.mode.upper()} data; 20% test period)"
        }
    }


@app.get("/api/v1/status")
def get_status(ctx=Depends(get_context)):
    """Return pipeline execution history, ingestion stats, and data freshness."""
    settings, watchlist, conn = ctx

    runs = conn.execute(
        "SELECT * FROM pipeline_runs ORDER BY run_id DESC LIMIT 10"
    ).fetchall()

    prices_count = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
    articles_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    preds_count = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    outcomes_count = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]

    latest_price = conn.execute("SELECT MAX(session_date), MAX(retrieved_at) FROM daily_prices").fetchone()
    latest_news = conn.execute("SELECT MAX(published_at_utc) FROM articles").fetchone()

    return {
        "mode": settings.mode,
        "data_origin": settings.mode,
        "market": watchlist.market.name,
        "exchange": watchlist.market.exchange,
        "timezone": watchlist.market.timezone,
        "counts": {
            "daily_prices": prices_count,
            "articles": articles_count,
            "predictions": preds_count,
            "outcomes": outcomes_count,
        },
        "freshness": {
            "latest_price_session": latest_price[0] if latest_price else None,
            "price_retrieved_at": latest_price[1] if latest_price else None,
            "latest_news_published": latest_news[0] if latest_news else None,
        },
        "recent_runs": [
            {
                "run_id": r["run_id"],
                "stage": r["stage"],
                "status": r["status"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "input_count": r["input_count"],
                "output_count": r["output_count"],
                "error": r["error_summary"],
            }
            for r in runs
        ]
    }


@app.post("/api/v1/jobs/refresh")
def post_refresh(
    mode: Optional[str] = Query(None),
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token")
):
    """Trigger manual data refresh and model prediction run. Protected by operator token."""
    ctx_gen = get_context(mode)
    settings, watchlist, _ = next(ctx_gen)

    expected_token = settings.operator_token or "newspulse-dev-token"
    if x_operator_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid operator token. Pass X-Operator-Token header matching configured token or 'newspulse-dev-token'."
        )

    res = run_full_pipeline(settings, watchlist)
    return {"message": "Pipeline executed successfully", "mode": settings.mode, "results": res}


# Mount frontend directory for full-stack local execution
frontend_dir = REPO_ROOT / "frontend"
if frontend_dir.exists():
    @app.get("/", include_in_schema=False)
    @app.head("/", include_in_schema=False)
    def get_root_index():
        return FileResponse(frontend_dir / "index.html")

    if (frontend_dir / "src").exists():
        app.mount("/src", StaticFiles(directory=str(frontend_dir / "src")), name="frontend_src")
    app.mount("/static", StaticFiles(directory=str(frontend_dir), html=True), name="frontend_static")
