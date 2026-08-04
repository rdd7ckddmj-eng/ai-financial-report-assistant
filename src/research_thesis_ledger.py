"""Deterministic helpers for a human-reviewed research thesis ledger."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from html import escape

from src.browser_research_state import THESIS_STATUSES, THESIS_TOPICS
from src.china_stock import CompanyIdentity, is_allowed_disclosure_url


def matching_evidence_items(
    thesis: Mapping[str, object],
    evidence_items: Sequence[Mapping[str, object]],
    *,
    limit: int = 5,
) -> list[Mapping[str, object]]:
    """Return topic-matched official evidence without inferring direction."""
    topic = thesis.get("topic")
    if topic not in THESIS_TOPICS or limit <= 0:
        return []
    result: list[Mapping[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in evidence_items:
        source_url = str(item.get("source_url", "")).strip()
        title = str(item.get("title", "")).strip()
        published_date = str(item.get("published_date", "")).strip()
        if (
            item.get("evidence_group") != topic
            or not title
            or not is_allowed_disclosure_url(source_url)
        ):
            continue
        key = (published_date, title, source_url)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def thesis_status_counts(
    theses: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    """Count only recognised human-assigned thesis states."""
    return {
        status: sum(thesis.get("status") == status for thesis in theses)
        for status in THESIS_STATUSES
    }


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _evidence_html(thesis: Mapping[str, object]) -> str:
    source_url = str(thesis.get("evidence_url", "")).strip()
    title = str(thesis.get("evidence_title", "")).strip()
    published_date = str(thesis.get("evidence_date", "")).strip()
    if not title or not is_allowed_disclosure_url(source_url):
        return '<p class="muted">本次状态未绑定官方证据。</p>'
    return (
        '<div class="evidence"><strong>本次引用：</strong>'
        f"{_text(published_date)}｜{_text(title)}<br>"
        f'<a href="{_text(source_url)}" target="_blank" '
        'rel="noopener noreferrer">查看官方原文 ↗</a></div>'
    )


def build_thesis_ledger_report_html(
    company: CompanyIdentity,
    theses: Sequence[Mapping[str, object]],
    *,
    generated_on: date,
) -> str:
    """Return a safe, portable HTML ledger using human-assigned statuses."""
    counts = thesis_status_counts(theses)
    summary_cards = "".join(
        "<div><span>{status}</span><strong>{count}</strong></div>".format(
            status=_text(status),
            count=count,
        )
        for status, count in counts.items()
    )
    thesis_cards = "".join(
        """
        <article>
          <div class="meta">{topic}｜状态：{status}｜更新：{updated_at}</div>
          <h2>{hypothesis}</h2>
          <div class="criteria confirm"><strong>支持条件</strong><p>{confirmation}</p></div>
          <div class="criteria invalidate"><strong>失效条件</strong><p>{invalidation}</p></div>
          <p><strong>人工复核备注：</strong>{review_note}</p>
          {evidence_html}
        </article>
        """.format(
            topic=_text(thesis.get("topic", "")),
            status=_text(thesis.get("status", "")),
            updated_at=_text(thesis.get("updated_at", "")),
            hypothesis=_text(thesis.get("hypothesis", "")),
            confirmation=_text(thesis.get("confirmation_criteria", "")),
            invalidation=_text(thesis.get("invalidation_criteria", "")),
            review_note=_text(thesis.get("review_note", "尚未填写")),
            evidence_html=_evidence_html(thesis),
        )
        for thesis in theses
    )
    if not thesis_cards:
        thesis_cards = '<div class="empty">当前公司还没有研究假设。</div>'

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WFZ 研究结论账本｜{company_name}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #edf2f5; color: #14233a; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; }}
    main {{ width: min(980px, calc(100% - 32px)); margin: 30px auto; padding: 38px; background: white; border-radius: 20px; box-shadow: 0 18px 55px rgba(11,31,58,.12); }}
    header {{ margin: -38px -38px 28px; padding: 38px; color: white; background: linear-gradient(120deg, #0b1f3a, #123f63 58%, #0f9b8e); border-radius: 20px 20px 0 0; }}
    h1 {{ margin: 5px 0; }} h2 {{ margin: 7px 0 16px; font-size: 20px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 22px 0; }}
    .summary div, .criteria {{ padding: 14px; border: 1px solid #dce5ec; border-radius: 12px; }}
    .summary span, .summary strong {{ display: block; }} .summary strong {{ font-size: 22px; }}
    article {{ margin: 20px 0; padding: 22px; border: 1px solid #dce5ec; border-top: 5px solid #0f9b8e; border-radius: 15px; break-inside: avoid; }}
    .meta, .muted {{ color: #65758b; font-size: 14px; }}
    .criteria {{ display: inline-block; width: calc(50% - 6px); vertical-align: top; background: #f3f7f9; }}
    .criteria.invalidate {{ margin-left: 8px; border-color: #efd39c; background: #fff9ed; }}
    .criteria p {{ margin: 5px 0 0; }} .evidence {{ padding: 14px; background: #edf7f6; border-radius: 11px; }}
    a {{ color: #087f75; font-weight: 700; text-decoration: none; }}
    .empty {{ padding: 18px; background: #f3f7f9; border-left: 4px solid #0f9b8e; }}
    @media (max-width: 720px) {{ main {{ padding: 22px; }} header {{ margin: -22px -22px 22px; }} .summary {{ grid-template-columns: repeat(2, 1fr); }} .criteria {{ display: block; width: 100%; }} .criteria.invalidate {{ margin: 8px 0 0; }} }}
  </style>
</head>
<body><main>
  <header><div>WFZ RESEARCH THESIS LEDGER</div><h1>{company_name}｜{canonical_code}</h1><p>研究假设、验证条件与人工复核记录 · 生成于 {generated_on}</p></header>
  <div class="summary">{summary_cards}</div>
  {thesis_cards}
  <p class="muted">状态和复核备注由用户人工指定。系统只按主题匹配官方证据，不根据公告标题自动判断支持、反驳、利好或利空。本报告不构成投资建议。</p>
</main></body></html>""".format(
        company_name=_text(company["name"]),
        canonical_code=_text(company["canonical_code"]),
        generated_on=generated_on.isoformat(),
        summary_cards=summary_cards,
        thesis_cards=thesis_cards,
    )
