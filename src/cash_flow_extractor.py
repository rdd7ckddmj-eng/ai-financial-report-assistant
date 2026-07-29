"""Deterministic extraction and reconciliation of cash-flow figures."""

import math
import re
from collections.abc import Iterable
from typing import TypedDict


class CashFlowFigures(TypedDict):
    """Key cash-flow totals and their source page."""

    current_operating_cash_flow: float
    previous_operating_cash_flow: float
    current_investing_cash_flow: float
    previous_investing_cash_flow: float
    current_financing_cash_flow: float
    previous_financing_cash_flow: float
    current_net_cash_change: float
    previous_net_cash_change: float
    current_opening_cash: float
    previous_opening_cash: float
    current_exchange_effect: float
    previous_exchange_effect: float
    current_ending_cash: float
    previous_ending_cash: float
    current_period_weeks: int | None
    previous_period_weeks: int | None
    unit: str
    page_number: int


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:-|\(?-?\d[\d,]*(?:\.\d+)?\)?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
WEEKS_PATTERN = re.compile(r"^(\d+) weeks(?: ended)?$", re.IGNORECASE)


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    return [
        " ".join(line.replace("\xa0", " ").split())
        for line in page_text.splitlines()
        if line.strip()
    ]


def _parse_financial_value(value: str) -> float:
    """Convert values such as '3,906' and '(706)' into numbers."""
    if value == "-":
        return 0.0

    is_negative = value.startswith("(") and value.endswith(")")
    cleaned_value = value.strip("()").replace(",", "")
    number = float(cleaned_value)
    return -number if is_negative else number


def _extract_row_pair(
    lines: list[str],
    row_label: str,
) -> tuple[float, float] | None:
    """Return current and previous values immediately after a row label."""
    try:
        row_start = lines.index(row_label)
    except ValueError:
        return None

    values: list[float] = []
    for line in lines[row_start + 1 :]:
        if FINANCIAL_VALUE_PATTERN.fullmatch(line):
            values.append(_parse_financial_value(line))
        else:
            break

    if len(values) < 2:
        return None

    # Some rows include a numeric note reference before the two values.
    return values[-2], values[-1]


def _extract_period_weeks(
    lines: list[str],
) -> tuple[int | None, int | None]:
    """Read current and previous period lengths when the PDF shows them."""
    period_weeks = [
        int(match.group(1))
        for line in lines
        if (match := WEEKS_PATTERN.fullmatch(line)) is not None
    ]
    if len(period_weeks) < 2:
        return None, None

    return period_weeks[0], period_weeks[1]


def extract_cash_flow_figures(
    page_number: int,
    page_text: str,
) -> CashFlowFigures | None:
    """Extract cash-flow totals only when both cash reconciliations pass."""
    lines = _normalise_lines(page_text)
    if "Group cash flow statement" not in lines:
        return None

    row_labels = {
        "operating": "Net cash generated from/(used in) operating activities",
        "investing": "Net cash generated from/(used in) investing activities",
        "financing": "Net cash generated from/(used in) financing activities",
        "net_change": "Net increase/(decrease) in cash and cash equivalents",
        "opening": "Cash and cash equivalents at the beginning of the year",
        "exchange": "Effect of foreign exchange rate changes",
        "ending": "Cash and cash equivalents at the end of the year",
    }
    extracted_rows = {
        name: _extract_row_pair(lines, label)
        for name, label in row_labels.items()
    }
    if any(values is None for values in extracted_rows.values()):
        return None

    operating = extracted_rows["operating"]
    investing = extracted_rows["investing"]
    financing = extracted_rows["financing"]
    net_change = extracted_rows["net_change"]
    opening = extracted_rows["opening"]
    exchange = extracted_rows["exchange"]
    ending = extracted_rows["ending"]
    assert operating is not None
    assert investing is not None
    assert financing is not None
    assert net_change is not None
    assert opening is not None
    assert exchange is not None
    assert ending is not None

    current_sections_reconcile = math.isclose(
        operating[0] + investing[0] + financing[0],
        net_change[0],
        abs_tol=0.5,
    )
    previous_sections_reconcile = math.isclose(
        operating[1] + investing[1] + financing[1],
        net_change[1],
        abs_tol=0.5,
    )
    current_cash_reconciles = math.isclose(
        opening[0] + net_change[0] + exchange[0],
        ending[0],
        abs_tol=0.5,
    )
    previous_cash_reconciles = math.isclose(
        opening[1] + net_change[1] + exchange[1],
        ending[1],
        abs_tol=0.5,
    )
    if (
        not current_sections_reconcile
        or not previous_sections_reconcile
        or not current_cash_reconciles
        or not previous_cash_reconciles
    ):
        return None

    current_weeks, previous_weeks = _extract_period_weeks(lines)
    unit = next((line for line in lines if UNIT_PATTERN.fullmatch(line)), "")
    return {
        "current_operating_cash_flow": operating[0],
        "previous_operating_cash_flow": operating[1],
        "current_investing_cash_flow": investing[0],
        "previous_investing_cash_flow": investing[1],
        "current_financing_cash_flow": financing[0],
        "previous_financing_cash_flow": financing[1],
        "current_net_cash_change": net_change[0],
        "previous_net_cash_change": net_change[1],
        "current_opening_cash": opening[0],
        "previous_opening_cash": opening[1],
        "current_exchange_effect": exchange[0],
        "previous_exchange_effect": exchange[1],
        "current_ending_cash": ending[0],
        "previous_ending_cash": ending[1],
        "current_period_weeks": current_weeks,
        "previous_period_weeks": previous_weeks,
        "unit": unit,
        "page_number": page_number,
    }


def find_cash_flow_figures(
    pages: Iterable[tuple[int, str]],
) -> CashFlowFigures | None:
    """Scan report pages and return the first reconciled cash-flow statement."""
    for page_number, page_text in pages:
        figures = extract_cash_flow_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures

    return None
