"""Deterministic extraction of liquidity figures from a balance sheet."""

import math
import re
from collections.abc import Iterable
from typing import TypedDict


class BalanceSheetFigures(TypedDict):
    """Current assets, liabilities, and their reconciliation."""

    current_assets_subtotal: float
    previous_assets_subtotal: float
    current_assets_held_for_sale: float
    previous_assets_held_for_sale: float
    current_resources: float
    previous_resources: float
    current_liabilities: float
    previous_liabilities: float
    current_net_current_liabilities: float
    previous_net_current_liabilities: float
    current_noncurrent_assets: float
    previous_noncurrent_assets: float
    current_total_assets: float
    previous_total_assets: float
    current_noncurrent_liabilities: float
    previous_noncurrent_liabilities: float
    current_total_liabilities: float
    previous_total_liabilities: float
    current_net_assets: float
    previous_net_assets: float
    unit: str
    page_number: int


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:-|\(?-?\d[\d,]*(?:\.\d+)?\)?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    return [
        " ".join(line.replace("\xa0", " ").split())
        for line in page_text.splitlines()
        if line.strip()
    ]


def _parse_financial_value(value: str) -> float:
    """Convert values such as '8,483' and '(14,329)' into numbers."""
    if value == "-":
        return 0.0

    is_negative = value.startswith("(") and value.endswith(")")
    cleaned_value = value.strip("()").replace(",", "")
    number = float(cleaned_value)
    return -number if is_negative else number


def _extract_last_pair_between(
    lines: list[str],
    start_label: str,
    end_label: str,
) -> tuple[float, float] | None:
    """Return the final current and previous values between two labels."""
    try:
        start_index = lines.index(start_label)
        end_index = lines.index(end_label, start_index + 1)
    except ValueError:
        return None

    values = [
        _parse_financial_value(line)
        for line in lines[start_index + 1 : end_index]
        if FINANCIAL_VALUE_PATTERN.fullmatch(line)
    ]
    if len(values) < 2:
        return None

    return values[-2], values[-1]


def _extract_row_pair(
    lines: list[str],
    row_label: str,
) -> tuple[float, float] | None:
    """Return the current and previous values immediately after a row label."""
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

    return values[-2], values[-1]


def extract_balance_sheet_figures(
    page_number: int,
    page_text: str,
) -> BalanceSheetFigures | None:
    """Extract current resources and liabilities only when totals reconcile."""
    lines = _normalise_lines(page_text)
    if "Group balance sheet" not in lines:
        return None

    current_assets = _extract_last_pair_between(
        lines,
        "Current assets",
        "Non-current assets classified as held for sale",
    )
    current_resources = _extract_last_pair_between(
        lines,
        "Non-current assets classified as held for sale",
        "Current liabilities",
    )
    current_liabilities_raw = _extract_last_pair_between(
        lines,
        "Current liabilities",
        "Net current liabilities",
    )
    reported_net_current_liabilities = _extract_row_pair(
        lines,
        "Net current liabilities",
    )
    noncurrent_assets = _extract_last_pair_between(
        lines,
        "Non-current assets",
        "Current assets",
    )
    noncurrent_liabilities_raw = _extract_last_pair_between(
        lines,
        "Non-current liabilities",
        "Net assets",
    )
    reported_net_assets = _extract_row_pair(lines, "Net assets")
    if (
        current_assets is None
        or current_resources is None
        or current_liabilities_raw is None
        or reported_net_current_liabilities is None
        or noncurrent_assets is None
        or noncurrent_liabilities_raw is None
        or reported_net_assets is None
    ):
        return None

    current_assets_subtotal, previous_assets_subtotal = current_assets
    current_resources_total, previous_resources_total = current_resources
    current_liabilities = abs(current_liabilities_raw[0])
    previous_liabilities = abs(current_liabilities_raw[1])
    current_net, previous_net = reported_net_current_liabilities
    current_noncurrent_assets, previous_noncurrent_assets = noncurrent_assets
    current_noncurrent_liabilities = abs(noncurrent_liabilities_raw[0])
    previous_noncurrent_liabilities = abs(noncurrent_liabilities_raw[1])
    current_net_assets, previous_net_assets = reported_net_assets

    current_total_assets = current_noncurrent_assets + current_resources_total
    previous_total_assets = previous_noncurrent_assets + previous_resources_total
    current_total_liabilities = (
        current_noncurrent_liabilities + current_liabilities
    )
    previous_total_liabilities = (
        previous_noncurrent_liabilities + previous_liabilities
    )

    # Reject the extraction if the balance-sheet arithmetic does not agree
    # with the published net-current-liabilities row.
    current_reconciles = math.isclose(
        current_resources_total - current_liabilities,
        current_net,
        abs_tol=0.5,
    )
    previous_reconciles = math.isclose(
        previous_resources_total - previous_liabilities,
        previous_net,
        abs_tol=0.5,
    )
    current_balance_sheet_reconciles = math.isclose(
        current_total_assets - current_total_liabilities,
        current_net_assets,
        abs_tol=0.5,
    )
    previous_balance_sheet_reconciles = math.isclose(
        previous_total_assets - previous_total_liabilities,
        previous_net_assets,
        abs_tol=0.5,
    )
    if (
        not current_reconciles
        or not previous_reconciles
        or not current_balance_sheet_reconciles
        or not previous_balance_sheet_reconciles
    ):
        return None

    unit = next((line for line in lines if UNIT_PATTERN.fullmatch(line)), "")
    return {
        "current_assets_subtotal": current_assets_subtotal,
        "previous_assets_subtotal": previous_assets_subtotal,
        "current_assets_held_for_sale": (
            current_resources_total - current_assets_subtotal
        ),
        "previous_assets_held_for_sale": (
            previous_resources_total - previous_assets_subtotal
        ),
        "current_resources": current_resources_total,
        "previous_resources": previous_resources_total,
        "current_liabilities": current_liabilities,
        "previous_liabilities": previous_liabilities,
        "current_net_current_liabilities": current_net,
        "previous_net_current_liabilities": previous_net,
        "current_noncurrent_assets": current_noncurrent_assets,
        "previous_noncurrent_assets": previous_noncurrent_assets,
        "current_total_assets": current_total_assets,
        "previous_total_assets": previous_total_assets,
        "current_noncurrent_liabilities": current_noncurrent_liabilities,
        "previous_noncurrent_liabilities": previous_noncurrent_liabilities,
        "current_total_liabilities": current_total_liabilities,
        "previous_total_liabilities": previous_total_liabilities,
        "current_net_assets": current_net_assets,
        "previous_net_assets": previous_net_assets,
        "unit": unit,
        "page_number": page_number,
    }


def find_balance_sheet_figures(
    pages: Iterable[tuple[int, str]],
) -> BalanceSheetFigures | None:
    """Scan report pages and return the first reconciled group balance sheet."""
    for page_number, page_text in pages:
        figures = extract_balance_sheet_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures

    return None
