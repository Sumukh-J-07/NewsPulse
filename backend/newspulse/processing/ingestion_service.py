"""Data ingestion, normalization, deduplication, and entity linking pipeline."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from ..calendar import UTC, to_iso
from ..db import session
from ..processing.dedup import DedupIndex, ingest_key, normalize_url
from ..processing.linking import EntityLinker
from ..processing.sentiment import score_headline
from ..providers.live_adapters import fetch_rss_feed, fetch_yfinance_prices
from ..providers.sample_generator import generate_sample_dataset
from ..settings import Settings, Watchlist

logger = logging.getLogger(__name__)


def ingest_market_prices(settings: Settings, watchlist: Watchlist) -> dict[str, Any]:
    """Ingest daily price data for watchlist assets and store in daily_prices table."""
    logger.info("Ingesting market prices for mode: %s", settings.mode)
    meta = {}
    if settings.mode == "sample":
        prices, _ = generate_sample_dataset(watchlist.assets)
        meta = {"success_symbols": [a.ticker for a in watchlist.assets], "failed_symbols": {}}
    else:
        from ..providers.live_adapters import fetch_yfinance_market_data
        prices, meta = fetch_yfinance_market_data(
            watchlist.assets,
            days=settings.price_history_days,
            timeout=settings.http_timeout_seconds
        )

    if not prices:
        logger.warning("No price records fetched")
        return {"inserted": 0, "count": 0, "success_symbols": [], "failed_symbols": meta.get("failed_symbols", {})}

    inserted = 0
    with session(settings.db_path) as conn:
        for p in prices:
            cursor = conn.execute(
                """INSERT INTO daily_prices (
                    asset_id, session_date, open, high, low, close, adjusted_close,
                    volume, provider, price_basis, data_origin, retrieved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, session_date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, adjusted_close=excluded.adjusted_close,
                    volume=excluded.volume, provider=excluded.provider,
                    retrieved_at=excluded.retrieved_at""",
                (
                    p["asset_id"], p["session_date"], p["open"], p["high"], p["low"],
                    p["close"], p["adjusted_close"], p["volume"], p["provider"],
                    p["price_basis"], p["data_origin"], p["retrieved_at"]
                )
            )
            inserted += cursor.rowcount

    logger.info("Ingested/updated %d daily price records", inserted)
    return {
        "inserted": inserted,
        "count": inserted,
        "success_symbols": meta.get("success_symbols", []),
        "failed_symbols": meta.get("failed_symbols", {}),
    }


def ingest_financial_news(settings: Settings, watchlist: Watchlist) -> int:
    """Ingest financial headlines from sample or live RSS feeds."""
    logger.info("Ingesting financial news for mode: %s", settings.mode)
    raw_articles = []

    if settings.mode == "sample":
        _, raw_articles = generate_sample_dataset(watchlist.assets)
    else:
        # Live RSS feeds
        for feed in watchlist.news_feeds:
            name = feed.get("name", "RSS")
            url_tmpl = feed.get("url_template")
            if feed.get("kind") == "per_asset" and url_tmpl:
                for asset in watchlist.stocks:
                    feed_url = url_tmpl.format(ticker=asset.ticker)
                    items = fetch_rss_feed(feed_url, feed_name=name, default_tags=[asset.ticker])
                    raw_articles.extend(items)
            elif feed.get("url"):
                items = fetch_rss_feed(feed["url"], feed_name=name)
                raw_articles.extend(items)

    if not raw_articles:
        logger.info("No raw articles to ingest")
        return 0

    inserted_count = 0
    with session(settings.db_path) as conn:
        # Build dedup index from existing canonical articles
        existing_rows = conn.execute(
            "SELECT article_id, source, source_id, normalized_url, headline, published_at_utc FROM articles WHERE is_duplicate = 0"
        ).fetchall()
        dedup_idx = DedupIndex()
        for row in existing_rows:
            pub_dt = datetime.fromisoformat(row["published_at_utc"].replace("Z", "+00:00")) if row["published_at_utc"] else None
            dedup_idx.add(
                row["article_id"], row["source"], row["source_id"], row["normalized_url"], row["headline"], pub_dt
            )

        linker = EntityLinker(watchlist.assets)

        for art in raw_articles:
            pub_dt = datetime.fromisoformat(art["published_at_utc"].replace("Z", "+00:00")) if art.get("published_at_utc") else None
            
            # Check duplicates
            dup_of, dup_reason = dedup_idx.check(
                art["source"], art.get("source_id"), art.get("normalized_url"), art.get("headline"), pub_dt
            )
            is_dup = 1 if dup_of else 0

            # Insert article
            try:
                cursor = conn.execute(
                    """INSERT INTO articles (
                        provider, source, source_id, ingest_key, url, normalized_url,
                        headline, published_at_utc, source_published_raw, source_timezone,
                        ingested_at, provider_tags, data_origin, is_duplicate, duplicate_of,
                        duplicate_reason, processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(provider, ingest_key) DO UPDATE SET
                        published_at_utc=COALESCE(articles.published_at_utc, excluded.published_at_utc)
                    RETURNING article_id""",
                    (
                        art["provider"], art["source"], art.get("source_id"), art["ingest_key"],
                        art.get("url"), art.get("normalized_url"), art.get("headline"),
                        art.get("published_at_utc"), art.get("source_published_raw"),
                        art.get("source_timezone"), art["ingested_at"],
                        str(art.get("provider_tags", [])), art["data_origin"],
                        is_dup, dup_of, dup_reason
                    )
                )
                row = cursor.fetchone()
                if row:
                    article_id = row[0]
                    inserted_count += 1
                    if not is_dup:
                        dedup_idx.add(
                            article_id, art["source"], art.get("source_id"),
                            art.get("normalized_url"), art.get("headline"), pub_dt
                        )
                    
                    # Link entities
                    links, _ = linker.link(art.get("headline"), art.get("provider_tags", []))
                    # Also attach explicit sample linked assets if provided
                    if "linked_asset_ids" in art:
                        for asset_id in art["linked_asset_ids"]:
                            if not any(l.asset_id == asset_id for l in links):
                                conn.execute(
                                    """INSERT OR IGNORE INTO article_links (article_id, asset_id, method, status, matched_text, reason)
                                    VALUES (?, ?, 'provider_tag', 'linked', NULL, 'sample explicit link')""",
                                    (article_id, asset_id)
                                )

                    for lk in links:
                        conn.execute(
                            """INSERT OR IGNORE INTO article_links (article_id, asset_id, method, status, matched_text, reason)
                            VALUES (?, ?, ?, ?, ?, ?)""",
                            (article_id, lk.asset_id, lk.method, lk.status, lk.matched_text, lk.reason)
                        )
            except Exception as exc:
                logger.error("Failed to insert article: %s", exc)

    logger.info("Ingested %d articles into database", inserted_count)
    return inserted_count


def process_unscored_articles(settings: Settings) -> int:
    """Score sentiment for all processed=0 articles using the lexicon scorer."""
    scored_count = 0
    with session(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT article_id, headline FROM articles WHERE processed = 0 AND headline IS NOT NULL"
        ).fetchall()

        now_utc = datetime.now(UTC).isoformat()
        for r in rows:
            res = score_headline(r["headline"])
            if res:
                conn.execute(
                    """UPDATE articles SET
                        processed = 1,
                        sentiment_label = ?,
                        sentiment_score = ?,
                        sentiment_confidence = ?,
                        sentiment_model = ?,
                        sentiment_version = ?,
                        sentiment_processed_at = ?,
                        sentiment_detail = ?
                    WHERE article_id = ?""",
                    (
                        res.label, res.score, res.confidence, res.model, res.version,
                        now_utc, str({"pos_hits": res.positive_hits, "neg_hits": res.negative_hits, "flags": res.flags}),
                        r["article_id"]
                    )
                )
                scored_count += 1
            else:
                conn.execute("UPDATE articles SET processed = 1 WHERE article_id = ?", (r["article_id"],))

    logger.info("Scored sentiment for %d headlines", scored_count)
    return scored_count
