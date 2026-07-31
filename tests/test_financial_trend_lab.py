from copy import deepcopy

import pytest

from src.financial_history import (
    load_moutai_financial_history,
    load_verified_financial_history,
    select_financial_history_as_of,
)
from src.financial_trend_lab import build_financial_trend_review


def _verified_points():
    return select_financial_history_as_of(
        load_moutai_financial_history(),
        "2026-07-30",
    )["points"]


def test_review_summarises_verified_moutai_history() -> None:
    points = _verified_points()

    review = build_financial_trend_review(points)

    assert review["start_year"] == 2022
    assert review["end_year"] == 2025
    assert review["period_count"] == 4
    assert review["year_span"] == 3
    assert review["revenue_cagr"] == pytest.approx(
        (points[-1]["revenue"] / points[0]["revenue"]) ** (1 / 3) - 1
    )
    assert review["net_profit_cagr"] == pytest.approx(
        (points[-1]["net_profit"] / points[0]["net_profit"]) ** (1 / 3)
        - 1
    )
    assert review["operating_cash_flow_cagr"] == pytest.approx(
        (
            points[-1]["operating_cash_flow"]
            / points[0]["operating_cash_flow"]
        )
        ** (1 / 3)
        - 1
    )
    assert review["growth_alignment"] == "收入与利润同向"
    assert review["cash_alignment"] == "利润与经营现金同向"
    assert review["restatement_count"] == 1
    assert any("追溯调整" in item for item in review["observations"])


def test_review_identifies_direction_mismatches_without_scoring() -> None:
    points = deepcopy(_verified_points())
    points[-1]["net_profit_growth"] = 0.05

    review = build_financial_trend_review(points)

    assert review["growth_alignment"] == "收入与利润方向不一致"
    assert review["cash_alignment"] == "利润与经营现金方向不一致"
    assert "买卖建议" in review["limitation"]


def test_review_summarises_verified_catl_history() -> None:
    points = select_financial_history_as_of(
        load_verified_financial_history("300750"),
        "2025-03-15",
    )["points"]

    review = build_financial_trend_review(points)

    assert review["start_year"] == 2022
    assert review["end_year"] == 2024
    assert review["period_count"] == 3
    assert review["growth_alignment"] == "收入与利润方向不一致"
    assert review["cash_alignment"] == "利润与经营现金同向"
    assert review["restatement_count"] == 0


def test_review_summarises_verified_byd_history() -> None:
    points = select_financial_history_as_of(
        load_verified_financial_history("002594"),
        "2025-03-25",
    )["points"]

    review = build_financial_trend_review(points)

    assert review["start_year"] == 2022
    assert review["end_year"] == 2024
    assert review["period_count"] == 3
    assert review["growth_alignment"] == "收入与利润同向"
    assert review["cash_alignment"] == "利润与经营现金方向不一致"
    assert review["restatement_count"] == 0


def test_single_year_does_not_invent_cross_year_change() -> None:
    review = build_financial_trend_review(_verified_points()[:1])

    assert review["revenue_cagr"] is None
    assert review["net_profit_cagr"] is None
    assert review["operating_cash_flow_cagr"] is None
    assert review["growth_alignment"] == "比较期不足"
    assert review["cash_alignment"] == "比较期不足"
    assert "不能计算" in review["observations"][0]


def test_review_rejects_unsorted_or_nonfinite_points() -> None:
    points = _verified_points()

    with pytest.raises(ValueError, match="按时间递增"):
        build_financial_trend_review(list(reversed(points)))

    invalid = deepcopy(points)
    invalid[-1]["revenue"] = float("nan")
    with pytest.raises(ValueError, match="有限数字"):
        build_financial_trend_review(invalid)
