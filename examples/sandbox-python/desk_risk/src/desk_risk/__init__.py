"""Portfolio helpers installed on the example sandbox worker."""

from __future__ import annotations

from datetime import date


def herfindahl(weights: dict[str, float]) -> float:
    """Herfindahl-Hirschman index of ticker weights. 1.0 is a single name."""
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return sum((float(value) / total) ** 2 for value in weights.values())


def next_review(as_of: date, months: int = 12) -> date:
    """Next scheduled review. Uses python-dateutil, which the stock worker does not ship."""
    from dateutil.relativedelta import relativedelta

    return as_of + relativedelta(months=months)
