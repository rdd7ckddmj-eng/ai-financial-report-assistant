"""Build a compact, page-linked financial snapshot from one annual report.

The snapshot is an extraction candidate, not audited financial data.  It is
designed for an on-demand workflow: the source PDF can be released after this
small structure has been created.
"""

from __future__ import annotations
from src.insurance_group_statement_extractor import TOTAL_REVENUE_TEMPLATES

import math
from copy import deepcopy
from src.bank_statement_extractor import BANK_TEMPLATE
from src.financial_sector_policy import is_special_financial_template, SECURITIES_REVENUE_TEMPLATES
from collections.abc import Mapping
from datetime import datetime, timezone
from html import escape
from typing import TypedDict

from src.audited_company_onboarding import (
    CandidateReportResult,
    rmb_unit_multiplier,
)
from src.china_stock import is_allowed_disclosure_url
from src.statement_evidence_rules import consistent_statement_unit


SNAPSHOT_SCHEMA_VERSION = "1.1"
MAX_METRIC_EXCERPT_CHARS = 480


class SnapshotMetricSource(TypedDict):
    """Original statement evidence retained for one core metric."""

    raw_current_value: float | None
    raw_previous_value: float | None
    original_unit: str
    accounting_basis: str
    comparison_basis: str
    comparison_comparable: bool
    statement: str
    pages: dict[str, int] | None
    excerpt: str
    excerpt_status: str


class SnapshotMetric(TypedDict):
    """One current/prior financial value with statement provenance."""

    key: str
    label: str
    current_yuan: float | None
    previous_yuan: float | None
    change_rate: float | None
    change_rate_note: str
    statement: str
    pages: dict[str, int] | None
    source: SnapshotMetricSource


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
    income_reconciliation: dict[str, object] | None
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
    """Do not label a loss reduction as negative percentage growth."""
    if current is None or previous is None or previous <= 0:
        return None
    result = (current - previous) / previous
    return result if math.isfinite(result) else None


def _change_rate_note(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "金额缺失或自动检查未通过，暂不计算变化率。"
    if previous <= 0:
        return "比较基期为零或负数，不展示百分比变化；请比较两期金额。"
    if _safe_change_rate(current, previous) is None:
        return "变化率超出可计算范围，暂不展示。"
    return ""


def _safe_ratio(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    """Match public-history rules; a loss is not a cash-conversion base."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def _normalise_pages(value: object) -> dict[str, int] | None:
    """Keep a valid inclusive page range without inventing provenance."""
    if not isinstance(value, Mapping):
        return None
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if start <= 0 or end < start:
        return None
    return {"start": start, "end": end}


def _normalise_metric_source(
    raw_source: object,
    *,
    current_raw: float | None,
    previous_raw: float | None,
    unit: str,
    statement: str,
    pages: dict[str, int] | None,
) -> SnapshotMetricSource:
    """Support old candidates while explicitly flagging missing excerpts."""
    source = raw_source if isinstance(raw_source, Mapping) else {}
    excerpt = " ".join(str(source.get("excerpt", "")).split())
    if len(excerpt) > MAX_METRIC_EXCERPT_CHARS:
        excerpt = excerpt[: MAX_METRIC_EXCERPT_CHARS - 1].rstrip() + "…"
    excerpt_status = str(source.get("excerpt_status", "")).strip()
    if not excerpt:
        excerpt_status = "unavailable_legacy"
    elif excerpt_status != "captured":
        excerpt_status = "captured"
    return {
        "raw_current_value": _finite_optional(
            source.get("raw_current_value", current_raw)
        ),
        "raw_previous_value": _finite_optional(
            source.get("raw_previous_value", previous_raw)
        ),
        "original_unit": str(
            source.get("original_unit", unit)
        ).strip(),
        "accounting_basis": str(
            source.get("accounting_basis", "报表口径待人工确认")
        ).strip()
        or "报表口径待人工确认",
        "comparison_comparable": source.get("comparison_comparable", True) is not False,
        "comparison_basis": str(
            source.get(
                "comparison_basis",
                "本期与年报比较栏原值；可能包含追溯调整",
            )
        ).strip(),
        "statement": str(source.get("statement", statement)).strip()
        or statement,
        "pages": _normalise_pages(source.get("pages")) or pages,
        "excerpt": excerpt,
        "excerpt_status": excerpt_status,
    }


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
    income_detail = result.get('income_reconciliation')
    if income_detail is not None and income_detail.get('status') != 'passed':
        statement_checks['income_statement_reconciled'] = False
    unit = consistent_statement_unit(units)
    multiplier: float | None = None
    automatic_checks_pass = (
        result.get("status") == "ready_for_human_review"
        and unit_check.get("passed") is True
        and all(statement_checks.values())
        and len(statement_checks) == 3
        and (income_detail is None or income_detail.get('status') == 'passed')
    )
    if automatic_checks_pass and unit:
        try:
            multiplier = rmb_unit_multiplier(unit)
        except ValueError:
            multiplier = None

    metrics: list[SnapshotMetric] = []
    values = result.get("values", {})
    pages_by_statement = result.get("statement_pages", {})
    metric_evidence = result.get("metric_evidence", {})
    if not isinstance(metric_evidence, Mapping):
        metric_evidence = {}
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
        pages = _normalise_pages(raw_pages)
        source = _normalise_metric_source(
            metric_evidence.get(key),
            current_raw=current_raw,
            previous_raw=previous_raw,
            unit=unit or "",
            statement=statement_label,
            pages=pages,
        )
        metrics.append(
            {
                "key": key,
                "label": "营业总收入（证券报表）" if key == "revenue" and result.get("statement_template") in SECURITIES_REVENUE_TEMPLATES else "营业总收入（保险报表）" if key == "revenue" and result.get("statement_template") in TOTAL_REVENUE_TEMPLATES else label,
                "current_yuan": current_yuan,
                "previous_yuan": previous_yuan,
                "change_rate": _safe_change_rate(current_yuan, previous_yuan) if source["comparison_comparable"] else None,
                "change_rate_note": _change_rate_note(current_yuan, previous_yuan) if source["comparison_comparable"] else "会计准则比较口径不一致，不自动计算同比。",
                "statement": source["statement"],
                "pages": source["pages"],
                "source": source,
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
        "extraction_note": str(result.get('extraction_note', '')),
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
            "statement_template": result.get('statement_template', 'general'),
            "report_year": int(result["report_year"]),
            "published_date": str(result["published_date"]),
            "title": str(result["title"]),
            "source_url": source_url,
            "page_count": int(result["page_count"]),
            **({'text_adjustments': deepcopy(result['pdf_text_adjustments'])}
               if result.get('pdf_text_adjustments') else {}),
            **({'cash_flow_layout_recoveries': deepcopy(result['cash_flow_layout_recoveries'])}
               if result.get('cash_flow_layout_recoveries') else {}),
            **({'income_layout_recoveries': deepcopy(result['income_layout_recoveries'])}
               if result.get('income_layout_recoveries') else {}),
        },
        "source_fingerprint_sha256": str(
            result["evidence_fingerprint_sha256"]
        ),
        "statement_checks": statement_checks,
        "income_reconciliation": result.get('income_reconciliation'),
        "statement_reconciliation": deepcopy(result.get('statement_reconciliation')),
        "unit": unit if multiplier is not None else None,
        "unit_note": (
            f"三张报表金额单位核对一致，按“{unit}”统一换算为人民币元；原文单位见各项证据。"
            if ready
            else "金额单位、三表勾稽或核心数值未全部通过，系统未输出标准化金额。"
        ),
        "metrics": metrics,
        "ratios": ({key: None for key in ('net_profit_margin', 'operating_cash_conversion', 'liabilities_to_assets')}
                   if is_special_financial_template(result.get('statement_template')) else {
            "net_profit_margin": _safe_ratio(net_profit, revenue),
            "operating_cash_conversion": _safe_ratio(
                operating_cash_flow,
                net_profit,
            ),
            "liabilities_to_assets": _safe_ratio(
                total_liabilities,
                total_assets,
            ),
        }),
        "limitations": [
            *([str(result['extraction_note'])] if result.get('extraction_note') else []),
            "本结果由程序从本次所选完整年度报告自动提取，未经人工复核或审计。",
            *(['本年报含带坐标依据的负号换行连接；原PDF与原文不改写，处理记录保留在报告信息中，仍需人工复核。']
              if result.get('pdf_text_adjustments') else []),
            *([str(result['income_reconciliation']['note'])]
              if result.get('income_reconciliation') and not result.get('extraction_note') else []),
            "跨期增速使用同一份年报中的上年同期/上年末比较栏，可能包含追溯调整。",
            "比较基期为零或负数时不展示百分比变化，保留两期金额供比较。",
            "比例仅在分母为正且金额可用时计算；净利润不大于零时不展示现金利润比，避免负数相除被误读为现金转化良好。",
            "银行、保险等特殊报表版式或扫描版PDF可能无法通过自动勾稽。",
            *( ["本报告使用银行双年度、带符号百万元模板；三表只核对指定汇总关系，容差为1百万元（报表舍入单位）。不计算普通公司比例，不等同于资本充足率、净息差或银行风险评估。"]
               if result.get('statement_template') == BANK_TEMPLATE else []),
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


def _format_raw_source_value(source: Mapping[str, object]) -> str:
    """Show the report value before unit conversion."""
    value = source.get("raw_current_value")
    if value is None:
        return "原值缺失"
    return f"{float(value):,.2f} {str(source.get('original_unit', '')).strip()}".strip()


def _format_pages(pages: Mapping[str, int] | None) -> str:
    """Format one inclusive PDF page range."""
    if not pages:
        return "待核验"
    start = int(pages["start"])
    end = int(pages["end"])
    return str(start) if start == end else f"{start}–{end}"


def income_reconciliation_rows(result: Mapping[str, object]) -> list[dict[str, str]]:
    """Display the saved checked relationships; never infer missing totals."""
    detail = result.get('income_reconciliation')
    if not isinstance(detail, Mapping):
        return []
    rows = []
    for check in detail.get('checks', []):
        periods = []
        for period in ('current', 'previous'):
            values = check.get(period) or {}
            difference = values.get('difference')
            periods.append(str(difference) if difference is not None else '证据不足')
        rows.append({'核对关系': str(check['label']), '本期差额': periods[0],
                     '比较期差额': periods[1], '检查结果': '通过' if check['passed'] else '待复核'})
    return rows


def operating_reconciliation_rows(result: Mapping[str, object]) -> list[dict[str, str]]:
    """Expose original two-period components only after a complete parse."""
    detail = result.get('income_reconciliation')
    operating = detail.get('operating_reconciliation') if isinstance(detail, Mapping) else None
    if not isinstance(operating, Mapping) or operating.get('status') not in ('passed', 'mismatch'):
        return []
    evidence = operating.get('evidence')
    if not isinstance(evidence, Mapping):
        return []
    rows = []
    for key, item in evidence.items():
        if not isinstance(item, Mapping):
            return []
        values = item.get('values')
        coefficient = item.get('coefficient')
        if (not isinstance(values, list) or len(values) != 2
                or type(coefficient) is not int or coefficient not in (-1, 0, 1)):
            return []
        operation = {-1: '减去原值', 1: '加上原值', 0: '已含在上级科目'}[coefficient]
        if key in ('operating_profit', 'profit_before_tax'):
            operation = '核对小计'
        rows.append({'原文科目': str(item.get('label', key)), '计算方式': operation,
                     '本期原值': str(values[0]), '比较期原值': str(values[1]),
                     'PDF页码': _format_pages(item.get('pages'))})
    return rows


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
    def source_for_report(item: Mapping[str, object]) -> Mapping[str, object]:
        raw_source = item.get("source")
        if isinstance(raw_source, Mapping):
            return raw_source
        # A browser may still hold a v1.0 snapshot after deployment.  Keep it
        # readable, but never pretend that the old snapshot retained an
        # annual-report original value, accounting basis or excerpt.
        return {
            "raw_current_value": None,
            "original_unit": "",
            "accounting_basis": "旧快照未保存原始口径，需重新生成并人工复核",
            "excerpt": "",
        }

    metric_rows = "".join(
        "<tr>"
        f"<td>{escape(item['label'])}</td>"
        f"<td>{escape(_format_raw_source_value(source_for_report(item)))}</td>"
        f"<td>{escape(_format_amount(item['current_yuan']))}</td>"
        f"<td>{escape(_format_amount(item['previous_yuan']))}</td>"
        f"<td>{escape(item.get('change_rate_note', '') or _format_percent(item['change_rate']))}</td>"
        f"<td>{escape(str(source_for_report(item)['accounting_basis']))}<br>"
        f"{escape(item['statement'])} 第"
        f"{escape(_format_pages(item['pages']))}页</td>"
        f"<td>{escape(str(source_for_report(item)['excerpt']) or '旧快照未保存原文摘录')}</td>"
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
    income_detail = snapshot.get('income_reconciliation')
    income_html = ''
    display_status = snapshot['status_label']
    if income_detail:
        check_rows = income_reconciliation_rows(snapshot)
        income_html = (
            '<h2>利润表金额关系复核</h2><p>' + escape(str(income_detail['note'])) + '</p>'
            + '<p>' + escape(' '.join(str(income_detail.get(key, '')) for key in ('tax_presentation', 'rounding_note'))) + '</p>'
            + '<p>差额按报表原单位展示：' + escape(str(income_detail.get('unit') or '待核验'))
            + '｜PDF第' + escape(_format_pages(income_detail.get('pages'))) + '页</p>'
            + '<table><thead><tr><th>核对关系</th><th>本期差额</th><th>比较期差额</th><th>检查结果</th></tr></thead><tbody>'
            + ''.join('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in row.values()) + '</tr>' for row in check_rows)
            + '</tbody></table>'
        )
        components = operating_reconciliation_rows(snapshot)
        if components:
            income_html += ('<h3>营业收入至税前利润的原文分项</h3>'
                '<p>按上方报表原单位展示。减项保留原文正负号；利息等明细已含在上级科目，不重复加总。</p>'
                '<table><thead><tr><th>原文科目</th><th>计算方式</th><th>本期原值</th><th>比较期原值</th><th>PDF页码</th></tr></thead><tbody>'
                + ''.join('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in row.values()) + '</tr>' for row in components)
                + '</tbody></table>')
    elif report.get('statement_template', 'general') == 'general':
        income_html = '<p>此快照未保存利润表金额关系复核明细；重新生成后可查看。</p>'
        display_status = '旧版候选快照；利润表金额关系需重新生成核对。'
    statement_detail = snapshot.get('statement_reconciliation')
    if isinstance(statement_detail, Mapping):
        extra_checks = [check for section in ('balance', 'cash') for check in statement_detail.get(section, [])]
        check_rows = income_reconciliation_rows({'income_reconciliation': {'checks': extra_checks}})
        if check_rows:
            income_html += ('<h2>资产负债与现金流金额关系</h2><p>按原报表单位逐项展示两期差额；核对范围见各条关系和利润表说明。仍需人工核验。</p>'
                + '<table><thead><tr><th>核对关系</th><th>本期差额</th><th>比较期差额</th><th>检查结果</th></tr></thead><tbody>'
                + ''.join('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in row.values()) + '</tr>' for row in check_rows)
                + '</tbody></table>')
    derivation_html = ''
    adjustments = report.get('text_adjustments', [])
    if isinstance(adjustments, list) and adjustments:
        derivation_html = '<h2>负号换行处理依据</h2><p>仅连接同一表格单元格内的负号与金额；原PDF和原始文字没有修改，不代表人工复核。</p>'
        for item in adjustments[:8]:
            if not isinstance(item, Mapping):
                continue
            derivation_html += ('<p>PDF第' + escape(str(item.get('page_number', '待核对'))) + '页｜'
                + escape(str(item.get('label', ''))) + '｜' + escape(str(item.get('column_year', ''))) + '年列</p>'
                + '<p>原始文字：</p><pre>' + escape(str(item.get('original_span', ''))[:1000]) + '</pre>'
                + '<p>程序读取：</p><pre>' + escape(str(item.get('replacement_span', ''))[:1000]) + '</pre>'
                + '<p>' + escape(str(item.get('reason', ''))[:1000]) + '</p>')
    recoveries = report.get('cash_flow_layout_recoveries', [])
    if isinstance(recoveries, list) and recoveries:
        derivation_html += ('<h2>现金流换行与附注读取依据</h2><p>'
            '按完整科目、附注列和两期金额识别换行；保留原始文字与页码，没有改写原PDF或补入缺失金额。</p>')
        for item in recoveries[:8]:
            if not isinstance(item, Mapping) or not isinstance(item.get('source_spans'), list):
                continue
            derivation_html += '<h3>' + escape(str(item.get('label', ''))) + '</h3>'
            for span in item.get('source_spans', []):
                if not isinstance(span, Mapping):
                    continue
                derivation_html += ('<p>PDF第' + escape(str(span.get('page_number', ''))) + '页</p><pre>'
                    + escape(str(span.get('original_text', ''))[:2000]) + '</pre>')
    for item in report.get('income_layout_recoveries', [])[:8]:
        if not isinstance(item, Mapping) or not isinstance(item.get('source_segments'), list):
            continue
        derivation_html += ('<h2>归母利润跨页读取依据</h2><p>'
            + escape(str(item.get('note', ''))) + '</p>')
        for segment in item['source_segments']:
            if isinstance(segment, Mapping):
                derivation_html += ('<p>PDF第' + escape(str(segment.get('page_number', ''))) + '页原始文字</p><pre>'
                    + escape(str(segment.get('text', ''))[:2000]) + '</pre>')
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
<p><small>FANGZHENG AI · A股按需财务快照 Agent</small></p>
<h1>{escape(company['name'])}｜{escape(company['canonical_code'])}</h1>
<p class="notice"><strong>{escape(display_status)}</strong><br>
自动提取候选，未经人工复核，不构成投资建议。</p>
<h2>来源报告</h2>
<p>{escape(str(report['title']))}<br>
报告期：{escape(str(report['report_year']))}｜公告日：
{escape(str(report['published_date']))}｜{safe_source_link}</p>
<p>{escape(snapshot['unit_note'])}</p>
<h2>核心财务快照</h2>
<table><thead><tr><th>指标</th><th>年报原值/原单位</th><th>本期换算值</th>
<th>上期比较栏</th><th>变化</th><th>口径/证据页</th><th>对应原文摘录</th>
</tr></thead><tbody>{metric_rows}</tbody></table>
<h2>确定性计算</h2><ul>{ratio_items}</ul>
{income_html}
{derivation_html}
<h2>使用边界</h2><ul>{limitation_items}</ul>
<p><small>生成时间（UTC）：{escape(snapshot['generated_at'])}<br>
证据文件 SHA-256：{escape(snapshot['source_fingerprint_sha256'])}</small></p>
</body></html>"""
