"""Candidate-package workflow for expanding the audited company catalogue.

This module deliberately stops before writing to ``data/verified``.  It turns
official annual reports into a compact, page-linked candidate package that a
human must review before the company is admitted to the audited catalogue.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import TypedDict

from src.balance_sheet_extractor import find_balance_sheet_figures
from src.cash_flow_extractor import find_cash_flow_figures
from src.china_stock import is_allowed_disclosure_url
from src.financial_statement_extractor import find_income_statement_figures


ONBOARDING_SCHEMA_VERSION = "1.0"
DEFAULT_REPORT_LIMIT = 3
ANNUAL_REPORT_EXCLUSIONS = re.compile(
    r"半年度报告|摘要|取消|问询|回复",
)
TRANSLATION_PATTERN = re.compile(
    r"英文(?:版|译本)?|English",
    re.IGNORECASE,
)
REPORT_YEAR_PATTERN = re.compile(r"((?:19|20)\d{2})年年度报告")


class AnnualReportCandidate(TypedDict):
    """One official complete annual report selected for candidate review."""

    report_year: int
    published_date: str
    title: str
    url: str


class CandidateReportResult(TypedDict):
    """Compact extraction result retained after the source PDF is released."""

    report_year: int
    published_date: str
    title: str
    source_url: str
    evidence_fingerprint_sha256: str
    page_count: int
    status: str
    statement_checks: dict[str, bool]
    unit_check: dict[str, object]
    statement_pages: dict[str, dict[str, int] | None]
    values: dict[str, float | None]


def _as_iso_date(value: object) -> str | None:
    """Normalise supported date values and reject unusable metadata."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _report_year(title: str) -> int | None:
    """Read the fiscal year explicitly stated in an annual-report title."""
    match = REPORT_YEAR_PATTERN.search(str(title))
    return int(match.group(1)) if match is not None else None


def select_recent_annual_reports(
    announcements: Iterable[Mapping[str, object]],
    *,
    limit: int = DEFAULT_REPORT_LIMIT,
) -> list[AnnualReportCandidate]:
    """Select recent distinct full reports, preferring Chinese editions.

    One report is retained for each explicit reporting year.  A later English
    translation never displaces the Chinese report for the same fiscal year.
    """
    if limit <= 0 or limit > 10:
        raise ValueError("候选年报数量必须在1到10之间。")

    by_year: dict[int, list[AnnualReportCandidate]] = {}
    for announcement in announcements:
        title = str(announcement.get("title", "")).strip()
        if (
            "年度报告" not in title
            or ANNUAL_REPORT_EXCLUSIONS.search(title) is not None
        ):
            continue
        report_year = _report_year(title)
        published_date = _as_iso_date(announcement.get("date"))
        url = str(announcement.get("url", "")).strip()
        if (
            report_year is None
            or published_date is None
            or not is_allowed_disclosure_url(url)
        ):
            continue
        by_year.setdefault(report_year, []).append(
            {
                "report_year": report_year,
                "published_date": published_date,
                "title": title,
                "url": url,
            }
        )

    selected: list[AnnualReportCandidate] = []
    for report_year in sorted(by_year, reverse=True)[:limit]:
        candidates = sorted(
            by_year[report_year],
            key=lambda item: item["published_date"],
            reverse=True,
        )
        chinese_candidates = [
            item
            for item in candidates
            if TRANSLATION_PATTERN.search(item["title"]) is None
        ]
        selected.append((chinese_candidates or candidates)[0])
    return selected


def pending_annual_reports(
    reports: Iterable[AnnualReportCandidate],
    results_by_url: Mapping[str, CandidateReportResult],
) -> list[AnnualReportCandidate]:
    """Return unprocessed reports in the original review order.

    Keeping this decision deterministic lets the interface resume an
    interrupted three-report task without downloading a completed PDF again.
    """
    return [
        report
        for report in reports
        if report["url"] not in results_by_url
    ]


def _page_range(
    figures: Mapping[str, object] | None,
) -> dict[str, int] | None:
    """Keep a small inclusive PDF page range for later human review."""
    if figures is None:
        return None
    start_page = int(figures["page_number"])
    return {
        "start": start_page,
        "end": int(figures.get("end_page_number", start_page)),
    }


def build_candidate_report_result(
    company: Mapping[str, object],
    report: Mapping[str, object],
    pdf_bytes: bytes,
    pages: Iterable[Mapping[str, object]],
) -> CandidateReportResult:
    """Extract five core metrics and preserve report/page provenance.

    The statement extractors already reject unreconciled statement layouts.
    This layer adds a cross-statement unit check and retains only the compact
    evidence needed for review, rather than keeping the entire PDF in memory.
    """
    required_identity = {"code", "name", "exchange", "canonical_code"}
    if not required_identity.issubset(company):
        raise ValueError("候选公司身份字段不完整。")
    source_url = str(report.get("url", "")).strip()
    title = str(report.get("title", "")).strip()
    report_year = int(report["report_year"])
    if not is_allowed_disclosure_url(source_url):
        raise ValueError("候选年报不是受信任的官方披露地址。")
    if _report_year(title) not in {None, report_year}:
        raise ValueError("候选年报标题与财务年度不一致。")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("候选文件不是有效PDF。")

    page_list = [
        (int(page["page_number"]), str(page.get("text", "")))
        for page in pages
    ]
    if not page_list:
        raise ValueError("候选年报没有可核验页面。")

    income = find_income_statement_figures(page_list)
    balance = find_balance_sheet_figures(page_list)
    cash_flow = find_cash_flow_figures(page_list)
    statement_checks = {
        "income_statement_reconciled": income is not None,
        "balance_sheet_reconciled": balance is not None,
        "cash_flow_statement_reconciled": cash_flow is not None,
    }
    statements = [
        figures
        for figures in (income, balance, cash_flow)
        if figures is not None
    ]
    units = [str(figures.get("unit", "")).strip() for figures in statements]
    all_units_present = len(units) == 3 and all(units)
    units_consistent = all_units_present and len(set(units)) == 1
    ready = all(statement_checks.values()) and units_consistent

    return {
        "report_year": report_year,
        "published_date": str(report["published_date"]),
        "title": title,
        "source_url": source_url,
        "evidence_fingerprint_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "page_count": len(page_list),
        "status": "ready_for_human_review" if ready else "needs_review",
        "statement_checks": statement_checks,
        "unit_check": {
            "passed": units_consistent,
            "units": units,
            "note": (
                "三张报表金额单位一致。"
                if units_consistent
                else "金额单位缺失或不一致，必须查看原文后再换算。"
            ),
        },
        "statement_pages": {
            "income_statement": _page_range(income),
            "balance_sheet": _page_range(balance),
            "cash_flow_statement": _page_range(cash_flow),
        },
        "values": {
            "current_revenue": (
                float(income["current_revenue"])
                if income is not None
                else None
            ),
            "previous_revenue": (
                float(income["previous_revenue"])
                if income is not None
                else None
            ),
            "current_net_profit": (
                float(income["current_net_profit"])
                if income is not None
                else None
            ),
            "previous_net_profit": (
                float(income["previous_net_profit"])
                if income is not None
                else None
            ),
            "current_operating_cash_flow": (
                float(cash_flow["current_operating_cash_flow"])
                if cash_flow is not None
                else None
            ),
            "previous_operating_cash_flow": (
                float(cash_flow["previous_operating_cash_flow"])
                if cash_flow is not None
                else None
            ),
            "current_total_assets": (
                float(balance["current_total_assets"])
                if balance is not None
                else None
            ),
            "previous_total_assets": (
                float(balance["previous_total_assets"])
                if balance is not None
                else None
            ),
            "current_total_liabilities": (
                float(balance["current_total_liabilities"])
                if balance is not None
                else None
            ),
            "previous_total_liabilities": (
                float(balance["previous_total_liabilities"])
                if balance is not None
                else None
            ),
        },
    }


def _years_are_continuous(reports: list[AnnualReportCandidate]) -> bool:
    """Require a descending sequence such as 2025, 2024, 2023."""
    years = [item["report_year"] for item in reports]
    return len(years) >= 2 and all(
        newer - older == 1
        for newer, older in zip(years, years[1:])
    )


def _cross_report_checks(
    reports: list[AnnualReportCandidate],
    results_by_url: Mapping[str, CandidateReportResult],
) -> list[dict[str, object]]:
    """Compare a later report's prior-year column with the earlier original.

    A difference is a restatement clue, not automatically an extraction error.
    """
    metric_pairs = (
        ("revenue", "previous_revenue", "current_revenue"),
        ("net_profit", "previous_net_profit", "current_net_profit"),
        (
            "operating_cash_flow",
            "previous_operating_cash_flow",
            "current_operating_cash_flow",
        ),
        ("total_assets", "previous_total_assets", "current_total_assets"),
        (
            "total_liabilities",
            "previous_total_liabilities",
            "current_total_liabilities",
        ),
    )
    comparisons: list[dict[str, object]] = []
    for newer_report, older_report in zip(
        reports,
        reports[1:],
    ):
        if newer_report["report_year"] - older_report["report_year"] != 1:
            continue
        newer = results_by_url.get(newer_report["url"])
        older = results_by_url.get(older_report["url"])
        if newer is None or older is None:
            continue
        newer_units = newer["unit_check"].get("units", [])
        older_units = older["unit_check"].get("units", [])
        comparable_units = (
            newer["unit_check"].get("passed") is True
            and older["unit_check"].get("passed") is True
            and newer_units == older_units
        )
        for label, newer_key, older_key in metric_pairs:
            later_report_value = newer["values"].get(newer_key)
            original_value = older["values"].get(older_key)
            comparable = (
                comparable_units
                and later_report_value is not None
                and original_value is not None
            )
            changed = (
                comparable
                and not math.isclose(
                    float(later_report_value),
                    float(original_value),
                    rel_tol=1e-9,
                    abs_tol=0.5,
                )
            )
            comparisons.append(
                {
                    "period_year": older_report["report_year"],
                    "metric": label,
                    "original_report_value": original_value,
                    "later_report_comparative_value": later_report_value,
                    "comparable": comparable,
                    "status": (
                        "changed_or_restated"
                        if changed
                        else "unchanged"
                        if comparable
                        else "not_comparable"
                    ),
                }
            )
    return comparisons


def build_onboarding_package(
    company: Mapping[str, object],
    reports: list[AnnualReportCandidate],
    results_by_url: Mapping[str, CandidateReportResult],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build a versioned candidate package without approving the company."""
    generated = generated_at or datetime.now(timezone.utc)
    processed_results = [
        results_by_url[report["url"]]
        for report in reports
        if report["url"] in results_by_url
    ]
    ready_count = sum(
        result["status"] == "ready_for_human_review"
        for result in processed_results
    )
    target_count = len(reports)
    continuous = _years_are_continuous(reports)
    if target_count < DEFAULT_REPORT_LIMIT:
        package_status = "insufficient_report_history"
    elif len(processed_results) < target_count:
        package_status = "candidate_in_progress"
    elif ready_count < target_count or not continuous:
        package_status = "human_review_required"
    else:
        package_status = "ready_for_human_review"

    cross_checks = _cross_report_checks(reports, results_by_url)
    return {
        "schema_version": ONBOARDING_SCHEMA_VERSION,
        "package_type": "audited_company_candidate",
        "generated_at": generated.isoformat(timespec="seconds"),
        "status": package_status,
        "company": {
            key: str(company.get(key, ""))
            for key in (
                "code",
                "name",
                "exchange",
                "exchange_name",
                "canonical_code",
            )
        },
        "discovery": {
            "target_report_count": DEFAULT_REPORT_LIMIT,
            "discovered_report_count": target_count,
            "years_continuous": continuous,
            "reports": reports,
        },
        "processing": {
            "processed_report_count": len(processed_results),
            "ready_for_human_review_count": ready_count,
            "results": processed_results,
        },
        "cross_report_checks": cross_checks,
        "restatement_clue_count": sum(
            item["status"] == "changed_or_restated"
            for item in cross_checks
        ),
        "approval_gate": {
            "catalogue_written": False,
            "human_approval_required": True,
            "required_actions": [
                "打开官方PDF复核三张报表页码和合并口径",
                "确认金额单位并按统一口径换算",
                "判断跨报告差异是否来自追溯调整",
                "复核连续年度后再写入受控数据目录",
            ],
        },
        "limitations": [
            "候选数据包不是审计意见或第三方认证。",
            "系统不使用AI猜测未识别数字。",
            "只有人工复核通过后，公司才能进入已核验目录。",
            "本流程不生成投资建议。",
        ],
    }


def serialise_onboarding_package(package: Mapping[str, object]) -> str:
    """Return stable, human-readable JSON for download and source control."""
    return json.dumps(
        package,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
