from datetime import date
from pathlib import Path

import pytest

from src.financial_history import (
    load_moutai_financial_history,
    load_verified_financial_history,
    select_financial_history_as_of,
    verified_financial_history_codes,
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


def test_verified_catl_history_has_three_audited_years() -> None:
    records = load_verified_financial_history("300750")

    assert verified_financial_history_codes() == ("600519", "300750")
    assert [record["period_year"] for record in records] == [
        2022,
        2023,
        2024,
    ]
    assert all(record["company_name"] == "宁德时代" for record in records)
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(
        record["source_url"].startswith(
            "https://static.cninfo.com.cn/finalpage/"
        )
        for record in records
    )


def test_catl_history_preserves_publication_cutoffs_and_python_ratios() -> None:
    records = load_verified_financial_history("300750")

    before_2023_report = select_financial_history_as_of(
        records,
        "2024-03-15",
    )
    complete = select_financial_history_as_of(records, "2025-03-15")

    assert [
        point["period_year"] for point in before_2023_report["points"]
    ] == [2022]
    assert complete["future_vintage_count"] == 0
    latest = complete["points"][-1]
    assert latest["revenue"] == pytest.approx(362_012_554_000)
    assert latest["revenue_growth"] == pytest.approx(
        362_012_554_000 / 400_917_044_900 - 1
    )
    assert latest["net_profit_growth"] == pytest.approx(
        50_744_682_000 / 44_121_248_300 - 1
    )
    assert latest["operating_cash_flow_growth"] == pytest.approx(
        96_990_345_000 / 92_826_124_400 - 1
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        513_201_949_000 / 786_658_123_000
    )


def test_generic_loader_rejects_companies_without_verified_history() -> None:
    with pytest.raises(ValueError, match="尚未建立"):
        load_verified_financial_history("000001")


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
    assert before["points"][0]["liabilities_to_assets"] == pytest.approx(
        49_400_116_741.17 / 254_364_804_995.25
    )
    assert after["points"][0]["accounting_basis"] == "restated"
    assert after["points"][0]["total_assets"] == pytest.approx(
        254_500_826_096.02
    )
    assert after["points"][0]["liabilities_to_assets"] == pytest.approx(
        49_562_744_832.16 / 254_500_826_096.02
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
    assert latest["net_margin"] == pytest.approx(
        82_320_067_101.68 / 168_838_102_514.79
    )
    assert latest["net_margin_change"] == pytest.approx(
        (
            82_320_067_101.68 / 168_838_102_514.79
            - 86_228_146_421.62 / 170_899_152_276.34
        )
    )
    assert latest["cash_conversion"] == pytest.approx(
        61_522_204_989.35 / 82_320_067_101.68
    )
    assert latest["cash_conversion_change"] == pytest.approx(
        (
            61_522_204_989.35 / 82_320_067_101.68
            - 92_463_692_168.43 / 86_228_146_421.62
        )
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        49_875_590_112.37 / 303_834_844_021.44
    )
    assert latest["liabilities_to_assets_change"] == pytest.approx(
        (
            49_875_590_112.37 / 303_834_844_021.44
            - 56_933_264_798.10 / 298_944_579_918.70
        )
    )


def test_first_available_year_does_not_invent_ratio_changes() -> None:
    result = select_financial_history_as_of(
        load_moutai_financial_history(),
        "2023-03-31",
    )
    first = result["points"][0]

    assert first["period_year"] == 2022
    assert first["net_margin_change"] is None
    assert first["cash_conversion_change"] is None
    assert first["liabilities_to_assets_change"] is None


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
