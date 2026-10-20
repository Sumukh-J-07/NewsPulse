import pytest
from datetime import datetime, timezone
import pandas as pd
from newspulse.processing.features import LookAheadError, aggregate_news, assert_no_look_ahead

UTC = timezone.utc

def test_no_future_news_leakage():
    cutoff = datetime(2026, 10, 15, 16, 0, tzinfo=UTC)
    window_start = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)

    # Eligible pre-cutoff news
    news_df = pd.DataFrame([
        {"article_id": 1, "published": pd.Timestamp("2026-10-15 10:00:00+00:00"), "score": 0.8, "label": "positive"},
        {"article_id": 2, "published": pd.Timestamp("2026-10-15 15:30:00+00:00"), "score": -0.5, "label": "negative"},
        # Future post-cutoff news
        {"article_id": 3, "published": pd.Timestamp("2026-10-15 16:30:00+00:00"), "score": 1.0, "label": "positive"},
    ])

    agg = aggregate_news(news_df, window_start, cutoff, half_life_hours=12.0)
    assert agg["news_count"] == 2
    assert 3 not in agg["article_ids"]
    assert agg["latest_article_published_at"] == "2026-10-15T15:30:00Z"
