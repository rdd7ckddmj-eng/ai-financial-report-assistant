from datetime import date
from pathlib import Path

import pytest

from src.financial_history import (
    FINANCIAL_HISTORY_CATALOG_PATH,
    audit_financial_history_catalog,
    load_financial_history_catalog,
    load_moutai_financial_history,
    load_verified_financial_history,
    select_financial_history_as_of,
    verified_financial_history_codes,
)


def test_standardised_catalog_accepts_all_verified_companies() -> None:
    cases = load_financial_history_catalog()
    audit = audit_financial_history_catalog()

    assert [case["company_code"] for case in cases] == [
        "600519",
        "000858",
        "000568",
        "300750",
        "002594",
        "000333",
    ]
    assert [case["canonical_code"] for case in cases] == [
        "600519.SH",
        "000858.SZ",
        "000568.SZ",
        "300750.SZ",
        "002594.SZ",
        "000333.SZ",
    ]
    assert audit == {
        "company_count": 6,
        "financial_period_count": 21,
        "publication_vintage_count": 23,
        "all_checks_passed": True,
        "cases": cases,
    }


def test_catalog_rejects_a_declared_year_range_that_data_does_not_cover(
    tmp_path: Path,
) -> None:
    history_name = "catl_copy.csv"
    (tmp_path / history_name).write_text(
        (
            FINANCIAL_HISTORY_CATALOG_PATH.parent
            / "catl_financial_history.csv"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "company_code,company_name,exchange,exchange_name,canonical_code,"
        "data_file,coverage_start_year,coverage_end_year,verified_periods,"
        "reviewed_on,status\n"
        "300750,宁德时代,SZ,深圳证券交易所,300750.SZ,catl_copy.csv,"
        "2022,2025,4,2026-07-31,verified\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="财务年度与接入目录不一致"):
        load_financial_history_catalog(catalog)


def test_catalog_rejects_a_data_file_outside_the_verified_directory(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "company_code,company_name,exchange,exchange_name,canonical_code,"
        "data_file,coverage_start_year,coverage_end_year,verified_periods,"
        "reviewed_on,status\n"
        "300750,宁德时代,SZ,深圳证券交易所,300750.SZ,../outside.csv,"
        "2022,2024,3,2026-07-31,verified\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="同目录下"):
        load_financial_history_catalog(catalog)


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

    assert verified_financial_history_codes() == (
        "600519",
        "000858",
        "000568",
        "300750",
        "002594",
        "000333",
    )
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


def test_wuliangye_history_preserves_restatement_and_2025_disclosure() -> None:
    records = load_verified_financial_history("000858")

    before_restatement = select_financial_history_as_of(
        records,
        "2024-04-28",
    )
    complete = select_financial_history_as_of(records, "2026-04-30")

    assert [point["period_year"] for point in complete["points"]] == [
        2022,
        2023,
        2024,
        2025,
    ]
    assert before_restatement["points"][0]["accounting_basis"] == "original"
    assert complete["points"][0]["accounting_basis"] == "restated"
    assert complete["restatement_count"] == 1
    latest = complete["points"][-1]
    assert latest["revenue"] == pytest.approx(40_528_509_770.23)
    assert latest["net_profit"] == pytest.approx(8_954_257_202.51)
    assert latest["operating_cash_flow"] == pytest.approx(
        29_706_259_919.13
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        67_803_587_170.33 / 189_984_270_815.47
    )
    assert "收入确认核算" in latest["notes"]
    assert latest["source_url"].startswith("https://disc.static.szse.cn/")


def test_luzhou_laojiao_history_has_four_unrestated_official_years() -> None:
    records = load_verified_financial_history("000568")

    assert [record["period_year"] for record in records] == [
        2022,
        2023,
        2024,
        2025,
    ]
    assert [record["summary_page"] for record in records] == [7, 7, 8, 7]
    assert [record["balance_sheet_page"] for record in records] == [
        85,
        84,
        88,
        76,
    ]
    assert all(record["company_name"] == "泸州老窖" for record in records)
    assert all(record["accounting_basis"] == "reported" for record in records)
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(
        record["source_url"].startswith(
            "https://static.cninfo.com.cn/finalpage/"
        )
        for record in records
    )

    before_2025_report = select_financial_history_as_of(
        records,
        "2026-04-28",
    )
    complete = select_financial_history_as_of(records, "2026-04-29")

    assert [
        point["period_year"] for point in before_2025_report["points"]
    ] == [2022, 2023, 2024]
    assert complete["restatement_count"] == 0
    latest = complete["points"][-1]
    assert latest["revenue"] == pytest.approx(25_731_010_647.32)
    assert latest["net_profit"] == pytest.approx(10_830_713_936.14)
    assert latest["operating_cash_flow"] == pytest.approx(
        7_123_218_677.88
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        14_900_912_470.81 / 64_794_994_851.27
    )


def test_verified_byd_history_has_three_page_linked_years() -> None:
    records = load_verified_financial_history("002594")

    assert [record["period_year"] for record in records] == [
        2022,
        2023,
        2024,
    ]
    assert [record["summary_page"] for record in records] == [7, 10, 11]
    assert [record["balance_sheet_page"] for record in records] == [
        127,
        138,
        143,
    ]
    assert all(record["company_name"] == "比亚迪" for record in records)
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(
        record["source_url"].startswith(
            "https://static.cninfo.com.cn/finalpage/"
        )
        for record in records
    )


def test_byd_history_preserves_cutoffs_and_calculates_latest_ratios() -> None:
    records = load_verified_financial_history("002594")

    before_2023_report = select_financial_history_as_of(
        records,
        "2024-03-26",
    )
    complete = select_financial_history_as_of(records, "2025-03-25")

    assert [
        point["period_year"] for point in before_2023_report["points"]
    ] == [2022]
    assert complete["future_vintage_count"] == 0
    latest = complete["points"][-1]
    assert latest["revenue"] == pytest.approx(777_102_455_000)
    assert latest["revenue_growth"] == pytest.approx(
        777_102_455_000 / 602_315_354_000 - 1
    )
    assert latest["net_profit_growth"] == pytest.approx(
        40_254_346_000 / 30_040_811_000 - 1
    )
    assert latest["operating_cash_flow_growth"] == pytest.approx(
        133_453_873_000 / 169_725_025_000 - 1
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        584_667_646_000 / 783_355_855_000
    )


def test_verified_midea_history_has_three_page_linked_years() -> None:
    records = load_verified_financial_history("000333")

    assert [record["period_year"] for record in records] == [
        2023,
        2024,
        2025,
    ]
    assert [record["summary_page"] for record in records] == [9, 9, 8]
    assert [record["balance_sheet_page"] for record in records] == [
        159,
        156,
        132,
    ]
    assert all(record["company_name"] == "美的集团" for record in records)
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(record["accounting_basis"] == "reported" for record in records)
    assert all(
        record["source_url"].startswith(
            "https://static.cninfo.com.cn/finalpage/"
        )
        for record in records
    )


def test_midea_history_preserves_cutoffs_and_calculates_latest_ratios() -> None:
    records = load_verified_financial_history("000333")

    before_2024_report = select_financial_history_as_of(
        records,
        "2025-03-28",
    )
    complete = select_financial_history_as_of(records, "2026-03-31")

    assert [
        point["period_year"] for point in before_2024_report["points"]
    ] == [2023]
    assert complete["future_vintage_count"] == 0
    assert complete["restatement_count"] == 0
    latest = complete["points"][-1]
    assert latest["revenue"] == pytest.approx(456_451_731_000)
    assert latest["revenue_growth"] == pytest.approx(
        456_451_731_000 / 407_149_600_000 - 1
    )
    assert latest["net_profit_growth"] == pytest.approx(
        43_945_411_000 / 38_537_237_000 - 1
    )
    assert latest["operating_cash_flow_growth"] == pytest.approx(
        53_345_930_000 / 60_511_572_000 - 1
    )
    assert latest["liabilities_to_assets"] == pytest.approx(
        372_367_543_000 / 608_791_766_000
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
