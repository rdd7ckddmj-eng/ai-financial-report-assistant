"""Small manually verified flagship cases for portfolio demonstrations."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOUTAI_EVENTS_PATH = (
    PROJECT_ROOT / "data" / "verified" / "moutai_historical_events.csv"
)
ALLOWED_EVENT_HOSTS = {
    "www.sse.com.cn",
    "static.sse.com.cn",
    "www.moutaichina.com",
}


class FlagshipEvent(TypedDict):
    """One manually checked event entry used as a Historical Lens shortcut."""

    company_code: str
    company_name: str
    event_id: str
    event_date: date
    published_date: date
    title: str
    category: str
    source_url: str
    evidence_grade: str
    verification_status: str
    why_important: str


def _parse_event_date(value: str, field_name: str) -> date:
    """Parse a required ISO date with a useful data-quality error."""
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as error:
        raise ValueError(
            f"旗舰案例中的 {field_name} 不是有效日期。"
        ) from error


def _validate_event(row: dict[str, str]) -> FlagshipEvent:
    """Validate identity, date order, source, and verification state."""
    event_date = _parse_event_date(row["event_date"], "event_date")
    published_date = _parse_event_date(
        row["published_date"],
        "published_date",
    )
    source_url = str(row["source_url"]).strip()
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in (
        ALLOWED_EVENT_HOSTS
    ):
        raise ValueError("旗舰案例必须使用允许的官方 HTTPS 来源。")
    if row["company_code"] != "600519":
        raise ValueError("贵州茅台旗舰案例的股票代码必须是 600519。")
    if row["evidence_grade"] != "A":
        raise ValueError("旗舰案例必须保留 A 级官方证据。")
    if row["verification_status"] != "verified":
        raise ValueError("未核验事件不能进入旗舰案例。")
    if not row["event_id"].strip() or not row["title"].strip():
        raise ValueError("旗舰案例缺少事件编号或标题。")

    return {
        "company_code": row["company_code"],
        "company_name": row["company_name"],
        "event_id": row["event_id"],
        "event_date": event_date,
        "published_date": published_date,
        "title": row["title"],
        "category": row["category"],
        "source_url": source_url,
        "evidence_grade": row["evidence_grade"],
        "verification_status": row["verification_status"],
        "why_important": row["why_important"],
    }


def load_moutai_flagship_events(
    path: Path = MOUTAI_EVENTS_PATH,
) -> list[FlagshipEvent]:
    """Load the small source-controlled and manually verified event list."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise ValueError("无法读取贵州茅台旗舰案例数据。") from error

    if not rows:
        raise ValueError("贵州茅台旗舰案例数据为空。")
    events = [_validate_event(row) for row in rows]
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("贵州茅台旗舰案例存在重复事件编号。")
    return sorted(events, key=lambda event: event["event_date"])
