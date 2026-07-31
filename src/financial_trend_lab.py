"""Deterministic cross-year review of verified annual-report facts.

The module describes how audited figures changed across publication-aware
financial history.  It deliberately avoids valuation, price forecasts, and
buy/sell language.  Input points are expected to have already passed the
point-in-time publication filter in :mod:`src.financial_history`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypedDict

from src.financial_history import FinancialTrendPoint


class FinancialTrendReview(TypedDict):
    """A compact, auditable summary of one verified financial series."""

    start_year: int
    end_year: int
    period_count: int
    year_span: int
    revenue_cagr: float | None
    net_profit_cagr: float | None
    operating_cash_flow_cagr: float | None
    latest_revenue_growth: float | None
    latest_net_profit_growth: float | None
    latest_operating_cash_flow_growth: float | None
    latest_net_margin: float
    latest_net_margin_change: float | None
    latest_cash_conversion: float
    latest_cash_conversion_change: float | None
    latest_liabilities_to_assets: float
    latest_liabilities_to_assets_change: float | None
    growth_alignment: str
    cash_alignment: str
    restatement_count: int
    observations: list[str]
    limitation: str


def _finite_number(value: object, field_name: str) -> float:
    """Return one finite numeric input or raise an explicit error."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} 不是有效数字。") from error
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} 必须是有限数字。")
    return parsed


def _cagr(start: float, end: float, year_span: int) -> float | None:
    """Calculate CAGR only when the economic and time bases are usable."""
    if year_span <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / year_span) - 1


def _same_direction(first: float | None, second: float | None) -> bool | None:
    """Compare signs without turning zero into a positive or negative move."""
    if first is None or second is None:
        return None
    if first == 0 or second == 0:
        return first == second
    return (first > 0) == (second > 0)


def _format_percent(value: float | None) -> str:
    """Format one ratio for deterministic Chinese observations."""
    if value is None:
        return "数据不足"
    return f"{value:.1%}"


def _format_points(value: float | None) -> str:
    """Format a ratio difference as percentage points."""
    if value is None:
        return "数据不足"
    return f"{value * 100:+.2f} 个百分点"


def build_financial_trend_review(
    points: Sequence[FinancialTrendPoint],
) -> FinancialTrendReview:
    """Describe verified annual trends with transparent, neutral rules."""
    if not points:
        raise ValueError("财务趋势至少需要一个已核验年度。")

    years = [int(point["period_year"]) for point in points]
    if years != sorted(years) or len(years) != len(set(years)):
        raise ValueError("财务年度必须按时间递增且不能重复。")

    checked_points = list(points)
    numeric_fields = (
        "revenue",
        "net_profit",
        "operating_cash_flow",
        "net_margin",
        "cash_conversion",
        "liabilities_to_assets",
    )
    for point in checked_points:
        for field_name in numeric_fields:
            _finite_number(point[field_name], field_name)

    first = checked_points[0]
    latest = checked_points[-1]
    year_span = years[-1] - years[0]
    revenue_cagr = _cagr(first["revenue"], latest["revenue"], year_span)
    net_profit_cagr = _cagr(
        first["net_profit"],
        latest["net_profit"],
        year_span,
    )
    operating_cash_flow_cagr = _cagr(
        first["operating_cash_flow"],
        latest["operating_cash_flow"],
        year_span,
    )

    growth_same_direction = _same_direction(
        latest["revenue_growth"],
        latest["net_profit_growth"],
    )
    if growth_same_direction is None:
        growth_alignment = "比较期不足"
    elif growth_same_direction:
        growth_alignment = "收入与利润同向"
    else:
        growth_alignment = "收入与利润方向不一致"

    cash_same_direction = _same_direction(
        latest["net_profit_growth"],
        latest["operating_cash_flow_growth"],
    )
    if cash_same_direction is None:
        cash_alignment = "比较期不足"
    elif cash_same_direction:
        cash_alignment = "利润与经营现金同向"
    else:
        cash_alignment = "利润与经营现金方向不一致"

    observations: list[str] = []
    if year_span > 0:
        observations.append(
            f"{years[0]}—{years[-1]} 年：营业收入复合年变化率为 "
            f"{_format_percent(revenue_cagr)}，归母净利润为 "
            f"{_format_percent(net_profit_cagr)}，经营现金流净额为 "
            f"{_format_percent(operating_cash_flow_cagr)}。"
        )
    else:
        observations.append("当前只有一个已核验年度，不能计算跨年复合变化率。")

    observations.append(
        f"{latest['period_year']} 年同比：营业收入 "
        f"{_format_percent(latest['revenue_growth'])}，归母净利润 "
        f"{_format_percent(latest['net_profit_growth'])}，经营现金流净额 "
        f"{_format_percent(latest['operating_cash_flow_growth'])}；"
        f"结构关系为“{growth_alignment}”“{cash_alignment}”。"
    )
    observations.append(
        f"最新归母净利率为 {_format_percent(latest['net_margin'])}，"
        f"较上一年度变化 {_format_points(latest['net_margin_change'])}；"
        f"经营现金 / 归母净利润为 {latest['cash_conversion']:.2f} 倍。"
    )
    observations.append(
        f"最新负债占总资产为 "
        f"{_format_percent(latest['liabilities_to_assets'])}，"
        f"较上一年度变化 "
        f"{_format_points(latest['liabilities_to_assets_change'])}。"
    )

    restatement_count = sum(
        point["accounting_basis"] == "restated"
        for point in checked_points
    )
    if restatement_count:
        observations.append(
            f"当前序列包含 {restatement_count} 个追溯调整后的年度版本；"
            "页面同时保留调整来源和公开日期。"
        )

    return {
        "start_year": years[0],
        "end_year": years[-1],
        "period_count": len(checked_points),
        "year_span": year_span,
        "revenue_cagr": revenue_cagr,
        "net_profit_cagr": net_profit_cagr,
        "operating_cash_flow_cagr": operating_cash_flow_cagr,
        "latest_revenue_growth": latest["revenue_growth"],
        "latest_net_profit_growth": latest["net_profit_growth"],
        "latest_operating_cash_flow_growth": latest[
            "operating_cash_flow_growth"
        ],
        "latest_net_margin": latest["net_margin"],
        "latest_net_margin_change": latest["net_margin_change"],
        "latest_cash_conversion": latest["cash_conversion"],
        "latest_cash_conversion_change": latest["cash_conversion_change"],
        "latest_liabilities_to_assets": latest["liabilities_to_assets"],
        "latest_liabilities_to_assets_change": latest[
            "liabilities_to_assets_change"
        ],
        "growth_alignment": growth_alignment,
        "cash_alignment": cash_alignment,
        "restatement_count": restatement_count,
        "observations": observations,
        "limitation": (
            "财务趋势只描述已经公开并人工核验的年报数字变化。"
            "复合变化率、利润率、现金利润比和负债比例均不等同于估值、"
            "未来业绩或买卖建议。"
        ),
    }
