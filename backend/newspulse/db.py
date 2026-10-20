"""SQLite persistence: schema migrations, connection helper and asset sync.

The database file is persistent (default ``data/newspulse_<mode>.db``). Each
request opens a short-lived connection to the same file; the schema is created
or migrated once at startup by :func:`init_db`.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .settings import Watchlist

SCHEMA_VERSION = 1

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('index', 'stock')),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS daily_prices (
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    session_date TEXT NOT NULL,
    open REAL, high REAL, low REAL,
    close REAL,
    adjusted_close REAL,
    volume REAL,
    provider TEXT NOT NULL,
    price_basis TEXT NOT NULL,
    data_origin TEXT NOT NULL CHECK (data_origin IN ('sample', 'live')),
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (asset_id, session_date)
);

CREATE TABLE IF NOT EXISTS articles (
    article_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    ingest_key TEXT NOT NULL,
    url TEXT,
    normalized_url TEXT,
    headline TEXT,
    published_at_utc TEXT,
    source_published_raw TEXT,
    source_timezone TEXT,
    ingested_at TEXT NOT NULL,
    provider_tags TEXT NOT NULL DEFAULT '[]',
    data_origin TEXT NOT NULL CHECK (data_origin IN ('sample', 'live')),
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of INTEGER REFERENCES articles(article_id),
    duplicate_reason TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    sentiment_label TEXT CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
    sentiment_score REAL,
    sentiment_confidence REAL,
    sentiment_model TEXT,
    sentiment_version TEXT,
    sentiment_processed_at TEXT,
    sentiment_detail TEXT,
    UNIQUE (provider, ingest_key)
);
CREATE INDEX IF NOT EXISTS ix_articles_published ON articles(published_at_utc);
CREATE INDEX IF NOT EXISTS ix_articles_normurl ON articles(normalized_url);
CREATE INDEX IF NOT EXISTS ix_articles_sourceid ON articles(source, source_id);

CREATE TABLE IF NOT EXISTS article_links (
    article_id INTEGER NOT NULL REFERENCES articles(article_id),
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    method TEXT NOT NULL CHECK (method IN ('provider_tag', 'ticker', 'strong_alias', 'weak_alias')),
    status TEXT NOT NULL CHECK (status IN ('linked', 'ambiguous')),
    matched_text TEXT,
    reason TEXT,
    PRIMARY KEY (article_id, asset_id)
);
CREATE INDEX IF NOT EXISTS ix_links_asset ON article_links(asset_id, status);

CREATE TABLE IF NOT EXISTS model_runs (
    model_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('baseline', 'news_aware')),
    algorithm TEXT NOT NULL,
    data_origin TEXT NOT NULL,
    features TEXT NOT NULL,
    params TEXT NOT NULL,
    split TEXT NOT NULL,
    exclusions TEXT NOT NULL,
    validation TEXT NOT NULL,
    trained_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    UNIQUE (model_name, model_version)
);

CREATE TABLE IF NOT EXISTS forecast_runs (
    forecast_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    reference_session TEXT,
    prediction_session TEXT,
    cutoff_at TEXT,
    generated_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published', 'withheld', 'already_published')),
    reasons TEXT NOT NULL DEFAULT '[]',
    freshness TEXT NOT NULL DEFAULT '{}',
    data_origin TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_run_id INTEGER REFERENCES forecast_runs(forecast_run_id),
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    model_id INTEGER NOT NULL REFERENCES model_runs(model_id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_role TEXT NOT NULL CHECK (model_role IN ('baseline', 'news_aware')),
    origin TEXT NOT NULL CHECK (origin IN ('forecast', 'holdout_backtest')),
    reference_session TEXT NOT NULL,
    prediction_session TEXT NOT NULL,
    horizon TEXT NOT NULL DEFAULT 'next_regular_session',
    cutoff_at TEXT NOT NULL,
    reference_close REAL NOT NULL,
    estimated_change_pct REAL NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('bullish', 'bearish', 'neutral')),
    threshold_pp REAL NOT NULL,
    feature_snapshot TEXT NOT NULL,
    input_freshness TEXT NOT NULL DEFAULT '{}',
    data_status TEXT NOT NULL,
    data_origin TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (asset_id, reference_session, model_name, model_version, origin)
);
CREATE INDEX IF NOT EXISTS ix_pred_session ON predictions(prediction_session);

CREATE TABLE IF NOT EXISTS outcomes (
    prediction_id INTEGER PRIMARY KEY REFERENCES predictions(prediction_id),
    actual_session TEXT NOT NULL,
    actual_close REAL NOT NULL,
    actual_change_pct REAL NOT NULL,
    signed_error_pct_points REAL NOT NULL,
    absolute_error_pct_points REAL NOT NULL,
    resolved_at TEXT NOT NULL,
    resolution_kind TEXT NOT NULL CHECK (resolution_kind IN ('observed', 'holdout_backtest', 'sample_simulation'))
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    stage TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    wall_started_at TEXT NOT NULL,
    wall_finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    input_count INTEGER,
    output_count INTEGER,
    error_summary TEXT,
    details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_runs_stage ON pipeline_runs(stage, run_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_V1)
    current = get_meta(conn, "schema_version")
    if current is None:
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
    elif int(current) > SCHEMA_VERSION:
        raise RuntimeError(f"Database schema {current} is newer than code schema {SCHEMA_VERSION}")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def sync_assets(conn: sqlite3.Connection, watchlist: Watchlist) -> None:
    """Upsert configured assets; deactivate assets no longer in the watchlist (history retained)."""
    configured = {a.asset_id for a in watchlist.assets}
    for a in watchlist.assets:
        conn.execute(
            """INSERT INTO assets(asset_id, ticker, display_name, exchange, asset_type, active)
               VALUES (?, ?, ?, ?, ?, 1)
               ON CONFLICT(asset_id) DO UPDATE SET ticker=excluded.ticker, display_name=excluded.display_name,
               exchange=excluded.exchange, asset_type=excluded.asset_type, active=1""",
            (a.asset_id, a.ticker, a.display_name, a.exchange, a.asset_type),
        )
    for row in conn.execute("SELECT asset_id FROM assets").fetchall():
        if row["asset_id"] not in configured:
            conn.execute("UPDATE assets SET active = 0 WHERE asset_id = ?", (row["asset_id"],))
    conn.commit()


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)
