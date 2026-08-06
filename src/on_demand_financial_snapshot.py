"""Build a compact, page-linked financial snapshot from one annual report.

The snapshot is an extraction candidate, not audited financial data.  It is
designed for an on-demand workflow: the source PDF can be released after this
small structure has been created.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timezone
from html import escape
from typing import TypedDict

from src.audited_company_onboarding import (
    CandidateReportResult,
    rmb_unit_multiplier,
)
from src.china_stock import is_allowed_disclosure_url


SNAPSHOT_SCHEMA_VERSION = "1.0"


class SnapshotMetric(TypedDict):
    """One current/prior financial value with statement provenance."""

    key: str
    label: str
    current_yuan: float | None
    previous_yuan: float | None
    change_rate: float | None
    statement: str
    pages: dict[str, int] | None


class OnDemandFinancialSnapshot(TypedDict):
    """Compact output retained after an annual-report PDF is released."""

    schema_version: str
    generated_at: str
    status: str
    status_label: str
    company: dict[str, str]
    report: dict[str, object]
    source_fingerprint_sha256: str
    statement_checks: dict[str, bool]
    unit: str | None
    unit_note: str
    metrics: list[SnapshotMetric]
    ratios: dict[str, float | None]
    limitations: list[str]


_METRIC_DEFINITIONS = (
    (
        "revenue",
        "营业收入",
        "current_revenue",
        "previous_revenue",
        "income_statement",
        "利润表",
    ),
    (
        "net_profit",
        "净利润（优先归母口径）",
        "current_net_profit",
        "previous_net_profit",
        "income_statement",
        "利润表",
    ),
    (
        "operating_cash_flow",
        "经营活动现金流量净额",
        "current_operating_cash_flow",
        "previous_operating_cash_flow",
        "cash_flow_statement",
        "现金流量表",
    ),
    (
        "total_assets",
        "资产总额",
        "current_total_assets",
        "previous_total_assets",
        "balance_sheet",
        "资产负债表",
    ),
    (
        "total_liabilities",
        "负债总额",
        "current_total_liabilities",
        "previous_total_liabilities",
        "balance_sheet",
        "资产负债表",
    ),
)


def _finite_optional(value: object) -> float | None:
    """Return one finite number while preserving a genuine missing value."""
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("自动提取结果包含非有限数值，已停止生成财务快照。")
    return number


def _safe_change_rate(
    current: float | None,
    previous: float | None,
) -> float | None:
    """Calculate a change rate only when its denominator is usable."""
    if current is None or previous in {None, 0.0}:
        return None
    return (current - previous) / previous


def _safe_ratio(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    """Calculate a ratio without disguising a missing or zero denominator."""
    if numerator is None or denominator in {None, 0.0}:
        return None
    return numerator / denominator


def build_on_demand_financial_snapshot(
    company: Mapping[str, object],
    result: CandidateReportResult,
    *,
    generated_at: datetime | None = None,
) -> OnDemandFinancialSnapshot:
    """Normalise one candidate extraction into a reviewable RMB snapshot."""
    required_identity = {
        "code",
        "name",
        "exchange",
        "exchange_name",
        "canonical_code",
    }
    if not required_identity.issubset(company):
        raise ValueError("公司身份字段不完整，不能生成财务快照。")

    source_url = str(result.get("source_url", "")).strip()
    if not is_allowed_disclosure_url(source_url):
        raise ValueError("财务快照只接受受信任的交易所或巨潮资讯来源。")

    unit_check = result.get("unit_check", {})
    raw_units = unit_check.get("units", [])
    units = (
        [str(item).strip() for item in raw_units]
        if isinstance(raw_units, list)
        else []
    )
    statement_checks = dict(result.get("statement_checks", {}))
    unit = units[0] if len(units) == 3 and len(set(units)) == 1 else None
    multiplier: float | None = None
    automatic_checks_pass = (
        result.get("status") == "ready_for_human_review"
        and unit_check.get("passed") is True
        and all(statement_checks.values())
        and len(statement_checks) == 3
    )
    if automatic_checks_pass and unit:
        try:
            multiplier = rmb_unit_multiplier(unit)
        except ValueError:
            multiplier = None

    metrics: list[SnapshotMetric] = []
    values = result.get("values", {})
    pages_by_statement = result.get("statement_pages", {})
    for (
        key,
        label,
        current_key,
        previous_key,
        statement_key,
        statement_label,
    ) in _METRIC_DEFINITIONS:
        current_raw = _finite_optional(values.get(current_key))
        previous_raw = _finite_optional(values.get(previous_key))
        current_yuan = (
            current_raw * multiplier
            if current_raw is not None and multiplier is not None
            else None
        )
        previous_yuan = (
            previous_raw * multiplier
            if previous_raw is not None and multiplier is not None
            else None
        )
        raw_pages = pages_by_statement.get(statement_key)
        pages = (
            {"start": int(raw_pages["start"]), "end": int(raw_pages["end"])}
            if isinstance(raw_pages, Mapping)
            and "start" in raw_pages
            and "end" in raw_pages
            else None
        )
        metrics.append(
            {
                "key": key,
                "label": label,
                "current_yuan": current_yuan,
                "previous_yuan": previous_yuan,
                "change_rate": _safe_change_rate(current_yuan, previous_yuan),
                "statement": statement_label,
                "pages": pages,
            }
        )

    metric_by_key = {item["key"]: item for item in metrics}
    revenue = metric_by_key["revenue"]["current_yuan"]
    net_profit = metric_by_key["net_profit"]["current_yuan"]
    operating_cash_flow = metric_by_key["operating_cash_flow"]["current_yuan"]
    total_assets = metric_by_key["total_assets"]["current_yuan"]
    total_liabilities = metric_by_key["total_liabilities"]["current_yuan"]
    ready = (
        automatic_checks_pass
        and multiplier is not None
        and all(item["current_yuan"] is not None for item in metrics)
    )

    generated = generated_at or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": generated.astimezone(timezone.utc).isoformat(),
        "status": "ready_for_human_review" if ready else "needs_review",
        "status_label": (
            "自动检查完成，等待人工复核"
            if ready
            else "自动检查未通过，需要查看年报原文"
        ),
        "company": {
            key: str(company[key])
            for key in (
                "code",
                "name",
                "exchange",
                "exchange_name",
                "canonical_code",
            )
        },
        "report": {
            "report_year": int(result["report_year"]),
            "published_date": str(result["published_date"]),
            "title": str(result["title"]),
            "source_url": source_url,
            "page_count": int(result["page_count"]),
        },
        "source_fingerprint_sha256": str(
            result["evidence_fingerprint_sha256"]
        ),
        "statement_checks": statement_checks,
        "unit": unit if multiplier is not None else None,
        "unit_note": (
            f"三张报表原始单位均为“{unit}”，页面数值已统一换算为人民币元。"
            if ready
            else "金额单位、三表勾稽或核心数值未全部通过，系统未输出标准化金额。"
        ),
        "metrics": metrics,
        "ratios": {
            "net_profit_margin": _safe_ratio(net_profit, revenue),
            "operating_cash_conversion": _safe_ratio(
                operating_cash_flow,
                net_profit,
            ),
            "liabilities_to_assets": _safe_ratio(
                total_liabilities,
                total_assets,
            ),
        },
        "limitations": [
            "本结果由程序从最新完整年度报告自动提取，未经人工复核或审计。",
            "跨期增速使用同一份年报中的上年同期/上年末比较栏，可能包含追溯调整。",
            "银行、保险等特殊报表版式或扫描版PDF可能无法通过自动勾稽。",
            "财务快照用于缩短资料整理时间，不构成估值结论或投资建议。",
        ],
    }


def _format_amount(value: float | None) -> str:
    """Format RMB yuan as a compact Chinese display value."""
    if value is None:
        return "待核验"
    return f"¥{value / 100_000_000:,.2f}亿元"


def _format_percent(value: float | None) -> str:
    """Format a ratio while retaining an explicit unavailable state."""
    return "待核验" if value is None else f"{value:.1%}"


def _format_pages(pages: Mapping[str, int] | None) -> str:
    """Format one inclusive PDF page range."""
    if not pages:
        return "待核验"
    start = int(pages["start"])
    end = int(pages["end"])
    return str(start) if start == end else f"{start}–{end}"


def build_financial_snapshot_report_html(
    snapshot: OnDemandFinancialSnapshot,
) -> str:
    """Create a portable, escaped review report with official provenance."""
    company = snapshot["company"]
    report = snapshot["report"]
    source_url = str(report.get("source_url", ""))
    safe_source_link = (
        f'<a href="{escape(source_url, quote=True)}">查看官方年报原文</a>'
        if is_allowed_disclosure_url(source_url)
        else "官方链接未通过域名校验"
    )
    metric_rows = "".join(
        "<tr>"
        f"<td>{escape(item['label'])}</td>"
        f"<td>{escape(_format_amount(item['current_yuan']))}</td>"
        f"<td>{escape(_format_amount(item['previous_yuan']))}</td>"
        f"<td>{escape(_format_percent(item['change_rate']))}</td>"
        f"<td>{escape(item['statement'])} 第"
        f"{escape(_format_pages(item['pages']))}页</td>"
        "</tr>"
        for item in snapshot["metrics"]
    )
    ratio_labels = {
        "net_profit_margin": "净利率（同一提取口径）",
        "operating_cash_conversion": "经营现金流 / 净利润",
        "liabilities_to_assets": "资产负债率",
    }
    ratio_items = "".join(
        f"<li>{escape(ratio_labels[key])}：{escape(_format_percent(value))}</li>"
        for key, value in snapshot["ratios"].items()
    )
    limitation_items = "".join(
        f"<li>{escape(item)}</li>" for item in snapshot["limitations"]
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(company['name'])}财务快照</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
max-width:980px;margin:40px auto;padding:0 24px;color:#13243a;line-height:1.65}}
.notice{{padding:14px 18px;background:#fff4d6;border-left:4px solid #d99000}}
table{{border-collapse:collapse;width:100%;margin:20px 0}}
th,td{{border:1px solid #d9e1ea;padding:10px;text-align:left}}
th{{background:#edf3f8}} small{{color:#5d6b7a}} a{{color:#075ea8}}
</style></head><body>
<p><small>FANGZHENG AI · 全市场按需财务快照 Agent</small></p>
<h1>{escape(company['name'])}｜{escape(company['canonical_code'])}</h1>
<p class="notice"><strong>{escape(snapshot['status_label'])}</strong><br>
自动提取候选，未经人工复核，不构成投资建议。</p>
<h2>来源报告</h2>
<p>{escape(str(report['title']))}<br>
报告期：{escape(str(report['report_year']))}｜公告日：
{escape(str(report['published_date']))}｜{safe_source_link}</p>
<p>{escape(snapshot['unit_note'])}</p>
<h2>核心财务快照</h2>
<table><thead><tr><th>指标</th><th>本期</th><th>上期比较栏</th>
<th>变化</th><th>证据页</th></tr></thead><tbody>{metric_rows}</tbody></table>
<h2>确定性计算</h2><ul>{ratio_items}</ul>
<h2>使用边界</h2><ul>{limitation_items}</ul>
<p><small>生成时间（UTC）：{escape(snapshot['generated_at'])}<br>
证据文件 SHA-256：{escape(snapshot['source_fingerprint_sha256'])}</small></p>
</body></html>"""
