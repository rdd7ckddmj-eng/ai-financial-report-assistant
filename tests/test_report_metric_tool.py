from typing import cast

import pytest

from src.balance_sheet_extractor import BalanceSheetFigures
from src.financial_statement_extractor import IncomeStatementFigures
from src.report_metric_tool import run_report_metric_tool


INCOME_FIGURES = cast(
    IncomeStatementFigures,
    {
        "current_revenue": 73_712.0,
        "previous_revenue": 69_916.0,
        "current_net_profit": 1_787.0,
        "previous_net_profit": 1_630.0,
        "unit": "£m",
        "page_number": 123,
        "current_period_weeks": 53,
        "previous_period_weeks": 52,
    },
)

BALANCE_FIGURES = cast(
    BalanceSheetFigures,
    {
        "current_resources": 8_483.0,
        "current_liabilities": 14_329.0,
        "current_total_assets": 39_474.0,
        "current_total_liabilities": 28_017.0,
        "unit": "£m",
        "page_number": 125,
    },
)


def test_metric_tool_calculates_net_profit_margin() -> None:
    result = run_report_metric_tool(
        "net_profit_margin",
        INCOME_FIGURES,
        BALANCE_FIGURES,
    )

    assert result["is_available"] is True
    assert result["display_value"] == "2.4%"
    assert result["formula"] == "1,787 ÷ 73,712 = 2.4%"
    assert result["source_page"] == 123
    assert result["source_pages"] == [123]


def test_metric_tool_calculates_revenue_growth_with_period_warning() -> None:
    result = run_report_metric_tool(
        "revenue_growth",
        INCOME_FIGURES,
        BALANCE_FIGURES,
    )

    assert result["display_value"] == "5.4%"
    assert "53 weeks versus 52 weeks" in result["messages"][1]
    assert result["source_page"] == 123


def test_metric_tool_calculates_current_ratio() -> None:
    result = run_report_metric_tool(
        "current_ratio",
        INCOME_FIGURES,
        BALANCE_FIGURES,
    )

    assert result["display_value"] == "0.59x"
    assert result["formula"] == "8,483 ÷ 14,329 = 0.59x"
    assert result["source_page"] == 125


def test_metric_tool_calculates_liabilities_to_assets() -> None:
    result = run_report_metric_tool(
        "liabilities_to_assets",
        INCOME_FIGURES,
        BALANCE_FIGURES,
    )

    assert result["display_value"] == "71.0%"
    assert result["formula"] == "28,017 ÷ 39,474 = 71.0%"
    assert result["source_page"] == 125


def test_metric_tool_reconciles_total_liabilities() -> None:
    result = run_report_metric_tool(
        "total_liabilities",
        INCOME_FIGURES,
        BALANCE_FIGURES,
    )

    assert result["display_value"] == "28,017 £m"
    assert result["formula"] == "14,329 + 13,688 = 28,017 £m"
    assert result["source_page"] == 125


def test_metric_tool_does_not_guess_when_statement_is_missing() -> None:
    result = run_report_metric_tool(
        "net_profit_margin",
        None,
        BALANCE_FIGURES,
    )

    assert result["is_available"] is False
    assert result["source_page"] is None
    assert result["source_pages"] == []
    assert "not found" in result["messages"][0]


def test_metric_tool_keeps_multi_page_statement_provenance() -> None:
    split_page_income = cast(
        IncomeStatementFigures,
        {
            **INCOME_FIGURES,
            "page_number": 61,
            "end_page_number": 62,
        },
    )

    result = run_report_metric_tool(
        "net_profit_margin",
        split_page_income,
        BALANCE_FIGURES,
    )

    assert result["source_page"] == 61
    assert result["source_pages"] == [61, 62]


def test_metric_tool_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unsupported report metric tool"):
        run_report_metric_tool("imaginary_ratio", None, None)
