"""Build a deterministic, source-linked change brief for official disclosures."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from html import escape
from typing import TypedDict

from src.china_stock import CompanyIdentity, is_allowed_disclosure_url


INITIAL_LOOKBACK_DAYS = 30
MAX_DELTA_LOOKBACK_DAYS = 365
MAX_DELTA_ITEMS = 100


class EvidenceWindow(TypedDict):
    """Bounded announcement-query window derived from a local checkpoint."""

    start_date: date
    end_date: date
    baseline_date: date | None
    mode: str
    truncated: bool


class EvidenceDeltaItem(TypedDict):
    """One validated official disclosure in a change review."""

    title: str
    published_date: date
    source_url: str
    source_category: str
    evidence_group: str
    attention: str
    delta_status: str


class EvidenceDeltaReview(TypedDict):
    """Portable evidence-change result rendered by Streamlit and HTML."""

    company: CompanyIdentity
    window: EvidenceWindow
    items: list[EvidenceDeltaItem]
    total_count: int
    high_attention_count: int
    group_counts: dict[str, int]
    item_limit_reached: bool
    generated_on: date


_GROUP_MAP = {
    "财务报告": "财务与业绩",
    "业绩动态": "财务与业绩",
    "经营动态": "经营事项",
    "分红与回购": "资本运作",
    "股权与资本": "资本运作",
    "公司治理": "治理与风险",
    "监管与风险": "治理与风险",
}
_GROUP_ORDER = (
    "财务与业绩",
    "经营事项",
    "资本运作",
    "治理与风险",
    "其他",
)
_ATTENTION_ORDER = {"高": 0, "中": 1, "低": 2}


def _parse_checkpoint_date(value: object) -> date | None:
    """Read an ISO timestamp without trusting browser-provided input."""
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        try:
            return date.fromisoformat(cleaned[:10])
        except ValueError:
            return None


def build_evidence_window(
    last_checked_at: object,
    *,
    as_of_date: date,
) -> EvidenceWindow:
    """Return a small, explicit query window for an evidence recheck."""
    baseline_date = _parse_checkpoint_date(last_checked_at)
    if baseline_date is None or baseline_date > as_of_date:
        return {
            "start_date": as_of_date - timedelta(
                days=INITIAL_LOOKBACK_DAYS - 1
            ),
            "end_date": as_of_date,
            "baseline_date": None,
            "mode": "首次基准",
            "truncated": False,
        }

    earliest_date = as_of_date - timedelta(
        days=MAX_DELTA_LOOKBACK_DAYS - 1
    )
    return {
        # Include the checkpoint date so same-day announcements are not missed.
        "start_date": max(baseline_date, earliest_date),
        "end_date": as_of_date,
        "baseline_date": baseline_date,
        "mode": "增量复核",
        "truncated": baseline_date < earliest_date,
    }


def _normalise_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    to_date = getattr(value, "date", None)
    if callable(to_date):
        result = to_date()
        return result if isinstance(result, date) else None
    return None


def _build_item(
    raw: Mapping[str, object],
    window: EvidenceWindow,
) -> EvidenceDeltaItem | None:
    title = str(raw.get("title", "")).strip()
    source_url = str(raw.get("url", "")).strip()
    published_date = _normalise_date(raw.get("date"))
    if (
        not title
        or published_date is None
        or not is_allowed_disclosure_url(source_url)
        or published_date < window["start_date"]
        or published_date > window["end_date"]
    ):
        return None

    source_category = str(raw.get("category", "其他公告")).strip()
    if not source_category:
        source_category = "其他公告"
    attention = str(raw.get("attention", "低")).strip()
    if attention not in _ATTENTION_ORDER:
        attention = "低"

    baseline_date = window["baseline_date"]
    if baseline_date is None:
        delta_status = "首次基准"
    elif published_date > baseline_date:
        delta_status = "新增"
    else:
        # The official feed exposes a date but not a reliable publication time.
        delta_status = "同日待复核"

    return {
        "title": title[:300],
        "published_date": published_date,
        "source_url": source_url,
        "source_category": source_category[:40],
        "evidence_group": _GROUP_MAP.get(source_category, "其他"),
        "attention": attention,
        "delta_status": delta_status,
    }


def build_evidence_delta_review(
    company: CompanyIdentity,
    announcements: Sequence[Mapping[str, object]],
    *,
    window: EvidenceWindow,
    generated_on: date,
) -> EvidenceDeltaReview:
    """Classify and deduplicate a bounded set of official announcements."""
    items: list[EvidenceDeltaItem] = []
    seen: set[tuple[date, str, str]] = set()
    for raw in announcements:
        item = _build_item(raw, window)
        if item is None:
            continue
        key = (
            item["published_date"],
            item["title"],
            item["source_url"],
        )
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    items.sort(
        key=lambda item: (
            item["published_date"],
            -_ATTENTION_ORDER[item["attention"]],
            item["title"],
        ),
        reverse=True,
    )
    total_count = len(items)
    displayed_items = items[:MAX_DELTA_ITEMS]
    counts = Counter(item["evidence_group"] for item in items)
    group_counts = {group: counts.get(group, 0) for group in _GROUP_ORDER}
    return {
        "company": company,
        "window": window,
        "items": displayed_items,
        "total_count": total_count,
        "high_attention_count": sum(
            item["attention"] == "高" for item in items
        ),
        "group_counts": group_counts,
        "item_limit_reached": total_count > MAX_DELTA_ITEMS,
        "generated_on": generated_on,
    }


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def build_evidence_delta_report_html(review: EvidenceDeltaReview) -> str:
    """Return a portable HTML change brief with validated official links."""
    company = review["company"]
    window = review["window"]
    group_cards = "".join(
        "<div><span>{group}</span><strong>{count}</strong></div>".format(
            group=_text(group),
            count=count,
        )
        for group, count in review["group_counts"].items()
    )
    item_cards = "".join(
        """
        <article>
          <div class="meta">{published_date}｜{group}｜{status}｜关注程度：{attention}</div>
          <h2>{title}</h2>
          <a href="{source_url}" target="_blank" rel="noopener noreferrer">查看官方原文 ↗</a>
        </article>
        """.format(
            published_date=item["published_date"].isoformat(),
            group=_text(item["evidence_group"]),
            status=_text(item["delta_status"]),
            attention=_text(item["attention"]),
            title=_text(item["title"]),
            source_url=_text(item["source_url"]),
        )
        for item in review["items"]
    )
    if not item_cards:
        item_cards = '<div class="empty">本次范围内未找到可核验的官方公告。</div>'
    baseline_text = (
        window["baseline_date"].isoformat()
        if window["baseline_date"] is not None
        else "首次建立基准"
    )
    limit_note = (
        f"报告只展示最近 {MAX_DELTA_ITEMS} 条，共核验 {review['total_count']} 条。"
        if review["item_limit_reached"]
        else f"共核验 {review['total_count']} 条。"
    )
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFZ 证据增量简报｜{company_name}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #edf2f5; color: #14233a; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; }}
    main {{ width: min(980px, calc(100% - 32px)); margin: 30px auto; padding: 38px; background: white; border-radius: 20px; box-shadow: 0 18px 55px rgba(11,31,58,.12); }}
    header {{ margin: -38px -38px 28px; padding: 38px; color: white; background: linear-gradient(120deg, #0b1f3a, #123f63 58%, #0f9b8e); border-radius: 20px 20px 0 0; }}
    h1 {{ margin: 5px 0; }} .muted, .meta {{ color: #65758b; font-size: 14px; }}
    .summary {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 22px 0; }}
    .summary div {{ padding: 14px; border: 1px solid #dce5ec; border-radius: 12px; }}
    .summary span, .summary strong {{ display: block; }} .summary strong {{ font-size: 22px; }}
    article {{ padding: 19px 0; border-top: 1px solid #dce5ec; break-inside: avoid; }}
    article h2 {{ margin: 6px 0; font-size: 18px; }} a {{ color: #087f75; font-weight: 700; text-decoration: none; }}
    .rule, .empty {{ padding: 16px; background: #f3f7f9; border-left: 4px solid #0f9b8e; }}
    @media (max-width: 760px) {{ main {{ padding: 22px; }} header {{ margin: -22px -22px 22px; }} .summary {{ grid-template-columns: repeat(2, 1fr); }} }}
  </style>
</head>
<body><main>
  <header><div>WFZ EVIDENCE DELTA AGENT</div><h1>{company_name}｜{canonical_code}</h1><p>官方披露变化简报 · 生成于 {generated_on}</p></header>
  <div class="rule"><strong>核验范围：</strong>{start_date} 至 {end_date}｜本地基准：{baseline_text}<br>{limit_note}</div>
  <div class="summary">{group_cards}</div>
  {item_cards}
  <p class="muted">“关注程度”只表示阅读优先级，不代表利好、利空或买卖建议。同日待复核表示官方数据只提供日期，无法可靠判断公告发生在基准保存前还是保存后。</p>
</main></body></html>""".format(
        company_name=_text(company["name"]),
        canonical_code=_text(company["canonical_code"]),
        generated_on=review["generated_on"].isoformat(),
        start_date=window["start_date"].isoformat(),
        end_date=window["end_date"].isoformat(),
        baseline_text=_text(baseline_text),
        limit_note=_text(limit_note),
        group_cards=group_cards,
        item_cards=item_cards,
    )
