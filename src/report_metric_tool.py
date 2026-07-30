"""Run supported financial metrics from reconciled report figures."""

from typing import TypedDict

from src.balance_sheet_extractor import BalanceSheetFigures
from src.financial_ratios import (
    current_ratio,
    liabilities_to_assets_ratio,
    net_profit_margin,
    revenue_growth,
)
from src.financial_statement_extractor import IncomeStatementFigures


class MetricInput(TypedDict):
    """One exact report value passed to a Python financial formula."""

    label: str
    value: float
    display_value: str


class MetricToolResult(TypedDict):
    """A deterministic result with its formula, inputs, and source pages."""

    is_available: bool
    tool_name: str
    label: str
    display_value: str
    formula: str
    inputs: list[MetricInput]
    source_page: int | None
    source_pages: list[int]
    messages: list[str]


TOOL_LABELS = {
    "net_profit_margin": "Net profit margin / 净利率",
    "revenue_growth": "Revenue growth / 收入增长率",
    "current_ratio": "Current ratio / 流动比率",
    "liabilities_to_assets": (
        "Liabilities-to-assets ratio / 负债资产比"
    ),
    "total_liabilities": "Total liabilities / 总负债",
}


def _format_report_value(value: float, unit: str) -> str:
    """Show a report value with its original statement unit."""
    unit_text = f" {unit}" if unit else ""
    return f"{value:,.0f}{unit_text}"


def _figure_source_pages(
    figures: IncomeStatementFigures | BalanceSheetFigures,
) -> list[int]:
    """Return every page covered by a single- or multi-page statement."""
    start_page = figures["page_number"]
    end_page = figures.get("end_page_number", start_page)
    return list(range(start_page, end_page + 1))


def _unavailable_result(tool_name: str, message: str) -> MetricToolResult:
    """Return a safe result when the required statement was not extracted."""
    return {
        "is_available": False,
        "tool_name": tool_name,
        "label": TOOL_LABELS[tool_name],
        "display_value": "",
        "formula": "",
        "inputs": [],
        "source_page": None,
        "source_pages": [],
        "messages": [message],
    }


def run_report_metric_tool(
    tool_name: str,
    income_figures: IncomeStatementFigures | None,
    balance_figures: BalanceSheetFigures | None,
) -> MetricToolResult:
    """Calculate one routed metric using only extracted report figures."""
    if tool_name not in TOOL_LABELS:
        raise ValueError(f"Unsupported report metric tool: {tool_name}.")

    if tool_name in {"net_profit_margin", "revenue_growth"}:
        if income_figures is None:
            return _unavailable_result(
                tool_name,
                "The supported income-statement figures were not found, so "
                "the metric was not calculated.",
            )

        unit = income_figures["unit"]
        source_page = income_figures["page_number"]
        source_pages = _figure_source_pages(income_figures)
        if tool_name == "net_profit_margin":
            revenue = income_figures["current_revenue"]
            net_profit = income_figures["current_net_profit"]
            try:
                result = net_profit_margin(revenue, net_profit)
            except ValueError as error:
                return _unavailable_result(tool_name, str(error))
            return {
                "is_available": True,
                "tool_name": tool_name,
                "label": TOOL_LABELS[tool_name],
                "display_value": f"{result:.1%}",
                "formula": (
                    f"{net_profit:,.0f} ÷ {revenue:,.0f} = {result:.1%}"
                ),
                "inputs": [
                    {
                        "label": "Profit for the year",
                        "value": net_profit,
                        "display_value": _format_report_value(
                            net_profit,
                            unit,
                        ),
                    },
                    {
                        "label": "Revenue",
                        "value": revenue,
                        "display_value": _format_report_value(revenue, unit),
                    },
                ],
                "source_page": source_page,
                "source_pages": source_pages,
                "messages": [
                    "Calculated by Python from the reported current-period "
                    "totals."
                ],
            }

        previous_revenue = income_figures["previous_revenue"]
        current_revenue = income_figures["current_revenue"]
        try:
            result = revenue_growth(previous_revenue, current_revenue)
        except ValueError as error:
            return _unavailable_result(tool_name, str(error))
        messages = [
            "Calculated by Python from the reported current and previous "
            "period totals."
        ]
        current_weeks = income_figures["current_period_weeks"]
        previous_weeks = income_figures["previous_period_weeks"]
        if (
            current_weeks is not None
            and previous_weeks is not None
            and current_weeks != previous_weeks
        ):
            messages.append(
                f"Comparability warning: {current_weeks} weeks versus "
                f"{previous_weeks} weeks."
            )
        return {
            "is_available": True,
            "tool_name": tool_name,
            "label": TOOL_LABELS[tool_name],
            "display_value": f"{result:.1%}",
            "formula": (
                f"({current_revenue:,.0f} − {previous_revenue:,.0f}) ÷ "
                f"{previous_revenue:,.0f} = {result:.1%}"
            ),
            "inputs": [
                {
                    "label": "Current-period revenue",
                    "value": current_revenue,
                    "display_value": _format_report_value(
                        current_revenue,
                        unit,
                    ),
                },
                {
                    "label": "Previous-period revenue",
                    "value": previous_revenue,
                    "display_value": _format_report_value(
                        previous_revenue,
                        unit,
                    ),
                },
            ],
            "source_page": source_page,
            "source_pages": source_pages,
            "messages": messages,
        }

    if balance_figures is None:
        return _unavailable_result(
            tool_name,
            "The reconciled balance-sheet figures were not found, so the "
            "metric was not calculated.",
        )

    unit = balance_figures["unit"]
    source_page = balance_figures["page_number"]
    source_pages = _figure_source_pages(balance_figures)
    if tool_name == "total_liabilities":
        current_liabilities = balance_figures["current_liabilities"]
        total_liabilities = balance_figures["current_total_liabilities"]
        non_current_liabilities = total_liabilities - current_liabilities
        return {
            "is_available": True,
            "tool_name": tool_name,
            "label": TOOL_LABELS[tool_name],
            "display_value": _format_report_value(
                total_liabilities,
                unit,
            ),
            "formula": (
                f"{current_liabilities:,.0f} + "
                f"{non_current_liabilities:,.0f} = "
                f"{total_liabilities:,.0f} {unit}"
            ),
            "inputs": [
                {
                    "label": "Current liabilities",
                    "value": current_liabilities,
                    "display_value": _format_report_value(
                        current_liabilities,
                        unit,
                    ),
                },
                {
                    "label": "Non-current liabilities",
                    "value": non_current_liabilities,
                    "display_value": _format_report_value(
                        non_current_liabilities,
                        unit,
                    ),
                },
            ],
            "source_page": source_page,
            "source_pages": source_pages,
            "messages": [
                "Reconciled by Python from current and non-current "
                "liabilities on the group balance sheet."
            ],
        }

    if tool_name == "current_ratio":
        current_resources = balance_figures["current_resources"]
        current_liabilities = balance_figures["current_liabilities"]
        try:
            result = current_ratio(
                current_assets=current_resources,
                current_liabilities=current_liabilities,
            )
        except ValueError as error:
            return _unavailable_result(tool_name, str(error))
        messages = [
            "Current resources include the reported current-assets subtotal "
            "and assets held for sale."
        ]
        if current_resources < current_liabilities:
            messages.append(
                "Current resources are below current liabilities on the "
                "reporting date."
            )
        return {
            "is_available": True,
            "tool_name": tool_name,
            "label": TOOL_LABELS[tool_name],
            "display_value": f"{result:.2f}x",
            "formula": (
                f"{current_resources:,.0f} ÷ "
                f"{current_liabilities:,.0f} = {result:.2f}x"
            ),
            "inputs": [
                {
                    "label": "Current resources",
                    "value": current_resources,
                    "display_value": _format_report_value(
                        current_resources,
                        unit,
                    ),
                },
                {
                    "label": "Current liabilities",
                    "value": current_liabilities,
                    "display_value": _format_report_value(
                        current_liabilities,
                        unit,
                    ),
                },
            ],
            "source_page": source_page,
            "source_pages": source_pages,
            "messages": messages,
        }

    total_assets = balance_figures["current_total_assets"]
    total_liabilities = balance_figures["current_total_liabilities"]
    try:
        result = liabilities_to_assets_ratio(
            total_assets=total_assets,
            total_liabilities=total_liabilities,
        )
    except ValueError as error:
        return _unavailable_result(tool_name, str(error))
    return {
        "is_available": True,
        "tool_name": tool_name,
        "label": TOOL_LABELS[tool_name],
        "display_value": f"{result:.1%}",
        "formula": (
            f"{total_liabilities:,.0f} ÷ {total_assets:,.0f} = "
            f"{result:.1%}"
        ),
        "inputs": [
            {
                "label": "Total liabilities",
                "value": total_liabilities,
                "display_value": _format_report_value(
                    total_liabilities,
                    unit,
                ),
            },
            {
                "label": "Total assets",
                "value": total_assets,
                "display_value": _format_report_value(total_assets, unit),
            },
        ],
        "source_page": source_page,
        "source_pages": source_pages,
        "messages": [
            "This describes balance-sheet structure and does not by itself "
            "measure solvency."
        ],
    }
