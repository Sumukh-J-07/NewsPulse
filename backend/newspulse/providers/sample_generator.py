"""Sample data generator for reproducible, deterministic demonstration mode (AC-08).

Generates internally consistent:
- Historical daily price records for index + 8 fictional stocks (DM100, ALFA, BRIO, CEDR, DUNE, ELIO, FERN, GALE, HALO)
- Realistic financial headlines with publication timestamps
- Linked company entities
- Positive, neutral, and negative sentiment distribution matching the financial lexicon
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from ..settings import AssetConfig

UTC = timezone.utc

SAMPLE_HEADLINE_TEMPLATES = [
    # Positive
    ("{name} announces strong quarterly profit growth and dividend boost", "positive", ["profit", "growth", "dividend"]),
    ("{name} secures landmark international infrastructure partnership deal", "positive", ["partnership", "deal", "secures"]),
    ("{name} beats estimates as regional demand surges", "positive", ["beats estimates", "surges"]),
    ("{name} raises annual capacity guidance following operational milestone", "positive", ["raises guidance", "milestone"]),
    ("{name} receives regulatory approval for major product expansion", "positive", ["approval", "expansion"]),
    ("{name} reports robust cash flows and order wins", "positive", ["robust", "wins"]),
    # Negative
    ("{name} warns of margin pressure amid rising raw material costs", "negative", ["warns", "pressure"]),
    ("{name} misses estimates as export shipments drop sharply", "negative", ["misses estimates", "drop", "sharply"]),
    ("{name} revises annual capacity outlook downwards amid volatile conditions", "negative", ["revises", "volatile"]),
    ("{name} faces regulatory probe into supply chain practices", "negative", ["probe", "risk"]),
    ("{name} slips as analysts cut price target following cautious guidance", "negative", ["slips", "cut"]),
    ("{name} reports quarterly loss amid rising debt headwinds", "negative", ["loss", "debt", "headwinds"]),
    # Neutral
    ("{name} publishes annual sustainability disclosure report", "neutral", []),
    ("{name} schedules board meeting to review quarterly accounts", "neutral", []),
    ("{name} announces ordinary general meeting details for shareholders", "neutral", []),
    ("{name} files periodic regulatory compliance update", "neutral", []),
]

INDEX_HEADLINES = [
    ("Markets rally as broader economic indicators beat expectations", "positive"),
    ("Benchmark index climbs on foreign institutional inflows", "positive"),
    ("Market slides amid global inflation headwinds and rate concerns", "negative"),
    ("Benchmark index sheds early gains in volatile trade", "negative"),
    ("Markets finish flat as investors await central bank decision", "neutral"),
]


def generate_sample_dataset(
    assets: Sequence[AssetConfig],
    start_date: date = date(2025, 4, 1),
    end_date: date = date(2026, 10, 16),
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """Generate deterministic (prices, articles) for sample mode."""
    rng = random.Random(seed)

    # 1. Generate trading sessions (weekdays excluding holidays)
    sessions: list[date] = []
    curr = start_date
    while curr <= end_date:
        if curr.weekday() < 5:  # Monday to Friday
            sessions.append(curr)
        curr += timedelta(days=1)

    # Base price parameters per asset
    base_prices = {
        "DM100": 12000.0,
        "ALFA": 140.0,
        "BRIO": 85.0,
        "CEDR": 215.0,
        "DUNE": 55.0,
        "ELIO": 110.0,
        "FERN": 320.0,
        "GALE": 180.0,
        "HALO": 450.0,
    }

    prices_out: list[dict] = []
    articles_out: list[dict] = []

    # Track prices per session to build realistic time series with correlation to index
    price_series: dict[str, list[float]] = {a.asset_id: [] for a in assets}

    for s_idx, session in enumerate(sessions):
        # Market move
        market_ret = rng.gauss(0.0004, 0.010)  # ~0.04% mean daily return, 1% vol
        if s_idx == 0:
            m_close = base_prices.get("DM100", 12000.0)
        else:
            m_close = price_series["DM100"][-1] * (1.0 + market_ret)
        price_series["DM100"].append(m_close)

        for a in assets:
            if a.asset_id == "DM100":
                close = m_close
            else:
                beta = rng.uniform(0.7, 1.3)
                idio = rng.gauss(0.0, 0.014)
                stock_ret = beta * market_ret + idio
                if s_idx == 0:
                    close = base_prices.get(a.asset_id, 100.0)
                else:
                    close = price_series[a.asset_id][-1] * (1.0 + stock_ret)
                price_series[a.asset_id].append(close)

            # High, Low, Open, Volume
            daily_vol = abs(rng.gauss(0, 0.008))
            open_p = close * (1.0 + rng.gauss(0, 0.004))
            high_p = max(open_p, close) * (1.0 + daily_vol)
            low_p = min(open_p, close) * (1.0 - daily_vol)
            volume = float(rng.randint(50000, 2000000)) if a.asset_type == "stock" else float(rng.randint(10000000, 50000000))

            prices_out.append({
                "asset_id": a.asset_id,
                "session_date": session.isoformat(),
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close, 2),
                "adjusted_close": round(close, 2),
                "volume": volume,
                "provider": "sample_fixture",
                "price_basis": "adjusted_close",
                "data_origin": "sample",
                "retrieved_at": datetime.now(UTC).isoformat(),
            })

    # 2. Generate headlines distributed realistically across sessions
    # Articles are published before the 16:00 cutoff of the session or in the preceding evening
    article_id_counter = 1000
    for s_idx, session in enumerate(sessions):
        # Index headlines occasionally
        if rng.random() < 0.6:
            tmpl, sentiment_type = rng.choice(INDEX_HEADLINES)
            pub_time = datetime.combine(session, datetime.min.time(), tzinfo=UTC) + timedelta(hours=rng.uniform(7, 15.5))
            articles_out.append({
                "article_id": article_id_counter,
                "provider": "sample_feed",
                "source": "MarketWire",
                "source_id": f"mw-{article_id_counter}",
                "ingest_key": f"sid:mw-{article_id_counter}",
                "url": f"https://demo.market.local/news/{article_id_counter}",
                "normalized_url": f"https://demo.market.local/news/{article_id_counter}",
                "headline": tmpl,
                "published_at_utc": pub_time.isoformat(),
                "source_published_raw": pub_time.isoformat(),
                "source_timezone": "UTC",
                "ingested_at": pub_time.isoformat(),
                "provider_tags": ["DM100"],
                "data_origin": "sample",
                "is_duplicate": 0,
                "linked_asset_ids": ["DM100"],
            })
            article_id_counter += 1

        # Stock headlines: each stock gets 0-3 headlines per session
        for a in assets:
            if a.asset_type != "stock":
                continue
            num_articles = rng.choices([0, 1, 2, 3], weights=[0.45, 0.35, 0.15, 0.05])[0]
            for _ in range(num_articles):
                tmpl, sent_type, _ = rng.choice(SAMPLE_HEADLINE_TEMPLATES)
                headline_text = tmpl.format(name=a.display_name)
                # Random time between previous session cutoff (16:00) and current cutoff (15:50)
                pub_time = datetime.combine(session, datetime.min.time(), tzinfo=UTC) + timedelta(hours=rng.uniform(6.5, 15.75))
                articles_out.append({
                    "article_id": article_id_counter,
                    "provider": "sample_feed",
                    "source": "Financial Observer",
                    "source_id": f"fo-{article_id_counter}",
                    "ingest_key": f"sid:fo-{article_id_counter}",
                    "url": f"https://demo.market.local/news/{article_id_counter}",
                    "normalized_url": f"https://demo.market.local/news/{article_id_counter}",
                    "headline": headline_text,
                    "published_at_utc": pub_time.isoformat(),
                    "source_published_raw": pub_time.isoformat(),
                    "source_timezone": "UTC",
                    "ingested_at": pub_time.isoformat(),
                    "provider_tags": [a.ticker],
                    "data_origin": "sample",
                    "is_duplicate": 0,
                    "linked_asset_ids": [a.asset_id],
                })
                article_id_counter += 1

    return prices_out, articles_out
