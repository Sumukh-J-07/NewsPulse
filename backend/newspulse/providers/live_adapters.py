"""Live data adapters for yfinance daily prices and public RSS financial news feeds.
Respects rate limits, timeouts, error logging, and graceful fallbacks without crashing.

PRICE SERIES POLICY:
- `close`: Nominal, unadjusted closing price on the exchange. Used for reporting, nominal reference close,
  and determining nominal realized session-to-session close prices.
- `adjusted_close`: Split- and dividend-adjusted closing price. Used for computing historical percentage
  changes, technical returns, and feature inputs to prevent corporate actions (splits, bonus issues)
  from injecting spurious return spikes into model features.
"""
from __future__ import annotations

import logging
import re
import ssl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Sequence
from urllib.request import Request, urlopen

from ..calendar import UTC, to_iso
from ..processing.dedup import ingest_key, normalize_url
from ..settings import AssetConfig

logger = logging.getLogger(__name__)

# SSL context with system and certifi root certificates for secure RSS feeds
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()


def fetch_yfinance_prices(
    assets: Sequence[AssetConfig],
    days: int = 120,
    timeout: float = 12.0
) -> list[dict]:
    """Retrieve daily price history using yfinance for configured assets.

    Returns normalized records with explicit close and adjusted_close fields.
    """
    records, _ = fetch_yfinance_market_data(assets, days=days, timeout=timeout)
    return records


def fetch_yfinance_market_data(
    assets: Sequence[AssetConfig],
    days: int = 120,
    timeout: float = 12.0
) -> tuple[list[dict], dict[str, Any]]:
    """Retrieve daily price history using yfinance and return records with per-symbol provenance.

    Returns:
        (records, metadata) where metadata contains:
        - success_symbols: list of tickers successfully fetched
        - failed_symbols: dict of {ticker: error_message}
        - session_counts: dict of {ticker: count_of_sessions}
    """
    import yfinance as yf

    results: list[dict] = []
    retrieved_at = datetime.now(UTC).isoformat()
    success_symbols: list[str] = []
    failed_symbols: dict[str, str] = {}
    session_counts: dict[str, int] = {}

    for asset in assets:
        try:
            logger.info("Fetching yfinance prices for %s (%s)", asset.ticker, asset.asset_id)
            ticker_obj = yf.Ticker(asset.ticker)
            # auto_adjust=False ensures both unadjusted 'Close' and 'Adj Close' are returned
            hist = ticker_obj.history(period=f"{days}d", auto_adjust=False, timeout=timeout)
            if hist.empty:
                logger.warning("Empty price dataframe returned by yfinance for %s", asset.ticker)
                failed_symbols[asset.ticker] = "Empty price history returned"
                continue

            asset_records = 0
            for idx, row in hist.iterrows():
                session_str = idx.strftime("%Y-%m-%d")
                close_val = float(row["Close"]) if "Close" in row and row["Close"] is not None else None
                adj_close_val = float(row["Adj Close"]) if "Adj Close" in row and row["Adj Close"] is not None else close_val
                if close_val is None or close_val <= 0:
                    continue

                open_val = float(row.get("Open", close_val))
                high_val = float(row.get("High", close_val))
                low_val = float(row.get("Low", close_val))
                vol_val = float(row.get("Volume", 0))

                results.append({
                    "asset_id": asset.asset_id,
                    "session_date": session_str,
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "adjusted_close": adj_close_val or close_val,
                    "volume": vol_val,
                    "provider": "yfinance",
                    "price_basis": "adjusted_close",
                    "data_origin": "live",
                    "retrieved_at": retrieved_at,
                })
                asset_records += 1

            if asset_records > 0:
                success_symbols.append(asset.ticker)
                session_counts[asset.ticker] = asset_records
            else:
                failed_symbols[asset.ticker] = "No valid close price rows parsed"

        except Exception as exc:
            err_msg = str(exc)
            logger.error("Error fetching prices for %s from yfinance: %s", asset.ticker, err_msg)
            failed_symbols[asset.ticker] = err_msg

    meta = {
        "success_symbols": success_symbols,
        "failed_symbols": failed_symbols,
        "session_counts": session_counts,
        "retrieved_at": retrieved_at,
    }
    return results, meta


def fetch_rss_feed(
    url: str,
    feed_name: str = "RSS Feed",
    default_tags: Sequence[str] = (),
    timeout: float = 10.0
) -> list[dict]:
    """Fetch and parse financial headlines from a public RSS feed."""
    results: list[dict] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (NewsPulse Financial Research; academic news-analysis)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, context=_SSL_CONTEXT, timeout=timeout) as resp:
            content = resp.read()
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []

    try:
        root = ET.fromstring(content)
    except Exception as exc:
        logger.warning("XML parse error on RSS feed %s: %s", url, exc)
        return []

    ingested_at = datetime.now(UTC).isoformat()

    # RSS items
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")
        guid_el = item.find("guid")

        headline = title_el.text.strip() if title_el is not None and title_el.text else None
        raw_url = link_el.text.strip() if link_el is not None and link_el.text else None
        guid = guid_el.text.strip() if guid_el is not None and guid_el.text else None

        if not headline:
            continue

        pub_utc = None
        raw_pub = None
        if pub_date_el is not None and pub_date_el.text:
            raw_pub = pub_date_el.text.strip()
            try:
                dt = parsedate_to_datetime(raw_pub)
                pub_utc = to_iso(dt)
            except Exception:
                # Do NOT assign retrieval time to pub_utc when publication date cannot be parsed!
                # Unparseable publication time remains None so cutoff filters can strictly exclude it.
                pub_utc = None

        norm_url = normalize_url(raw_url)
        ikey = ingest_key(guid, raw_url, headline, pub_utc)

        results.append({
            "provider": "rss",
            "source": feed_name,
            "source_id": guid,
            "ingest_key": ikey,
            "url": raw_url,
            "normalized_url": norm_url,
            "headline": headline,
            "published_at_utc": pub_utc,
            "source_published_raw": raw_pub,
            "source_timezone": "UTC" if pub_utc else None,
            "ingested_at": ingested_at,
            "provider_tags": list(default_tags),
            "data_origin": "live",
            "is_duplicate": 0,
        })

    return results
