import pytest

from src.financial_ratios import (
    current_ratio,
    liabilities_to_assets_ratio,
    net_profit_margin,
    revenue_growth,
)


def test_net_profit_margin_for_profitable_company() -> None:
    assert net_profit_margin(1_200_000, 120_000) == pytest.approx(0.10)


def test_net_profit_margin_for_loss_making_company() -> None:
    assert net_profit_margin(1_000_000, -50_000) == pytest.approx(-0.05)


def test_net_profit_margin_rejects_zero_revenue() -> None:
    with pytest.raises(ValueError, match="Revenue must not be zero"):
        net_profit_margin(0, 120_000)


def test_revenue_growth_for_growing_revenue() -> None:
    assert revenue_growth(1_000_000, 1_200_000) == pytest.approx(0.20)


def test_revenue_growth_for_declining_revenue() -> None:
    assert revenue_growth(1_000_000, 800_000) == pytest.approx(-0.20)


def test_revenue_growth_for_unchanged_revenue() -> None:
    assert revenue_growth(1_000_000, 1_000_000) == pytest.approx(0.00)


def test_revenue_growth_rejects_zero_previous_revenue() -> None:
    with pytest.raises(ValueError, match="Previous revenue must not be zero"):
        revenue_growth(0, 1_000_000)


def test_current_ratio_when_assets_exceed_liabilities() -> None:
    assert current_ratio(1_500_000, 1_000_000) == pytest.approx(1.50)


def test_current_ratio_when_assets_are_below_liabilities() -> None:
    assert current_ratio(800_000, 1_000_000) == pytest.approx(0.80)


def test_current_ratio_rejects_zero_current_liabilities() -> None:
    with pytest.raises(ValueError, match="Current liabilities must not be zero"):
        current_ratio(1_000_000, 0)


def test_liabilities_to_assets_ratio() -> None:
    assert liabilities_to_assets_ratio(5_000_000, 2_000_000) == pytest.approx(0.40)


def test_liabilities_to_assets_ratio_above_one() -> None:
    assert liabilities_to_assets_ratio(1_000_000, 1_200_000) == pytest.approx(1.20)


def test_liabilities_to_assets_ratio_rejects_zero_assets() -> None:
    with pytest.raises(ValueError, match="Total assets must not be zero"):
        liabilities_to_assets_ratio(0, 1_000_000)
