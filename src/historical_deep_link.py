"""Validate shareable Historical Lens query parameters."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import TypedDict


class HistoricalDeepLink(TypedDict):
    """A validated company-and-date entry point for Historical Lens."""

    code: str
    event_date: date
    source: str | None


def _first_text(value: object) -> str:
    """Read the first value from either scalar or list-style query params."""
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        value = value[0]
    return str(value).strip()


def parse_historical_deep_link(
    params: Mapping[str, object],
    *,
    today: date,
) -> HistoricalDeepLink | None:
    """Return only safe A-share code/date parameters inside the page window."""
    code = _first_text(params.get("code", ""))
    event_date_text = _first_text(params.get("date", ""))
    if re.fullmatch(r"\d{6}", code) is None:
        return None

    try:
        event_date = date.fromisoformat(event_date_text)
    except ValueError:
        return None

    earliest_date = today - timedelta(days=365 * 5)
    if not earliest_date <= event_date <= today:
        return None

    raw_source = _first_text(params.get("source", ""))
    source = "anomaly-report" if raw_source == "anomaly-report" else None
    return {
        "code": code,
        "event_date": event_date,
        "source": source,
    }
