"""Trading-session calendar and timestamp helpers.

Sessions are weekdays that are not configured holidays. The calendar is used to
(1) compute the prediction cutoff for a reference session and (2) estimate the
next regular session date. Reconciliation never relies on the estimate: it uses
the first session actually present in stored price data after the reference
session.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

UTC = timezone.utc


def parse_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string into an aware UTC datetime (None stays None)."""
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Ambiguous timestamp without timezone: {value}")
    return dt.astimezone(UTC)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError("Refusing to serialise a naive datetime")
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MarketCalendar:
    def __init__(self, tz_name: str, cutoff_local: time, holidays: Iterable[date] = ()):
        self.tz = ZoneInfo(tz_name)
        self.tz_name = tz_name
        self.cutoff_local = cutoff_local
        self.holidays = frozenset(holidays)

    def is_session(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def next_session(self, d: date) -> date:
        nxt = d + timedelta(days=1)
        while not self.is_session(nxt):
            nxt += timedelta(days=1)
        return nxt

    def previous_session(self, d: date) -> date:
        prv = d - timedelta(days=1)
        while not self.is_session(prv):
            prv -= timedelta(days=1)
        return prv

    def cutoff_at(self, session: date) -> datetime:
        """Prediction cutoff for a reference session, as an aware UTC datetime."""
        return datetime.combine(session, self.cutoff_local, tzinfo=self.tz).astimezone(UTC)

    def latest_completed_session(self, now_utc: datetime) -> date:
        """Most recent session whose cutoff has passed at ``now_utc``."""
        local = now_utc.astimezone(self.tz)
        d = local.date()
        if self.is_session(d) and local.time() >= self.cutoff_local:
            return d
        return self.previous_session(d)

    def local_iso(self, dt: datetime | None) -> str | None:
        return None if dt is None else dt.astimezone(self.tz).isoformat()

    def sessions_between(self, start: date, end: date) -> list[date]:
        out, d = [], start
        while d <= end:
            if self.is_session(d):
                out.append(d)
            d += timedelta(days=1)
        return out
