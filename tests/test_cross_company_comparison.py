from copy import deepcopy
from datetime import date

import pytest

from src.company_industry import load_company_industry_catalog
from src.cross_company_comparison import (
    build_cross_company_comparison,
    common_financial_years,
)
from src.financial_history import (
    load_financial_history_catalog,
    load_verified_financial_history,
    select_financial_history_as_of,
)


def _verified_comparison_inputs():
    cases = load_financial_history_catalog()
    industry_profiles = load_company_industry_catalog()
    points_by_code = {
        case["company_code"]: select_financial_history_as_of(
            load_verified_financial_history(case["company_code"]),
            date.today(),
        )["points"]
        for case in cases
    }
    return cases, points_by_code, industry_profiles


def test_comparison_uses_latest_common_verified_year() -> None:
    cases, points_by_code, industry_profiles = _verified_comparison_inputs()

    comparison = build_cross_company_comparison(
        cases,
        points_by_code,
        industry_profiles=industry_profiles,
    )

    assert comparison["common_years"] == [2022, 2023, 2024]
    assert comparison["selected_year"] == 2024
    assert comparison["company_count"] == 3
    assert [row["company_name"] for row in comparison["rows"]] == [
        "贵州茅台",
        "宁德时代",
        "比亚迪",
    ]
    assert comparison["scope_label"] == "跨行业比较（3个研究组）"
    assert comparison["industry_group_count"] == 3
    assert comparison["is_same_peer_group"] is False
    assert "不含估值、预测或买卖建议" in comparison["limitation"]


def test_comparison_preserves_byd_values_and_official_evidence() -> None:
    cases, points_by_code, industry_profiles = _verified_comparison_inputs()

    comparison = build_cross_company_comparison(
        cases,
        points_by_code,
        industry_profiles=industry_profiles,
    )
    byd = next(
        row for row in comparison["rows"]
        if row["company_code"] == "002594"
    )

    assert byd["revenue"] == pytest.approx(777_102_455_000)
    assert byd["net_profit"] == pytest.approx(40_254_346_000)
    assert byd["operating_cash_flow"] == pytest.approx(133_453_873_000)
    assert byd["net_margin"] == pytest.approx(
        40_254_346_000 / 777_102_455_000
    )
    assert byd["liabilities_to_assets"] == pytest.approx(
        584_667_646_000 / 783_355_855_000
    )
    assert byd["summary_page"] == 11
    assert byd["balance_sheet_page"] == 143
    assert byd["source_url"] == (
        "https://static.cninfo.com.cn/finalpage/2025-03-25/"
        "1222881496.PDF"
    )
    assert byd["revenue_position"] == "高于样本中位数"
    assert byd["net_margin_position"] == "低于样本中位数"


def test_comparison_can_select_an_earlier_common_year() -> None:
    cases, points_by_code, industry_profiles = _verified_comparison_inputs()

    comparison = build_cross_company_comparison(
        cases,
        points_by_code,
        selected_year=2023,
        industry_profiles=industry_profiles,
    )

    assert comparison["selected_year"] == 2023
    assert all(row["period_year"] == 2023 for row in comparison["rows"])
    assert all(row["published_date"][:4] == "2024" for row in comparison["rows"])
    assert all(row["revenue_growth"] is not None for row in comparison["rows"])


def test_comparison_requires_two_distinct_companies() -> None:
    cases, points_by_code, _ = _verified_comparison_inputs()

    with pytest.raises(ValueError, match="至少需要两家"):
        common_financial_years(cases[:1], points_by_code)

    with pytest.raises(ValueError, match="不能重复"):
        common_financial_years([cases[0], cases[0]], points_by_code)


def test_comparison_rejects_missing_common_year_or_invalid_selection() -> None:
    cases, points_by_code, industry_profiles = _verified_comparison_inputs()
    non_overlapping = {
        cases[0]["company_code"]: [points_by_code[cases[0]["company_code"]][-1]],
        cases[1]["company_code"]: [points_by_code[cases[1]["company_code"]][0]],
    }

    with pytest.raises(ValueError, match="没有共同"):
        common_financial_years(cases[:2], non_overlapping)

    with pytest.raises(ValueError, match="不是所有公司的共同"):
        build_cross_company_comparison(
            cases,
            points_by_code,
            2025,
            industry_profiles=industry_profiles,
        )


def test_comparison_rejects_company_identity_mismatch() -> None:
    cases, points_by_code, industry_profiles = _verified_comparison_inputs()
    invalid_points = deepcopy(points_by_code)
    invalid_points["300750"][0]["company_code"] = "002594"

    with pytest.raises(ValueError, match="公司身份"):
        build_cross_company_comparison(
            cases,
            invalid_points,
            industry_profiles=industry_profiles,
        )
