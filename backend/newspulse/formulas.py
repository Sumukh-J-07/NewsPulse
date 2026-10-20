"""Target formula, signal labels, errors and evaluation metrics (SRS sections 1.3, 4.1, 4.2, 4.4).

Percentages are percent values: 1.25 means 1.25 %. Errors are percentage points.
Missing values stay ``None``; they are never coerced to zero.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def pct_change(reference_close: float | None, new_close: float | None) -> float | None:
    """100 * (new - reference) / reference. Returns None if either input is unusable."""
    if not (_finite(reference_close) and _finite(new_close)):
        return None
    if reference_close <= 0 or new_close <= 0:
        return None  # zero/negative closes are invalid market data, not a 0 % change
    return 100.0 * (new_close - reference_close) / reference_close


def implied_close(reference_close: float, estimated_change_pct: float) -> float:
    """Predicted close implied by an estimated percent change (inverse of pct_change)."""
    return reference_close * (1.0 + estimated_change_pct / 100.0)


def signal_label(estimate_pct: float | None, threshold_pp: float = 0.25) -> str | None:
    """Bullish if > +theta, bearish if < -theta, neutral otherwise (boundaries are neutral)."""
    if not _finite(estimate_pct):
        return None
    if estimate_pct > threshold_pp:
        return "bullish"
    if estimate_pct < -threshold_pp:
        return "bearish"
    return "neutral"


def direction(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def forecast_errors(estimate_pct: float | None, actual_pct: float | None) -> tuple[float | None, float | None]:
    """(signed, absolute) error in percentage points; signed = estimate - actual."""
    if not (_finite(estimate_pct) and _finite(actual_pct)):
        return None, None
    signed = estimate_pct - actual_pct
    return signed, abs(signed)


def mae(pairs: Iterable[tuple[float, float]]) -> float | None:
    values = [abs(e - a) for e, a in pairs if _finite(e) and _finite(a)]
    return sum(values) / len(values) if values else None


def directional_accuracy(pairs: Iterable[tuple[float, float]]) -> float | None:
    """Fraction (0-1) of pairs whose sign matches; zero is treated as neutral."""
    values = [direction(e) == direction(a) for e, a in pairs if _finite(e) and _finite(a)]
    return sum(values) / len(values) if values else None


def evaluate(estimates: Sequence[float], actuals: Sequence[float]) -> dict:
    if len(estimates) != len(actuals):
        raise ValueError("estimates and actuals must align")
    pairs = list(zip(estimates, actuals))
    return {"mae_pp": mae(pairs), "directional_accuracy": directional_accuracy(pairs), "sample_count": len(pairs)}
