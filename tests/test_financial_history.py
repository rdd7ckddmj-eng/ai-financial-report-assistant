from datetime import date
from pathlib import Path

import pytest

from src.financial_history import (
    load_moutai_financial_history,
    select_financial_history_as_of,
)


def test_verified_moutai_history_has_four_years_and_official_sources() -> None:
    records = load_moutai_financial_history()

    assert {record["period_year"] for record in records} == {
        2022,
        2023,
        2024,
        2025,
    }
    assert all(record["company_code"] == "600519" for record in records)
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(
        record["verification_status"] == "verified"
        for record in records
    )
    assert all(
        record["total_liabilities"] < record["total_assets"]
        for record in records
    )


def test_as_of_filter_does_not_reveal_unpublished_financial_years() -> None:
    result = select_financial_history_as_of(
        load_moutai_financial_history(),
        "2025-04-02",
    )

    assert [point["period_year"] for point in result["points"]] == [
        2022,
        2023,
    ]
    assert result["future_vintage_count"] == 2


def test_restatement_replaces_original_only_after_publication() -> None:
    records = load_moutai_financial_history()

    before = select_financial_history_as_of(records, "2024-04-02")
    after = select_financial_history_as_of(records, "2024-04-03")

    assert before["points"][0]["accounting_basis"] == "original"
    assert before["points"][0]["total_assets"] == pytest.approx(
        254_364_804_995.25
    )
    assert after["points"][0]["accounting_basis"] == "restated"
    assert after["points"][0]["total_assets"] == pytest.approx(
        254_500_826_096.02
    )
    assert after["restatement_count"] == 1


def test_growth_and_ratios_are_calculated_in_python() -> None:
    result = select_financial_history_as_of(
        load_moutai_financial_history(),
        date(2026, 7, 30),
    )
    latest = result["points"][-1]

    assert latest["period_year"] == 2025
    assert latest["revenue_growth"] == pytest.approx(-0.0121, abs=0.0001)
    assert latest["net_profit_growth"] == pytest.approx(
        -0.0453,
        abs=0.0001,
    )
    assert latest["operating_cash_flow_growth"] == pytest.approx(
        -0.3346,
        abs=0.0001,
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        49_875_590_112.37 / 303_834_844_021.44
    )


def test_history_loader_rejects_untrusted_sources(tmp_path: Path) -> None:
    bad_data = tmp_path / "financial_history.csv"
    bad_data.write_text(
        "company_code,company_name,period_year,report_year,published_date,"
        "report_title,source_url,revenue,net_profit,operating_cash_flow,"
        "total_assets,total_liabilities,summary_page,balance_sheet_page,"
        "evidence_grade,verification_status,accounting_basis,notes\n"
        "600519,贵州茅台,2025,2025,2026-04-17,测试,"
        "https://example.com/report.pdf,10,5,6,20,8,5,58,"
        "A,verified,reported,测试\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="允许的官方 HTTPS 来源"):
        load_moutai_financial_history(bad_data)
