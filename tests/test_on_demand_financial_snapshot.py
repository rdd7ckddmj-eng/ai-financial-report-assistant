from datetime import datetime, timezone

import pytest

from src.on_demand_financial_snapshot import (
    build_financial_snapshot_report_html,
    build_on_demand_financial_snapshot,
)


def _company(*, name: str = "测试公司") -> dict[str, str]:
    return {
        "code": "600000",
        "name": name,
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600000.SH",
    }


def _candidate_result(
    *,
    status: str = "ready_for_human_review",
    unit: str = "万元",
    previous_revenue: float = 900.0,
) -> dict[str, object]:
    return {
        "report_year": 2025,
        "published_date": "2026-04-20",
        "title": "测试公司2025年年度报告",
        "source_url": "https://static.cninfo.com.cn/example.pdf",
        "evidence_fingerprint_sha256": "a" * 64,
        "page_count": 200,
        "status": status,
        "statement_checks": {
            "income_statement_reconciled": status
            == "ready_for_human_review",
            "balance_sheet_reconciled": status
            == "ready_for_human_review",
            "cash_flow_statement_reconciled": status
            == "ready_for_human_review",
        },
        "unit_check": {
            "passed": True,
            "units": [unit, unit, unit],
            "note": "三张报表金额单位一致。",
        },
        "statement_pages": {
            "income_statement": {"start": 100, "end": 101},
            "balance_sheet": {"start": 98, "end": 99},
            "cash_flow_statement": {"start": 102, "end": 103},
        },
        "values": {
            "current_revenue": 1000.0,
            "previous_revenue": previous_revenue,
            "current_net_profit": 100.0,
            "previous_net_profit": 80.0,
            "current_operating_cash_flow": 125.0,
            "previous_operating_cash_flow": 70.0,
            "current_total_assets": 2000.0,
            "previous_total_assets": 1800.0,
            "current_total_liabilities": 800.0,
            "previous_total_liabilities": 750.0,
        },
    }


def test_ready_snapshot_normalises_values_and_calculates_ratios() -> None:
    snapshot = build_on_demand_financial_snapshot(
        _company(),
        _candidate_result(),  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )

    assert snapshot["status"] == "ready_for_human_review"
    assert snapshot["unit"] == "万元"
    assert snapshot["metrics"][0]["current_yuan"] == 10_000_000
    assert snapshot["metrics"][0]["change_rate"] == pytest.approx(1 / 9)
    assert snapshot["ratios"]["net_profit_margin"] == pytest.approx(0.1)
    assert snapshot["ratios"]["operating_cash_conversion"] == 1.25
    assert snapshot["ratios"]["liabilities_to_assets"] == 0.4
    assert snapshot["metrics"][0]["pages"] == {"start": 100, "end": 101}


def test_failed_statement_check_does_not_publish_standardised_amounts() -> None:
    snapshot = build_on_demand_financial_snapshot(
        _company(),
        _candidate_result(status="needs_review"),  # type: ignore[arg-type]
    )

    assert snapshot["status"] == "needs_review"
    assert snapshot["unit"] is None
    assert all(item["current_yuan"] is None for item in snapshot["metrics"])
    assert all(value is None for value in snapshot["ratios"].values())


def test_inconsistent_ready_flag_cannot_bypass_unit_check() -> None:
    result = _candidate_result()
    result["unit_check"]["passed"] = False  # type: ignore[index]

    snapshot = build_on_demand_financial_snapshot(
        _company(),
        result,  # type: ignore[arg-type]
    )

    assert snapshot["status"] == "needs_review"
    assert all(item["current_yuan"] is None for item in snapshot["metrics"])


def test_zero_comparison_denominator_stays_explicitly_unavailable() -> None:
    snapshot = build_on_demand_financial_snapshot(
        _company(),
        _candidate_result(previous_revenue=0.0),  # type: ignore[arg-type]
    )

    assert snapshot["metrics"][0]["change_rate"] is None


def test_snapshot_rejects_untrusted_report_source() -> None:
    result = _candidate_result()
    result["source_url"] = "https://example.com/report.pdf"

    with pytest.raises(ValueError, match="受信任"):
        build_on_demand_financial_snapshot(
            _company(),
            result,  # type: ignore[arg-type]
        )


def test_html_report_escapes_external_text_and_preserves_provenance() -> None:
    result = _candidate_result()
    result["title"] = "<script>alert('report')</script>"
    snapshot = build_on_demand_financial_snapshot(
        _company(name="<img src=x onerror=alert(1)>"),
        result,  # type: ignore[arg-type]
        generated_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )

    html = build_financial_snapshot_report_html(snapshot)

    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "https://static.cninfo.com.cn/example.pdf" in html
    assert "自动提取候选，未经人工复核" in html
    assert "第100–101页" in html
