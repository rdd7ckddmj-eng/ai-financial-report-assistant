from copy import deepcopy
from datetime import date

import pytest

from src.baijiu_operating_quality import (
    build_baijiu_operating_quality,
    load_baijiu_operating_quality,
)
from src.company_industry import load_company_industry_catalog
from src.cross_company_comparison import build_cross_company_comparison
from src.financial_history import (
    load_financial_history_catalog,
    load_verified_financial_history,
    select_financial_history_as_of,
)


def _baijiu_comparison_rows(period_year: int = 2025):
    cases = load_financial_history_catalog()[:3]
    points_by_code = {
        case["company_code"]: select_financial_history_as_of(
            load_verified_financial_history(case["company_code"]),
            date.today(),
        )["points"]
        for case in cases
    }
    comparison = build_cross_company_comparison(
        cases,
        points_by_code,
        selected_year=period_year,
        industry_profiles=load_company_industry_catalog(),
    )
    return comparison["rows"]


def test_baijiu_operating_quality_source_has_three_years_for_each_company() -> None:
    records = load_baijiu_operating_quality()

    assert len(records) == 9
    assert {
        (record["company_code"], record["period_year"])
        for record in records
    } == {
        (company_code, period_year)
        for company_code in ("600519", "000858", "000568")
        for period_year in (2023, 2024, 2025)
    }
    assert all(record["evidence_grade"] == "A" for record in records)
    assert all(record["verification_status"] == "verified" for record in records)


def test_baijiu_operating_quality_calculates_traceable_ratios() -> None:
    result = build_baijiu_operating_quality(
        _baijiu_comparison_rows(),
        load_baijiu_operating_quality(),
    )

    assert result["period_year"] == 2025
    assert result["company_count"] == 3
    assert "不生成综合得分" in result["limitation"]

    moutai = next(
        row for row in result["rows"] if row["company_code"] == "600519"
    )
    assert moutai["gross_margin"] == pytest.approx(
        (168_838_102_514.79 - 14_892_277_570.91)
        / 168_838_102_514.79
    )
    assert moutai["inventory_to_assets"] == pytest.approx(
        61_427_421_796.18 / 303_834_844_021.44
    )
    assert moutai["inventory_growth"] == pytest.approx(
        61_427_421_796.18 / 54_343_285_157.47 - 1
    )
    assert moutai["contract_liabilities_to_revenue"] == pytest.approx(
        8_006_739_780.94 / 168_838_102_514.79
    )
    assert moutai["income_statement_page"] == 61
    assert moutai["inventory_page"] == 57
    assert moutai["contract_liabilities_page"] == 58

    wuliangye = next(
        row for row in result["rows"] if row["company_code"] == "000858"
    )
    assert wuliangye["gross_margin"] == pytest.approx(
        (40_528_509_770.23 - 9_101_956_953.59) / 40_528_509_770.23
    )
    assert wuliangye["contract_liabilities_growth"] == pytest.approx(
        13_459_591_156.56 / 11_689_880_975.04 - 1
    )
    assert wuliangye["cash_conversion"] == pytest.approx(
        29_706_259_919.13 / 8_954_257_202.51
    )


def test_baijiu_operating_quality_calculates_verified_history() -> None:
    records = load_baijiu_operating_quality()
    result_2023 = build_baijiu_operating_quality(
        _baijiu_comparison_rows(2023),
        records,
    )
    result_2024 = build_baijiu_operating_quality(
        _baijiu_comparison_rows(2024),
        records,
    )

    moutai_2023 = next(
        row for row in result_2023["rows"] if row["company_code"] == "600519"
    )
    assert result_2023["period_year"] == 2023
    assert moutai_2023["gross_margin"] == pytest.approx(
        (147_693_604_994.14 - 11_867_273_851.78)
        / 147_693_604_994.14
    )
    assert moutai_2023["inventory_growth"] == pytest.approx(
        46_435_185_061.53 / 38_824_374_236.24 - 1
    )
    assert moutai_2023["income_statement_page"] == 63
    assert moutai_2023["inventory_page"] == 59
    assert moutai_2023["contract_liabilities_page"] == 60

    luzhou_2024 = next(
        row for row in result_2024["rows"] if row["company_code"] == "000568"
    )
    assert result_2024["period_year"] == 2024
    assert luzhou_2024["inventory_to_assets"] == pytest.approx(
        13_392_794_475.96 / 68_334_595_564.58
    )
    assert luzhou_2024["contract_liabilities_growth"] == pytest.approx(
        3_978_131_528.88 / 2_672_977_090.30 - 1
    )
    assert luzhou_2024["income_statement_page"] == 91
    assert luzhou_2024["inventory_page"] == 86
    assert luzhou_2024["contract_liabilities_page"] == 87


def test_baijiu_operating_quality_rejects_cross_source_mismatch() -> None:
    records = deepcopy(load_baijiu_operating_quality())
    moutai_2025 = next(
        record
        for record in records
        if record["company_code"] == "600519"
        and record["period_year"] == 2025
    )
    moutai_2025["source_url"] = next(
        record["source_url"]
        for record in records
        if record["company_code"] == "000858"
        and record["period_year"] == 2025
    )

    with pytest.raises(ValueError, match="不一致"):
        build_baijiu_operating_quality(
            _baijiu_comparison_rows(),
            records,
        )
