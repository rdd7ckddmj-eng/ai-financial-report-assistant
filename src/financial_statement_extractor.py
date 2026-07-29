"""Deterministic extraction of key figures from an income-statement page."""

import re
from collections.abc import Iterable
from typing import TypedDict


class IncomeStatementFigures(TypedDict):
    """Key figures and their source page."""

    current_revenue: float
    previous_revenue: float
    current_net_profit: float
    previous_net_profit: float
    unit: str
    page_number: int
    current_period_weeks: int | None
    previous_period_weeks: int | None


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:-|\(?-?\d[\d,]*(?:\.\d+)?\)?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
WEEKS_PATTERN = re.compile(r"^(\d+) weeks ended$", re.IGNORECASE)


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    return [
        " ".join(line.replace("\xa0", " ").split())
        for line in page_text.splitlines()
        if line.strip()
    ]


def _parse_financial_value(value: str) -> float:
    """Convert PDF table values such as '1,787' or '(153)' into numbers."""
    if value == "-":
        return 0.0

    is_negative = value.startswith("(") and value.endswith(")")
    cleaned_value = value.strip("()").replace(",", "")
    number = float(cleaned_value)
    return -number if is_negative else number


def _extract_six_column_totals(
    lines: list[str],
    row_label: str,
) -> tuple[float, float] | None:
    """Return current and previous totals from a two-year, six-column row."""
    try:
        row_start = lines.index(row_label)
    except ValueError:
        return None

    row_values: list[str] = []
    for line in lines[row_start + 1 :]:
        if FINANCIAL_VALUE_PATTERN.fullmatch(line):
            row_values.append(line)
        else:
            break

    if len(row_values) < 6:
        return None

    # The final six values are:
    # current before adjustments, current adjustment, current total,
    # previous before adjustments, previous adjustment, previous total.
    current_total = _parse_financial_value(row_values[-4])
    previous_total = _parse_financial_value(row_values[-1])
    return current_total, previous_total


def _extract_period_weeks(
    lines: list[str],
) -> tuple[int | None, int | None]:
    """Read the current and previous reporting-period lengths when shown."""
    period_weeks = [
        int(match.group(1))
        for line in lines
        if (match := WEEKS_PATTERN.fullmatch(line)) is not None
    ]
    if len(period_weeks) < 2:
        return None, None

    return period_weeks[0], period_weeks[1]


def extract_income_statement_figures(
    page_number: int,
    page_text: str,
) -> IncomeStatementFigures | None:
    """Extract revenue and profit totals without guessing missing values."""
    lines = _normalise_lines(page_text)

    if "Group income statement" not in lines:
        return None

    revenue_totals = _extract_six_column_totals(lines, "Revenue")
    profit_totals = _extract_six_column_totals(
        lines,
        "Profit/(loss) for the year",
    )
    if revenue_totals is None or profit_totals is None:
        return None

    unit = next((line for line in lines if UNIT_PATTERN.fullmatch(line)), "")
    current_revenue, previous_revenue = revenue_totals
    current_net_profit, previous_net_profit = profit_totals
    current_period_weeks, previous_period_weeks = _extract_period_weeks(lines)

    return {
        "current_revenue": current_revenue,
        "previous_revenue": previous_revenue,
        "current_net_profit": current_net_profit,
        "previous_net_profit": previous_net_profit,
        "unit": unit,
        "page_number": page_number,
        "current_period_weeks": current_period_weeks,
        "previous_period_weeks": previous_period_weeks,
    }


def find_income_statement_figures(
    pages: Iterable[tuple[int, str]],
) -> IncomeStatementFigures | None:
    """Scan report pages and return the first supported income statement."""
    for page_number, page_text in pages:
        figures = extract_income_statement_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures

    return None
