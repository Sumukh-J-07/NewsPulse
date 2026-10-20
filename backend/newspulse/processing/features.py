"""Daily feature engineering (FR-07, FR-08) with explicit no-look-ahead enforcement.

For asset *i* and reference session *t* (cutoff C_t = session t at the configured
local cutoff time):

Price features (percent units, computed on adjusted close, only sessions <= t):
  ret_1d_pct, ret_5d_pct, ret_10d_pct  - trailing returns ending at t
  vol_10d_pct                          - std. dev. of the last 10 daily returns
  index_ret_1d_pct, index_ret_5d_pct   - same for the market index at t
  is_index                             - 1 for the index row, else 0

News features (eligible linked, non-duplicate, sentiment-scored articles with
published_at_utc in the window (C_prev, C_t], where prev is the previous session
present in the asset's price history):
  news_count, news_mean_sentiment (None if no articles), news_positive_count,
  news_negative_count, news_recency_sentiment (None if no articles; weights
  w = 0.5 ** (age_hours / half_life) with age measured back from C_t).

Model input rule for missing news: when news_count == 0 the mean and recency
sentiment are *missing*; the model vector encodes them as 0.0 together with
has_news = 0 so the model can distinguish "no news" from "neutral news". The
snapshot stores the raw ``None`` values and the imputation note.

Target (training/evaluation only): 100 * (close[t+1] - close[t]) / close[t] where
t+1 is the next session actually present in the price data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..calendar import MarketCalendar, to_iso

PRICE_FEATURES = [
    "ret_1d_pct", "ret_5d_pct", "ret_10d_pct", "vol_10d_pct", "index_ret_1d_pct", "index_ret_5d_pct", "is_index",
]
NEWS_FEATURES = [
    "news_count_log1p", "news_mean_sentiment_filled", "news_positive_count", "news_negative_count",
    "news_recency_sentiment_filled", "has_news",
]
MIN_HISTORY = 11  # 10 trailing returns need 11 closes


class LookAheadError(AssertionError):
    """Raised when a feature input is dated after the prediction cutoff."""


@dataclass
class FeatureRow:
    asset_id: str
    reference_session: date
    cutoff_at: datetime
    reference_close: float
    values: dict[str, float]           # model-ready vector (price + news)
    snapshot: dict[str, Any]           # auditable raw inputs and provenance
    target_pct: float | None = None
    target_session: date | None = None
    target_close: float | None = None


def price_frame(prices: pd.DataFrame) -> pd.DataFrame:
    """Backward-looking price features for one asset. ``prices`` has columns session_date, adjusted_close."""
    df = prices.sort_values("session_date").reset_index(drop=True).copy()
    c = df["adjusted_close"].astype(float)
    daily = c.pct_change() * 100.0
    df["ret_1d_pct"] = daily
    df["ret_5d_pct"] = (c / c.shift(5) - 1.0) * 100.0
    df["ret_10d_pct"] = (c / c.shift(10) - 1.0) * 100.0
    df["vol_10d_pct"] = daily.rolling(10, min_periods=10).std(ddof=1)
    df["prev_session"] = df["session_date"].shift(1)
    df["next_session"] = df["session_date"].shift(-1)
    df["next_close"] = c.shift(-1)  # label only; never used as a feature
    df["target_pct"] = (c.shift(-1) / c - 1.0) * 100.0  # label only; never used as a feature
    return df


def load_price_frames(conn) -> dict[str, pd.DataFrame]:
    rows = conn.execute(
        "SELECT asset_id, session_date, adjusted_close FROM daily_prices "
        "WHERE adjusted_close IS NOT NULL AND adjusted_close > 0 ORDER BY asset_id, session_date"
    ).fetchall()
    frames: dict[str, list] = {}
    for r in rows:
        frames.setdefault(r["asset_id"], []).append((date.fromisoformat(r["session_date"]), r["adjusted_close"]))
    return {
        a: price_frame(pd.DataFrame(v, columns=["session_date", "adjusted_close"])) for a, v in frames.items()
    }


def load_eligible_news(conn) -> dict[str, pd.DataFrame]:
    """Linked, canonical, timestamped, scored articles grouped by asset."""
    rows = conn.execute(
        """SELECT l.asset_id, a.article_id, a.published_at_utc, a.sentiment_score, a.sentiment_label
           FROM article_links l JOIN articles a ON a.article_id = l.article_id
           WHERE l.status = 'linked' AND a.is_duplicate = 0 AND a.published_at_utc IS NOT NULL
             AND a.sentiment_score IS NOT NULL
           ORDER BY l.asset_id, a.published_at_utc"""
    ).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["asset_id"], []).append(
            (r["article_id"], pd.Timestamp(r["published_at_utc"]).tz_convert("UTC"), r["sentiment_score"], r["sentiment_label"])
        )
    return {
        a: pd.DataFrame(v, columns=["article_id", "published", "score", "label"]) for a, v in out.items()
    }


def aggregate_news(news: pd.DataFrame | None, window_start: datetime, cutoff: datetime,
                   half_life_hours: float) -> dict[str, Any]:
    """Aggregate eligible articles in (window_start, cutoff]. Raises LookAheadError on violations."""
    if news is None or news.empty:
        sel = pd.DataFrame(columns=["article_id", "published", "score", "label"])
    else:
        ts = news["published"]
        mask = (ts > pd.Timestamp(window_start)) & (ts <= pd.Timestamp(cutoff))
        sel = news.loc[mask]
    if not sel.empty and sel["published"].max() > pd.Timestamp(cutoff):
        raise LookAheadError("article published after cutoff selected")
    count = int(len(sel))
    if count:
        scores = sel["score"].astype(float).to_numpy()
        ages = (pd.Timestamp(cutoff) - sel["published"]).dt.total_seconds().to_numpy() / 3600.0
        if (ages < 0).any():
            raise LookAheadError("negative article age relative to cutoff")
        weights = np.power(0.5, ages / half_life_hours)
        mean = float(scores.mean())
        recency = float((weights * scores).sum() / weights.sum())
    else:
        mean = recency = None
    return {
        "news_count": count,
        "news_mean_sentiment": mean,
        "news_positive_count": int((sel["label"] == "positive").sum()) if count else 0,
        "news_negative_count": int((sel["label"] == "negative").sum()) if count else 0,
        "news_recency_sentiment": recency,
        "article_ids": [int(x) for x in sel["article_id"].tolist()],
        "latest_article_published_at": to_iso(sel["published"].max().to_pydatetime()) if count else None,
        "window_start": to_iso(window_start),
        "window_end": to_iso(cutoff),
    }


def news_vector(agg: dict[str, Any]) -> dict[str, float]:
    has = 1.0 if agg["news_count"] > 0 else 0.0
    return {
        "news_count_log1p": math.log1p(agg["news_count"]),
        "news_mean_sentiment_filled": agg["news_mean_sentiment"] if has else 0.0,
        "news_positive_count": float(agg["news_positive_count"]),
        "news_negative_count": float(agg["news_negative_count"]),
        "news_recency_sentiment_filled": agg["news_recency_sentiment"] if has else 0.0,
        "has_news": has,
    }


def _finite(*values) -> bool:
    return all(v is not None and isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def build_rows(price_frames: dict[str, pd.DataFrame], news: dict[str, pd.DataFrame], index_id: str,
               asset_types: dict[str, str], calendar: MarketCalendar, half_life_hours: float,
               news_coverage_start: datetime | None, sessions: set[date] | None = None,
               require_target: bool = True) -> tuple[list[FeatureRow], list[dict]]:
    """Build feature rows for every (asset, session). Returns (rows, exclusions)."""
    rows: list[FeatureRow] = []
    exclusions: list[dict] = []
    idx = price_frames.get(index_id)
    idx_by_session = idx.set_index("session_date") if idx is not None else None
    for asset_id, df in price_frames.items():
        if asset_id not in asset_types:
            continue
        for pos, r in enumerate(df.itertuples(index=False)):
            t: date = r.session_date
            if sessions is not None and t not in sessions:
                continue
            ex = {"asset_id": asset_id, "reference_session": t.isoformat()}
            if pos < MIN_HISTORY - 1 or not _finite(r.ret_1d_pct, r.ret_5d_pct, r.ret_10d_pct, r.vol_10d_pct):
                exclusions.append({**ex, "reason": "insufficient_price_history"})
                continue
            if idx_by_session is None or t not in idx_by_session.index:
                exclusions.append({**ex, "reason": "missing_index_price"})
                continue
            irow = idx_by_session.loc[t]
            if not _finite(irow["ret_1d_pct"], irow["ret_5d_pct"]):
                exclusions.append({**ex, "reason": "insufficient_index_history"})
                continue
            target = r.target_pct if _finite(r.target_pct) else None
            if require_target and target is None:
                exclusions.append({**ex, "reason": "missing_target"})
                continue
            cutoff = calendar.cutoff_at(t)
            window_start = calendar.cutoff_at(r.prev_session)
            if news_coverage_start is None or window_start < news_coverage_start:
                exclusions.append({**ex, "reason": "no_news_coverage"})
                continue
            agg = aggregate_news(news.get(asset_id), window_start, cutoff, half_life_hours)
            values = {
                "ret_1d_pct": float(r.ret_1d_pct), "ret_5d_pct": float(r.ret_5d_pct),
                "ret_10d_pct": float(r.ret_10d_pct), "vol_10d_pct": float(r.vol_10d_pct),
                "index_ret_1d_pct": float(irow["ret_1d_pct"]), "index_ret_5d_pct": float(irow["ret_5d_pct"]),
                "is_index": 1.0 if asset_types[asset_id] == "index" else 0.0,
                **news_vector(agg),
            }
            snapshot = {
                "price_inputs": {
                    "basis": "adjusted_close",
                    "first_session_used": df["session_date"].iloc[max(0, pos - 10)].isoformat(),
                    "last_session_used": t.isoformat(),
                    "index_last_session_used": t.isoformat(),
                },
                "news_inputs": agg,
                "missing_value_rule": "news sentiment is None when news_count == 0; encoded as 0.0 with has_news=0",
                "features": values,
            }
            assert_no_look_ahead(snapshot, t, cutoff)
            rows.append(FeatureRow(
                asset_id=asset_id, reference_session=t, cutoff_at=cutoff, reference_close=float(r.adjusted_close),
                values=values, snapshot=snapshot, target_pct=target,
                target_session=r.next_session if target is not None else None,
                target_close=float(r.next_close) if target is not None else None,
            ))
    return rows, exclusions


def assert_no_look_ahead(snapshot: dict[str, Any], reference_session: date, cutoff: datetime) -> None:
    pi = snapshot["price_inputs"]
    if date.fromisoformat(pi["last_session_used"]) > reference_session:
        raise LookAheadError("price input after reference session")
    if date.fromisoformat(pi["index_last_session_used"]) > reference_session:
        raise LookAheadError("index price input after reference session")
    latest = snapshot["news_inputs"].get("latest_article_published_at")
    if latest is not None and datetime.fromisoformat(latest.replace("Z", "+00:00")) > cutoff:
        raise LookAheadError("article published after cutoff")
    if datetime.fromisoformat(snapshot["news_inputs"]["window_end"].replace("Z", "+00:00")) > cutoff:
        raise LookAheadError("news window extends past cutoff")


def truncate_frames(price_frames: dict[str, pd.DataFrame], through: date) -> dict[str, pd.DataFrame]:
    """Recompute price features using only sessions <= ``through`` (used for live forecasts)."""
    out = {}
    for a, df in price_frames.items():
        cut = df.loc[df["session_date"] <= through, ["session_date", "adjusted_close"]]
        if not cut.empty:
            out[a] = price_frame(cut)
    return out


__all__ = [
    "PRICE_FEATURES", "NEWS_FEATURES", "FeatureRow", "LookAheadError", "aggregate_news", "build_rows",
    "load_price_frames", "load_eligible_news", "price_frame", "truncate_frames", "assert_no_look_ahead",
    "news_vector",
]
