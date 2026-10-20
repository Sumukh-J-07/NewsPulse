"""Unit tests for market data and RSS adapters with deterministic mocks (FR-02, FR-03, FR-04)."""
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timezone

from newspulse.providers.live_adapters import fetch_rss_feed, fetch_yfinance_market_data
from newspulse.settings import AssetConfig

TEST_ASSET = AssetConfig(
    asset_id="TESTSTOCK",
    ticker="TEST.NS",
    display_name="Test Stock",
    exchange="NSE",
    asset_type="stock",
    strong_aliases=("Test Stock",),
    weak_aliases=("Test",),
    conflicts=()
)

def test_yfinance_empty_response():
    """Verify empty yfinance history is tracked as a failure without crashing."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_instance

        records, meta = fetch_yfinance_market_data([TEST_ASSET], days=30)
        assert len(records) == 0
        assert "TEST.NS" in meta["failed_symbols"]
        assert len(meta["success_symbols"]) == 0

def test_yfinance_success_response():
    """Verify valid yfinance dataframe formats both nominal and adjusted close."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_df = pd.DataFrame({
            "Open": [100.0, 102.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 101.0],
            "Close": [104.0, 105.5],
            "Adj Close": [103.5, 105.0],
            "Volume": [1000, 1200],
        }, index=pd.to_datetime(["2026-10-15", "2026-10-16"]))
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        records, meta = fetch_yfinance_market_data([TEST_ASSET], days=30)
        assert len(records) == 2
        assert "TEST.NS" in meta["success_symbols"]
        assert records[0]["close"] == 104.0
        assert records[0]["adjusted_close"] == 103.5
        assert records[0]["price_basis"] == "adjusted_close"

def test_rss_safe_timestamp_parsing():
    """Verify publication timestamp handling: unparseable pubDate remains None and is not set to retrieval time."""
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <item>
          <title>Valid Article Headline</title>
          <link>https://example.com/article1</link>
          <pubDate>Wed, 15 Oct 2026 10:30:00 GMT</pubDate>
          <guid>guid-1</guid>
        </item>
        <item>
          <title>Article with Invalid Date</title>
          <link>https://example.com/article2</link>
          <pubDate>not-a-valid-date</pubDate>
          <guid>guid-2</guid>
        </item>
        <item>
          <title>Article with Missing Date</title>
          <link>https://example.com/article3</link>
          <guid>guid-3</guid>
        </item>
      </channel>
    </rss>"""

    with patch("newspulse.providers.live_adapters.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = xml_content
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        items = fetch_rss_feed("https://example.com/feed.xml", feed_name="Test Source")
        assert len(items) == 3

        # Item 1: valid UTC publication time
        assert items[0]["published_at_utc"] == "2026-10-15T10:30:00Z"

        # Item 2: invalid date -> published_at_utc must be None
        assert items[1]["published_at_utc"] is None
        assert items[1]["source_published_raw"] == "not-a-valid-date"

        # Item 3: missing date -> published_at_utc must be None
        assert items[2]["published_at_utc"] is None
        assert items[2]["source_published_raw"] is None
