"""Separate Live Provider Smoke Test against actual real-world market and RSS sources.
Reports timestamp, provider responses, asset status, and failures.
"""
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

# Add backend to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from newspulse.calendar import UTC
from newspulse.providers.live_adapters import fetch_rss_feed, fetch_yfinance_market_data
from newspulse.settings import load_watchlist

def run_smoke_test():
    test_time = datetime.now(UTC)
    print("=" * 60)
    print(f"NEWSPULSE LIVE-PROVIDER SMOKE TEST — {test_time.isoformat()}")
    print("=" * 60)

    watchlist_path = REPO_ROOT / "config" / "watchlist.nse.json"
    watchlist = load_watchlist(watchlist_path)
    print(f"Loaded Watchlist: {len(watchlist.assets)} assets ({watchlist.index.ticker} index + {len(watchlist.stocks)} stocks)")

    # 1. Market Data Smoke Test
    print("\n--- 1. MARKET DATA PROVIDER (yfinance) ---")
    start_yf = datetime.now(UTC)
    prices, meta = fetch_yfinance_market_data(watchlist.assets, days=10, timeout=15.0)
    yf_duration = (datetime.now(UTC) - start_yf).total_seconds()

    print(f"yfinance query duration: {yf_duration:.2f}s")
    print(f"Successful symbols ({len(meta['success_symbols'])}/{len(watchlist.assets)}):")
    for sym in meta["success_symbols"]:
        print(f"  ✓ {sym}: {meta['session_counts'].get(sym, 0)} sessions returned")

    if meta["failed_symbols"]:
        print(f"Failed symbols ({len(meta['failed_symbols'])}):")
        for sym, err in meta["failed_symbols"].items():
            print(f"  ✗ {sym}: {err}")
    else:
        print("  ✓ No market data provider errors.")

    # 2. News Feeds Smoke Test
    print("\n--- 2. RSS NEWS PROVIDERS ---")
    feed_results = {}
    for feed in watchlist.news_feeds:
        feed_name = feed.get("name", "Unknown Feed")
        url = feed.get("url")
        if not url:
            continue
        print(f"Testing feed: {feed_name} ({url})...")
        start_feed = datetime.now(UTC)
        articles = fetch_rss_feed(url, feed_name=feed_name, timeout=12.0)
        feed_duration = (datetime.now(UTC) - start_feed).total_seconds()
        feed_results[feed_name] = {
            "articles_count": len(articles),
            "duration": round(feed_duration, 2),
            "sample_headline": articles[0]["headline"] if articles else None,
            "sample_pub_utc": articles[0]["published_at_utc"] if articles else None
        }
        print(f"  ✓ Fetched {len(articles)} headlines in {feed_duration:.2f}s")
        if articles:
            print(f"    Sample: \"{articles[0]['headline'][:70]}...\" ({articles[0]['published_at_utc']})")

    # Overall Summary
    print("\n" + "=" * 60)
    print("LIVE SMOKE TEST SUMMARY")
    print("=" * 60)
    market_ok = len(meta["success_symbols"]) == len(watchlist.assets)
    news_ok = sum(f["articles_count"] for f in feed_results.values()) > 0
    print(f"Market Data Status : {'PASS' if market_ok else 'PARTIAL' if meta['success_symbols'] else 'FAIL'}")
    print(f"RSS Feeds Status   : {'PASS' if news_ok else 'FAIL'}")
    print(f"Total Live Articles: {sum(f['articles_count'] for f in feed_results.values())}")
    print(f"Total Price Rows   : {len(prices)}")
    print("=" * 60)

    return market_ok and news_ok

if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
