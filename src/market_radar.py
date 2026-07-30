"""Build a bounded, deterministic watchlist anomaly radar."""

from __future__ import annotations

import re
from typing import TypedDict

from src.china_stock import CompanyIdentity, MarketActivityEvidence


class WatchlistParseResult(TypedDict):
    """Validated six-digit codes plus transparent input limits."""

    codes: list[str]
    invalid_tokens: list[str]
    duplicate_count: int
    omitted_count: int


class MarketRadarRow(TypedDict):
    """One company's latest-session evidence for the watchlist wall."""

    company: CompanyIdentity
    latest_date: str
    daily_return: float | None
    volume_ratio_20d: float | None
    turnover: float | None
    turnover_percentile_250d: float | None
    limit_up_candidate: bool
    triggered_signals: list[str]
    trigger_count: int
    available_signal_count: int
    radar_status: str
    market_source: str
    turnover_source: str


def parse_watchlist_codes(
    text: str,
    *,
    max_codes: int = 5,
) -> WatchlistParseResult:
    """Parse comma/space-separated codes while preserving first-seen order."""
    tokens = [
        token
        for token in re.split(r"[\s,，;；、]+", str(text).strip())
        if token
    ]
    valid_unique: list[str] = []
    invalid_tokens: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0

    for token in tokens:
        if re.fullmatch(r"\d{6}", token) is None:
            invalid_tokens.append(token)
            continue
        if token in seen:
            duplicate_count += 1
            continue
        seen.add(token)
        valid_unique.append(token)

    omitted_count = max(0, len(valid_unique) - max_codes)
    return {
        "codes": valid_unique[:max_codes],
        "invalid_tokens": invalid_tokens,
        "duplicate_count": duplicate_count,
        "omitted_count": omitted_count,
    }


def build_market_radar_row(
    company: CompanyIdentity,
    activity: MarketActivityEvidence,
    *,
    market_source: str,
    turnover_source: str,
) -> MarketRadarRow:
    """Translate existing activity evidence into three transparent triggers."""
    limit_up_candidate = activity["limit_up_status"] == "涨停候选"
    volume_ratio = activity["volume_ratio_20d"]
    turnover_percentile = activity["turnover_percentile_250d"]
    triggered_signals: list[str] = []
    if limit_up_candidate:
        triggered_signals.append("涨停候选")
    if volume_ratio is not None and volume_ratio >= 2:
        triggered_signals.append("明显放量")
    if turnover_percentile is not None and turnover_percentile >= 0.9:
        triggered_signals.append("普通换手率历史高位")

    available_signal_count = sum(
        (
            activity["daily_return"] is not None,
            volume_ratio is not None,
            turnover_percentile is not None,
        )
    )
    trigger_count = len(triggered_signals)
    if trigger_count >= 2:
        radar_status = "复合异动"
    elif trigger_count == 1:
        radar_status = "单项异动"
    elif available_signal_count < 3:
        radar_status = "未触发（部分数据缺失）"
    else:
        radar_status = "未触发"

    return {
        "company": company,
        "latest_date": activity["latest_date"],
        "daily_return": activity["daily_return"],
        "volume_ratio_20d": volume_ratio,
        "turnover": activity["turnover"],
        "turnover_percentile_250d": turnover_percentile,
        "limit_up_candidate": limit_up_candidate,
        "triggered_signals": triggered_signals,
        "trigger_count": trigger_count,
        "available_signal_count": available_signal_count,
        "radar_status": radar_status,
        "market_source": market_source,
        "turnover_source": turnover_source,
    }


def rank_market_radar(
    rows: list[MarketRadarRow],
) -> list[MarketRadarRow]:
    """Rank evidence strength without converting it into a buy/sell score."""

    def sort_key(row: MarketRadarRow) -> tuple[object, ...]:
        volume_ratio = row["volume_ratio_20d"]
        turnover_percentile = row["turnover_percentile_250d"]
        return (
            -row["trigger_count"],
            -int(row["limit_up_candidate"]),
            -(volume_ratio if volume_ratio is not None else -1.0),
            -(
                turnover_percentile
                if turnover_percentile is not None
                else -1.0
            ),
            row["company"]["code"],
        )

    return sorted(rows, key=sort_key)
