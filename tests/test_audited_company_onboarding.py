import csv
from datetime import datetime, timezone
from io import StringIO

import pytest

from src.audited_company_onboarding import (
    build_candidate_report_result,
    build_financial_history_draft_rows,
    build_onboarding_package,
    pending_annual_reports,
    rmb_unit_multiplier,
    select_recent_annual_reports,
    serialise_financial_history_draft,
    serialise_onboarding_package,
)
from src.china_stock import build_company_identity


def _report(year: int) -> dict[str, object]:
    return {
        "report_year": year,
        "published_date": f"{year + 1}-04-20",
        "title": f"测试公司{year}年年度报告",
        "url": f"https://static.cninfo.com.cn/{year}.pdf",
    }


def _result(
    year: int,
    *,
    current_base: float,
    previous_base: float,
) -> dict[str, object]:
    report = _report(year)
    return {
        "report_year": year,
        "published_date": report["published_date"],
        "title": report["title"],
        "source_url": report["url"],
        "evidence_fingerprint_sha256": "a" * 64,
        "page_count": 200,
        "status": "ready_for_human_review",
        "statement_checks": {
            "income_statement_reconciled": True,
            "balance_sheet_reconciled": True,
            "cash_flow_statement_reconciled": True,
        },
        "unit_check": {
            "passed": True,
            "units": ["人民币元", "人民币元", "人民币元"],
            "note": "三张报表金额单位一致。",
        },
        "statement_pages": {
            "income_statement": {"start": 100, "end": 101},
            "balance_sheet": {"start": 98, "end": 99},
            "cash_flow_statement": {"start": 102, "end": 103},
        },
        "values": {
            "current_revenue": current_base,
            "previous_revenue": previous_base,
            "current_net_profit": current_base / 10,
            "previous_net_profit": previous_base / 10,
            "current_operating_cash_flow": current_base / 8,
            "previous_operating_cash_flow": previous_base / 8,
            "current_total_assets": current_base * 2,
            "previous_total_assets": previous_base * 2,
            "current_total_liabilities": current_base,
            "previous_total_liabilities": previous_base,
        },
    }


def test_recent_report_selection_uses_three_distinct_chinese_reports() -> None:
    announcements = [
        {
            "title": "测试公司2025年年度报告（英文版）",
            "date": "2026-04-30",
            "url": "https://static.cninfo.com.cn/2025-en.pdf",
        },
        {
            "title": "测试公司2025年年度报告",
            "date": "2026-04-20",
            "url": "https://static.cninfo.com.cn/2025-zh.pdf",
        },
        {
            "title": "测试公司2025年年度报告摘要",
            "date": "2026-04-20",
            "url": "https://static.cninfo.com.cn/2025-summary.pdf",
        },
        {
            "title": "测试公司2024年年度报告",
            "date": "2025-04-20",
            "url": "https://static.cninfo.com.cn/2024.pdf",
        },
        {
            "title": "测试公司2023年年度报告",
            "date": "2024-04-20",
            "url": "https://static.cninfo.com.cn/2023.pdf",
        },
        {
            "title": "测试公司2022年年度报告",
            "date": "2023-04-20",
            "url": "https://static.cninfo.com.cn/2022.pdf",
        },
    ]

    reports = select_recent_annual_reports(announcements)

    assert [item["report_year"] for item in reports] == [2025, 2024, 2023]
    assert reports[0]["url"].endswith("2025-zh.pdf")


def test_pending_reports_skip_completed_years_and_keep_review_order() -> None:
    reports = [_report(2025), _report(2024), _report(2023)]
    results = {
        str(reports[1]["url"]): _result(
            2024,
            current_base=100.0,
            previous_base=90.0,
        ),
    }

    pending = pending_annual_reports(
        reports,  # type: ignore[arg-type]
        results,  # type: ignore[arg-type]
    )

    assert [report["report_year"] for report in pending] == [2025, 2023]


def test_candidate_report_requires_three_statements_and_matching_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    income = {
        "current_revenue": 100.0,
        "previous_revenue": 90.0,
        "current_net_profit": 10.0,
        "previous_net_profit": 9.0,
        "unit": "人民币万元",
        "page_number": 101,
        "end_page_number": 102,
    }
    balance = {
        "current_total_assets": 200.0,
        "previous_total_assets": 180.0,
        "current_total_liabilities": 80.0,
        "previous_total_liabilities": 70.0,
        "unit": "人民币万元",
        "page_number": 99,
        "end_page_number": 100,
    }
    cash_flow = {
        "current_operating_cash_flow": 12.0,
        "previous_operating_cash_flow": 11.0,
        "unit": "人民币万元",
        "page_number": 103,
        "end_page_number": 104,
    }
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_income_statement_figures",
        lambda pages: income,
    )
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_balance_sheet_figures",
        lambda pages: balance,
    )
    monkeypatch.setattr(
        "src.audited_company_onboarding.find_cash_flow_figures",
        lambda pages: cash_flow,
    )

    result = build_candidate_report_result(
        build_company_identity("000333", "美的集团"),
        _report(2025),
        b"%PDF-test",
        [{"page_number": 1, "text": "年度报告"}],
    )

    assert result["status"] == "ready_for_human_review"
    assert result["unit_check"]["passed"] is True
    assert result["values"]["current_revenue"] == 100.0
    assert result["statement_pages"]["cash_flow_statement"] == {
        "start": 103,
        "end": 104,
    }
    assert len(result["evidence_fingerprint_sha256"]) == 64


def test_package_stops_at_human_gate_and_surfaces_restatement_clue() -> None:
    reports = [_report(2025), _report(2024), _report(2023)]
    results = {
        str(reports[0]["url"]): _result(
            2025,
            current_base=120.0,
            previous_base=110.0,
        ),
        str(reports[1]["url"]): _result(
            2024,
            current_base=100.0,
            previous_base=90.0,
        ),
        str(reports[2]["url"]): _result(
            2023,
            current_base=90.0,
            previous_base=80.0,
        ),
    }

    package = build_onboarding_package(
        build_company_identity("000333", "美的集团"),
        reports,  # type: ignore[arg-type]
        results,  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )

    assert package["status"] == "ready_for_human_review"
    assert package["approval_gate"]["catalogue_written"] is False
    assert package["approval_gate"]["human_approval_required"] is True
    assert package["restatement_clue_count"] == 5
    assert "candidate_in_progress" not in serialise_onboarding_package(package)


def test_incomplete_package_is_not_presented_as_verified() -> None:
    reports = [_report(2025), _report(2024), _report(2023)]
    package = build_onboarding_package(
        build_company_identity("000333", "美的集团"),
        reports,  # type: ignore[arg-type]
        {},
        generated_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )

    assert package["status"] == "candidate_in_progress"
    assert package["processing"]["processed_report_count"] == 0


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("人民币元", 1.0),
        ("人民币千元", 1_000.0),
        ("万元", 10_000.0),
        ("人民币百万元", 1_000_000.0),
    ],
)
def test_rmb_unit_multiplier_supports_a_share_report_units(
    unit: str,
    expected: float,
) -> None:
    assert rmb_unit_multiplier(unit) == expected


def test_rmb_unit_multiplier_rejects_unsupported_currency() -> None:
    with pytest.raises(ValueError, match="不支持自动换算"):
        rmb_unit_multiplier("美元")


def test_financial_history_draft_converts_units_but_stays_candidate() -> None:
    reports = [_report(2025), _report(2024), _report(2023)]
    results = {
        str(report["url"]): _result(
            int(report["report_year"]),
            current_base=float(index * 100),
            previous_base=float((index - 1) * 100),
        )
        for index, report in enumerate(reversed(reports), start=1)
    }
    for result in results.values():
        result["unit_check"]["units"] = [
            "人民币千元",
            "人民币千元",
            "人民币千元",
        ]
    package = build_onboarding_package(
        build_company_identity("000333", "美的集团"),
        reports,  # type: ignore[arg-type]
        results,  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    rows = build_financial_history_draft_rows(package)
    serialised = serialise_financial_history_draft(package)
    csv_rows = list(csv.DictReader(StringIO(serialised)))

    assert [row["period_year"] for row in rows] == [2023, 2024, 2025]
    assert rows[0]["revenue"] == 100_000.0
    assert rows[0]["verification_status"] == "candidate"
    assert rows[0]["source_url"] == (
        "https://static.cninfo.com.cn/2023.pdf"
    )
    assert csv_rows[0]["verification_status"] == "candidate"
    assert "人民币千元并换算为人民币元" in csv_rows[0]["notes"]


def test_financial_history_draft_rejects_incomplete_package() -> None:
    reports = [_report(2025), _report(2024), _report(2023)]
    package = build_onboarding_package(
        build_company_identity("000333", "美的集团"),
        reports,  # type: ignore[arg-type]
        {},
        generated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="自动检查完成"):
        build_financial_history_draft_rows(package)
