"""Build a bounded, deterministic watchlist research task queue."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import TypedDict

from src.china_stock import (
    CompanyIdentity,
    MarketActivityEvidence,
    is_allowed_disclosure_url,
)


class WatchlistParseResult(TypedDict):
    """Validated six-digit codes plus transparent input limits."""

    codes: list[str]
    invalid_tokens: list[str]
    duplicate_count: int
    omitted_count: int


class MarketRadarRow(TypedDict):
    """One company's latest-session evidence for the research queue."""

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


class RadarDisclosure(TypedDict):
    """One recent official disclosure attached to a radar company."""

    title: str
    published_date: str
    source_url: str
    category: str
    attention: str
    days_old: int


class ResearchQueueRow(MarketRadarRow):
    """A radar row enriched with a non-predictive research task priority."""

    latest_disclosure: RadarDisclosure | None
    disclosure_status: str
    research_priority: str
    research_reasons: list[str]


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


def _as_date(value: object) -> date | None:
    """Normalise supported disclosure-date values without guessing."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def build_research_queue_row(
    radar_row: MarketRadarRow,
    disclosures: Sequence[Mapping[str, object]] | None,
    *,
    as_of_date: date,
    disclosure_status: str = "已核验",
) -> ResearchQueueRow:
    """Attach recent official evidence and assign a review priority.

    P1/P2/P3 only schedules research work.  It never represents expected
    return, investment quality, or the direction of an announcement's impact.
    """
    candidates: list[RadarDisclosure] = []
    if disclosures is not None:
        attention_order = {"高": 3, "中": 2, "低": 1}
        for disclosure in disclosures:
            published_date = _as_date(disclosure.get("date"))
            title = str(disclosure.get("title", "")).strip()
            source_url = str(disclosure.get("url", "")).strip()
            raw_category = disclosure.get("category")
            raw_attention = disclosure.get("attention")
            category = (
                str(raw_category).strip()
                if raw_category is not None
                else "其他公告"
            )
            attention = (
                str(raw_attention).strip()
                if raw_attention is not None
                else "低"
            )
            if (
                published_date is None
                or published_date > as_of_date
                or not title
                or not is_allowed_disclosure_url(source_url)
            ):
                continue
            if attention not in attention_order:
                attention = "低"
            candidates.append(
                {
                    "title": title,
                    "published_date": published_date.isoformat(),
                    "source_url": source_url,
                    "category": category or "其他公告",
                    "attention": attention,
                    "days_old": (as_of_date - published_date).days,
                }
            )
        candidates.sort(
            key=lambda item: (
                item["published_date"],
                attention_order[item["attention"]],
                item["title"],
            ),
            reverse=True,
        )

    latest_disclosure = candidates[0] if candidates else None
    trigger_count = radar_row["trigger_count"]
    urgent_disclosure = next(
        (
            disclosure
            for disclosure in candidates
            if disclosure["attention"] == "高"
            and disclosure["days_old"] <= 2
        ),
        None,
    )
    recent_priority_disclosure = next(
        (
            disclosure
            for disclosure in candidates
            if disclosure["attention"] in {"高", "中"}
            and disclosure["days_old"] <= 7
        ),
        None,
    )

    if trigger_count >= 2 or urgent_disclosure:
        research_priority = "P1｜立即核查"
    elif trigger_count == 1 or recent_priority_disclosure:
        research_priority = "P2｜优先复盘"
    else:
        research_priority = "P3｜常规跟踪"

    research_reasons: list[str] = []
    if trigger_count >= 2:
        research_reasons.append(
            f"市场端同时触发{trigger_count}项异动证据"
        )
    elif trigger_count == 1:
        research_reasons.append("市场端触发1项异动证据")
    if recent_priority_disclosure is not None:
        research_reasons.append(
            f"近{recent_priority_disclosure['days_old']}天有"
            f"{recent_priority_disclosure['attention']}关注官方公告："
            f"{recent_priority_disclosure['category']}"
        )
    if disclosures is None:
        research_reasons.append(
            "官方公告源本次不可访问，未用新闻或AI猜测替代"
        )
    elif latest_disclosure is None:
        research_reasons.append("查询窗口内没有可展示的官方公告")
    if not research_reasons:
        research_reasons.append(
            "当前未触发异动门槛，也无近7日高/中关注官方公告"
        )

    return {
        **radar_row,
        "latest_disclosure": latest_disclosure,
        "disclosure_status": disclosure_status,
        "research_priority": research_priority,
        "research_reasons": research_reasons,
    }


def rank_research_queue(
    rows: Sequence[ResearchQueueRow],
) -> list[ResearchQueueRow]:
    """Order research tasks without exposing a numeric investment score."""
    priority_order = {
        "P1｜立即核查": 1,
        "P2｜优先复盘": 2,
        "P3｜常规跟踪": 3,
    }

    def sort_key(row: ResearchQueueRow) -> tuple[object, ...]:
        latest_disclosure = row["latest_disclosure"]
        disclosure_days = (
            latest_disclosure["days_old"]
            if latest_disclosure is not None
            else 10_000
        )
        return (
            priority_order[row["research_priority"]],
            -row["trigger_count"],
            disclosure_days,
            row["company"]["code"],
        )

    return sorted(rows, key=sort_key)
