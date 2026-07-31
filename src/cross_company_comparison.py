"""Deterministic common-year comparison for verified A-share companies.

The module compares only annual-report facts that passed the shared catalogue
checks and exist for the same financial year.  It intentionally separates
scale, profitability, cash conversion, and balance-sheet structure instead of
compressing unlike businesses into one unsupported score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import TypedDict

from src.financial_history import (
    FinancialHistoryCase,
    FinancialTrendPoint,
)


class CrossCompanyComparisonRow(TypedDict):
    """One company's verified facts for the selected common year."""

    company_code: str
    company_name: str
    canonical_code: str
    exchange_name: str
    period_year: int
    published_date: str
    report_title: str
    source_url: str
    summary_page: int
    balance_sheet_page: int
    accounting_basis: str
    notes: str
    revenue: float
    net_profit: float
    operating_cash_flow: float
    total_assets: float
    total_liabilities: float
    revenue_growth: float | None
    net_profit_growth: float | None
    operating_cash_flow_growth: float | None
    net_margin: float
    cash_conversion: float
    liabilities_to_assets: float
    revenue_position: str
    net_margin_position: str
    cash_conversion_position: str
    liabilities_to_assets_position: str


class CrossCompanyComparison(TypedDict):
    """Auditable result for a selected set of verified companies."""

    common_years: list[int]
    selected_year: int
    company_count: int
    rows: list[CrossCompanyComparisonRow]
    observations: list[str]
    scope_label: str
    limitation: str


COMPARISON_NUMERIC_FIELDS = (
    "revenue",
    "net_profit",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
    "net_margin",
    "cash_conversion",
    "liabilities_to_assets",
)


def _finite_number(value: object, field_name: str) -> float:
    """Accept only finite Python-calculated financial values."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效数字。") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} 必须是有限数字。")
    return parsed


def _relative_to_median(value: float, sample_median: float) -> str:
    """Describe sample position without implying that high or low is better."""
    if math.isclose(value, sample_median, rel_tol=1e-9, abs_tol=1e-12):
        return "接近样本中位数"
    if value > sample_median:
        return "高于样本中位数"
    return "低于样本中位数"


def _names_at_extreme(
    rows: Sequence[CrossCompanyComparisonRow],
    field_name: str,
    *,
    highest: bool,
) -> str:
    """Return every tied company at one numerical extreme."""
    values = [_finite_number(row[field_name], field_name) for row in rows]
    target = max(values) if highest else min(values)
    return "、".join(
        row["company_name"]
        for row in rows
        if math.isclose(
            _finite_number(row[field_name], field_name),
            target,
            rel_tol=1e-9,
            abs_tol=1e-12,
        )
    )


def common_financial_years(
    cases: Sequence[FinancialHistoryCase],
    points_by_code: Mapping[str, Sequence[FinancialTrendPoint]],
) -> list[int]:
    """Find complete financial years shared by every selected company."""
    if len(cases) < 2:
        raise ValueError("横向比较至少需要两家已核验公司。")

    codes = [case["company_code"] for case in cases]
    if len(codes) != len(set(codes)):
        raise ValueError("横向比较不能重复选择同一家公司。")

    shared_years: set[int] | None = None
    for case in cases:
        code = case["company_code"]
        points = list(points_by_code.get(code, ()))
        if not points:
            raise ValueError(f"{case['company_name']}缺少可比较的财务年度。")
        years = [int(point["period_year"]) for point in points]
        if years != sorted(years) or len(years) != len(set(years)):
            raise ValueError("每家公司的财务年度必须递增且不能重复。")
        if any(point["company_code"] != code for point in points):
            raise ValueError("横向比较中的公司身份与财务数据不一致。")
        shared_years = (
            set(years)
            if shared_years is None
            else shared_years.intersection(years)
        )

    common = sorted(shared_years or set())
    if not common:
        raise ValueError("所选公司没有共同的已核验财务年度。")
    return common


def build_cross_company_comparison(
    cases: Sequence[FinancialHistoryCase],
    points_by_code: Mapping[str, Sequence[FinancialTrendPoint]],
    selected_year: int | None = None,
) -> CrossCompanyComparison:
    """Compare verified companies on one shared annual-report year."""
    checked_cases = list(cases)
    common_years = common_financial_years(checked_cases, points_by_code)
    year = max(common_years) if selected_year is None else int(selected_year)
    if year not in common_years:
        raise ValueError("所选年度不是所有公司的共同已核验年度。")

    provisional_rows: list[dict[str, object]] = []
    for case in checked_cases:
        point = next(
            point
            for point in points_by_code[case["company_code"]]
            if int(point["period_year"]) == year
        )
        if point["company_name"] != case["company_name"]:
            raise ValueError("接入清单中的公司名称与财务数据不一致。")
        for field_name in COMPARISON_NUMERIC_FIELDS:
            _finite_number(point[field_name], field_name)
        provisional_rows.append(
            {
                "company_code": case["company_code"],
                "company_name": case["company_name"],
                "canonical_code": case["canonical_code"],
                "exchange_name": case["exchange_name"],
                "period_year": year,
                "published_date": point["published_date"].isoformat(),
                "report_title": point["report_title"],
                "source_url": point["source_url"],
                "summary_page": point["summary_page"],
                "balance_sheet_page": point["balance_sheet_page"],
                "accounting_basis": point["accounting_basis"],
                "notes": point["notes"],
                "revenue": point["revenue"],
                "net_profit": point["net_profit"],
                "operating_cash_flow": point["operating_cash_flow"],
                "total_assets": point["total_assets"],
                "total_liabilities": point["total_liabilities"],
                "revenue_growth": point["revenue_growth"],
                "net_profit_growth": point["net_profit_growth"],
                "operating_cash_flow_growth": point[
                    "operating_cash_flow_growth"
                ],
                "net_margin": point["net_margin"],
                "cash_conversion": point["cash_conversion"],
                "liabilities_to_assets": point["liabilities_to_assets"],
            }
        )

    medians = {
        field_name: median(
            _finite_number(row[field_name], field_name)
            for row in provisional_rows
        )
        for field_name in (
            "revenue",
            "net_margin",
            "cash_conversion",
            "liabilities_to_assets",
        )
    }
    rows: list[CrossCompanyComparisonRow] = []
    for provisional in provisional_rows:
        rows.append(
            {
                **provisional,
                "revenue_position": _relative_to_median(
                    _finite_number(provisional["revenue"], "revenue"),
                    medians["revenue"],
                ),
                "net_margin_position": _relative_to_median(
                    _finite_number(provisional["net_margin"], "net_margin"),
                    medians["net_margin"],
                ),
                "cash_conversion_position": _relative_to_median(
                    _finite_number(
                        provisional["cash_conversion"],
                        "cash_conversion",
                    ),
                    medians["cash_conversion"],
                ),
                "liabilities_to_assets_position": _relative_to_median(
                    _finite_number(
                        provisional["liabilities_to_assets"],
                        "liabilities_to_assets",
                    ),
                    medians["liabilities_to_assets"],
                ),
            }  # type: ignore[typeddict-item]
        )

    revenue_high = _names_at_extreme(rows, "revenue", highest=True)
    revenue_low = _names_at_extreme(rows, "revenue", highest=False)
    margin_high = _names_at_extreme(rows, "net_margin", highest=True)
    margin_low = _names_at_extreme(rows, "net_margin", highest=False)
    leverage_high = _names_at_extreme(
        rows,
        "liabilities_to_assets",
        highest=True,
    )
    leverage_low = _names_at_extreme(
        rows,
        "liabilities_to_assets",
        highest=False,
    )
    growth_ready = sum(
        row["revenue_growth"] is not None
        and row["net_profit_growth"] is not None
        and row["operating_cash_flow_growth"] is not None
        for row in rows
    )

    observations = [
        (
            f"共同口径采用 {year} 财务年度，覆盖 {len(rows)} 家公司；"
            "每家公司只使用截至比较截止日已经公开的最新有效年报版本。"
        ),
        (
            f"营业收入规模区间两端为 {revenue_low} 与 {revenue_high}；"
            "这只描述规模差异，不代表经营质量排序。"
        ),
        (
            f"归母净利率区间两端为 {margin_low} 与 {margin_high}；"
            "跨商业模式的利润率不能脱离行业结构直接判断优劣。"
        ),
        (
            f"负债占总资产区间两端为 {leverage_low} 与 {leverage_high}；"
            "负债结构还需结合有息债务、营运资金和现金流继续核查。"
        ),
        (
            f"{growth_ready}/{len(rows)} 家公司的收入、利润和经营现金"
            "均具备上一年度同比基数。"
        ),
    ]

    return {
        "common_years": common_years,
        "selected_year": year,
        "company_count": len(rows),
        "rows": rows,
        "observations": observations,
        "scope_label": "跨公司演示样本（非严格同行组）",
        "limitation": (
            "当前接入清单尚未保存统一行业分类，因此页面不能把所选公司"
            "宣称为严格同行组。不同商业模式的规模、利润率、现金转换和"
            "负债结构不可直接合成为优劣分数；本结果不含估值、预测或"
            "买卖建议。"
        ),
    }
