"""Deterministic financial-ratio calculations."""


def net_profit_margin(revenue: float, net_profit: float) -> float:
    """Return net profit as a proportion of revenue.

    A result of 0.10 means that the company earned 10 pence of net profit
    for each pound of revenue.
    """
    if revenue == 0:
        raise ValueError("Revenue must not be zero.")

    # Financial formula: net profit margin = net profit / revenue.
    return net_profit / revenue


def revenue_growth(
    previous_revenue: float,
    current_revenue: float,
) -> float:
    """Return the change in revenue as a proportion of previous revenue."""
    if previous_revenue == 0:
        raise ValueError("Previous revenue must not be zero.")

    # Financial formula: (current revenue - previous revenue) / previous revenue.
    return (current_revenue - previous_revenue) / previous_revenue


def current_ratio(
    current_assets: float,
    current_liabilities: float,
) -> float:
    """Return current assets divided by current liabilities."""
    if current_liabilities == 0:
        raise ValueError("Current liabilities must not be zero.")

    # Financial formula: current ratio = current assets / current liabilities.
    return current_assets / current_liabilities


def liabilities_to_assets_ratio(
    total_assets: float,
    total_liabilities: float,
) -> float:
    """Return total liabilities as a proportion of total assets."""
    if total_assets == 0:
        raise ValueError("Total assets must not be zero.")

    # Financial formula: liabilities-to-assets = liabilities / assets.
    return total_liabilities / total_assets
