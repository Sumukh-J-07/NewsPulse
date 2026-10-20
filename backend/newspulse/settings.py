"""Runtime configuration loaded from environment variables and the watchlist JSON file.

Secrets (operator token) come only from the environment and are never serialised
into API responses or logs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"

VALID_MODES = ("sample", "live")


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class AssetConfig:
    asset_id: str
    ticker: str
    display_name: str
    exchange: str
    asset_type: str  # "index" | "stock"
    strong_aliases: tuple[str, ...] = ()
    weak_aliases: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketConfig:
    name: str
    exchange: str
    timezone: str
    session_close_local: time
    cutoff_local: time
    holidays: frozenset[date]


@dataclass(frozen=True)
class Watchlist:
    data_origin: str
    market: MarketConfig
    index: AssetConfig
    stocks: tuple[AssetConfig, ...]
    news_feeds: tuple[dict[str, Any], ...] = ()

    @property
    def assets(self) -> tuple[AssetConfig, ...]:
        return (self.index, *self.stocks)

    def get(self, asset_id: str) -> AssetConfig | None:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None


@dataclass(frozen=True)
class Settings:
    mode: str
    db_path: Path
    watchlist_path: Path
    threshold_pp: float = 0.25
    price_max_age_days: int = 4
    news_max_age_hours: float = 36.0
    recency_half_life_hours: float = 12.0
    min_train_sessions: int = 40
    min_test_sessions: int = 10
    price_history_days: int = 400
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3
    refresh_min_interval_seconds: float = 5.0
    operator_token: str | None = field(default=None, repr=False)

    @property
    def refresh_enabled(self) -> bool:
        return bool(self.operator_token)


def _parse_time(value: str, label: str) -> time:
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid {label} '{value}', expected HH:MM") from exc


def _asset(raw: Mapping[str, Any], asset_type: str) -> AssetConfig:
    for key in ("asset_id", "ticker", "display_name", "exchange"):
        if not raw.get(key):
            raise ConfigError(f"Watchlist asset missing '{key}': {raw}")
    aliases = raw.get("aliases", {}) or {}
    return AssetConfig(
        asset_id=str(raw["asset_id"]).upper(),
        ticker=str(raw["ticker"]),
        display_name=str(raw["display_name"]),
        exchange=str(raw["exchange"]),
        asset_type=asset_type,
        strong_aliases=tuple(aliases.get("strong", [])),
        weak_aliases=tuple(aliases.get("weak", [])),
        conflicts=tuple(raw.get("conflicts", [])),
    )


def load_watchlist(path: Path) -> Watchlist:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Watchlist file not found: {path}") from exc
    market_raw = raw["market"]
    from zoneinfo import ZoneInfo

    ZoneInfo(market_raw["timezone"])  # validates timezone name
    market = MarketConfig(
        name=market_raw["name"],
        exchange=market_raw["exchange"],
        timezone=market_raw["timezone"],
        session_close_local=_parse_time(market_raw.get("session_close_local", "15:30"), "session_close_local"),
        cutoff_local=_parse_time(market_raw.get("cutoff_local", "16:00"), "cutoff_local"),
        holidays=frozenset(date.fromisoformat(d) for d in market_raw.get("holidays", [])),
    )
    stocks = tuple(_asset(s, "stock") for s in raw.get("stocks", []))
    if not 5 <= len(stocks) <= 10:
        raise ConfigError(f"Watchlist must contain 5-10 stocks (FR-01); found {len(stocks)}")
    ids = [s.asset_id for s in stocks]
    if len(set(ids)) != len(ids):
        raise ConfigError("Duplicate asset_id in watchlist")
    return Watchlist(
        data_origin=raw.get("data_origin", "live"),
        market=market,
        index=_asset(raw["index"], "index"),
        stocks=stocks,
        news_feeds=tuple(raw.get("news_feeds", [])),
    )


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    mode = env.get("NEWSPULSE_MODE", "sample").strip().lower()
    if mode not in VALID_MODES:
        raise ConfigError(f"NEWSPULSE_MODE must be one of {VALID_MODES}, got '{mode}'")
    default_watchlist = CONFIG_DIR / ("watchlist.sample.json" if mode == "sample" else "watchlist.nse.json")
    default_db = DATA_DIR / f"newspulse_{mode}.db"

    def num(name: str, default: float, cast=float):
        value = env.get(name)
        if value is None or value == "":
            return default
        try:
            return cast(value)
        except ValueError as exc:
            raise ConfigError(f"{name} must be numeric, got '{value}'") from exc

    threshold = num("NEWSPULSE_THRESHOLD_PP", 0.25)
    if threshold < 0:
        raise ConfigError("NEWSPULSE_THRESHOLD_PP must be >= 0")
    return Settings(
        mode=mode,
        db_path=Path(env.get("NEWSPULSE_DB_PATH") or default_db),
        watchlist_path=Path(env.get("NEWSPULSE_WATCHLIST") or default_watchlist),
        threshold_pp=threshold,
        price_max_age_days=int(num("NEWSPULSE_PRICE_MAX_AGE_DAYS", 4, int)),
        news_max_age_hours=num("NEWSPULSE_NEWS_MAX_AGE_HOURS", 36.0),
        recency_half_life_hours=num("NEWSPULSE_RECENCY_HALF_LIFE_HOURS", 12.0),
        min_train_sessions=int(num("NEWSPULSE_MIN_TRAIN_SESSIONS", 40, int)),
        min_test_sessions=int(num("NEWSPULSE_MIN_TEST_SESSIONS", 10, int)),
        http_timeout_seconds=num("NEWSPULSE_HTTP_TIMEOUT_SECONDS", 10.0),
        http_max_retries=int(num("NEWSPULSE_HTTP_MAX_RETRIES", 3, int)),
        refresh_min_interval_seconds=num("NEWSPULSE_REFRESH_MIN_INTERVAL_SECONDS", 5.0),
        operator_token=(env.get("NEWSPULSE_OPERATOR_TOKEN") or None),
    )
