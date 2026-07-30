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
    statement_format: str


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:[-−－—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
CHINESE_UNIT_PATTERN = re.compile(
    r"单位[:：](?:人民币)?(元|千元|万元|百万元)"
)
CHINESE_CURRENT_ASSETS_LABELS = ("流动资产合计",)
CHINESE_NONCURRENT_ASSETS_LABELS = ("非流动资产合计",)
CHINESE_TOTAL_ASSETS_LABELS = ("资产总计",)
CHINESE_CURRENT_LIABILITIES_LABELS = ("流动负债合计",)
CHINESE_NONCURRENT_LIABILITIES_LABELS = ("非流动负债合计",)
CHINESE_TOTAL_LIABILITIES_LABELS = ("负债合计",)
CHINESE_TOTAL_EQUITY_LABELS = (
    "所有者权益（或股东权益）合计",
    "所有者权益(或股东权益)合计",
    "所有者权益合计",
    "股东权益合计",
)


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    return [
        " ".join(line.replace("\xa0", " ").split())
        for line in page_text.splitlines()
        if line.strip()
    ]


def _parse_financial_value(value: str) -> float:
    """Convert values such as '8,483' and '(14,329)' into numbers."""
    normalised = (
        value.replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
        .replace("−", "-")
        .replace("－", "-")
    )
    if normalised in {"-", "—", "–"}:
        return 0.0

    is_negative = normalised.startswith("(") and normalised.endswith(")")
    cleaned_value = normalised.strip("()").replace(",", "")
    number = float(cleaned_value)
    if is_negative and number > 0:
        return -number
    return number


def _compact_chinese_text(value: str) -> str:
    """Remove PDF spacing differences without translating statement labels."""
    return re.sub(r"\s+", "", value).replace(":", "：")


def _chinese_label_matches(line: str, label: str) -> bool:
    """Match an exact Chinese row label or the label followed by values."""
    compact_line = _compact_chinese_text(line)
    compact_label = _compact_chinese_text(label)
    if compact_line == compact_label:
        return True
    if not compact_line.startswith(compact_label):
        return False

    remainder = compact_line[len(compact_label) :]
    return remainder.startswith(
        ("：", "（", "(", "-", "−", "－")
    ) or bool(re.match(r"^\d", remainder))


def _financial_values_in_line(line: str) -> list[float]:
    """Read standalone financial tokens from one extracted PDF line."""
    return [
        _parse_financial_value(token)
        for token in line.split()
        if FINANCIAL_VALUE_PATTERN.fullmatch(token)
    ]


def _extract_chinese_row_pair(
    lines: list[str],
    labels: tuple[str, ...],
) -> tuple[float, float] | None:
    """Return current and prior-year values from a common A-share row."""
    for label in labels:
        for row_index, line in enumerate(lines):
            if not _chinese_label_matches(line, label):
                continue

            same_line_values = _financial_values_in_line(line)
            if len(same_line_values) >= 2:
                return same_line_values[-2], same_line_values[-1]

            following_values: list[float] = []
            for following_line in lines[row_index + 1 : row_index + 7]:
                values = _financial_values_in_line(following_line)
                if values:
                    following_values.extend(values)
                    continue
                if following_values:
                    break
            if len(following_values) >= 2:
                return following_values[-2], following_values[-1]
    return None


def _extract_unit(lines: list[str]) -> str:
    """Read a supported English or Chinese statement unit."""
    english_unit = next(
        (line for line in lines if UNIT_PATTERN.fullmatch(line)),
        "",
    )
    if english_unit:
        return english_unit

    for line in lines:
        compact_line = _compact_chinese_text(line)
        match = CHINESE_UNIT_PATTERN.search(compact_line)
        if match is None:
            continue
        unit = match.group(1)
        return f"人民币{unit}" if "人民币" in compact_line else unit
    return ""


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


def _extract_chinese_balance_sheet_figures(
    page_number: int,
    lines: list[str],
) -> BalanceSheetFigures | None:
    """Extract a common A-share consolidated balance sheet and reconcile it."""
    current_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_CURRENT_ASSETS_LABELS,
    )
    noncurrent_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_NONCURRENT_ASSETS_LABELS,
    )
    reported_total_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_ASSETS_LABELS,
    )
    current_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_CURRENT_LIABILITIES_LABELS,
    )
    noncurrent_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_NONCURRENT_LIABILITIES_LABELS,
    )
    reported_total_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_LIABILITIES_LABELS,
    )
    reported_total_equity = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_EQUITY_LABELS,
    )
    extracted_rows = (
        current_assets,
        noncurrent_assets,
        reported_total_assets,
        current_liabilities,
        noncurrent_liabilities,
        reported_total_liabilities,
        reported_total_equity,
    )
    if any(row is None for row in extracted_rows):
        return None

    assert current_assets is not None
    assert noncurrent_assets is not None
    assert reported_total_assets is not None
    assert current_liabilities is not None
    assert noncurrent_liabilities is not None
    assert reported_total_liabilities is not None
    assert reported_total_equity is not None

    current_assets_total, previous_assets_total = current_assets
    current_noncurrent_assets, previous_noncurrent_assets = noncurrent_assets
    current_total_assets, previous_total_assets = reported_total_assets
    current_current_liabilities, previous_current_liabilities = (
        current_liabilities
    )
    (
        current_noncurrent_liabilities,
        previous_noncurrent_liabilities,
    ) = noncurrent_liabilities
    current_total_liabilities, previous_total_liabilities = (
        reported_total_liabilities
    )
    current_total_equity, previous_total_equity = reported_total_equity

    reconciliations = (
        math.isclose(
            current_assets_total + current_noncurrent_assets,
            current_total_assets,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
        math.isclose(
            previous_assets_total + previous_noncurrent_assets,
            previous_total_assets,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
        math.isclose(
            current_current_liabilities + current_noncurrent_liabilities,
            current_total_liabilities,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
        math.isclose(
            previous_current_liabilities + previous_noncurrent_liabilities,
            previous_total_liabilities,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
        math.isclose(
            current_total_assets - current_total_liabilities,
            current_total_equity,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
        math.isclose(
            previous_total_assets - previous_total_liabilities,
            previous_total_equity,
            rel_tol=0.0,
            abs_tol=0.5,
        ),
    )
    if not all(reconciliations):
        return None

    return {
        "current_assets_subtotal": current_assets_total,
        "previous_assets_subtotal": previous_assets_total,
        "current_assets_held_for_sale": 0.0,
        "previous_assets_held_for_sale": 0.0,
        "current_resources": current_assets_total,
        "previous_resources": previous_assets_total,
        "current_liabilities": current_current_liabilities,
        "previous_liabilities": previous_current_liabilities,
        "current_net_current_liabilities": (
            current_assets_total - current_current_liabilities
        ),
        "previous_net_current_liabilities": (
            previous_assets_total - previous_current_liabilities
        ),
        "current_noncurrent_assets": current_noncurrent_assets,
        "previous_noncurrent_assets": previous_noncurrent_assets,
        "current_total_assets": current_total_assets,
        "previous_total_assets": previous_total_assets,
        "current_noncurrent_liabilities": current_noncurrent_liabilities,
        "previous_noncurrent_liabilities": previous_noncurrent_liabilities,
        "current_total_liabilities": current_total_liabilities,
        "previous_total_liabilities": previous_total_liabilities,
        "current_net_assets": current_total_equity,
        "previous_net_assets": previous_total_equity,
        "unit": _extract_unit(lines),
        "page_number": page_number,
        "statement_format": "chinese_a_share",
    }


def extract_balance_sheet_figures(
    page_number: int,
    page_text: str,
) -> BalanceSheetFigures | None:
    """Extract current resources and liabilities only when totals reconcile."""
    lines = _normalise_lines(page_text)
    if any("合并资产负债表" in line for line in lines):
        return _extract_chinese_balance_sheet_figures(page_number, lines)
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
        rel_tol=0.0,
        abs_tol=0.5,
    )
    previous_reconciles = math.isclose(
        previous_resources_total - previous_liabilities,
        previous_net,
        rel_tol=0.0,
        abs_tol=0.5,
    )
    current_balance_sheet_reconciles = math.isclose(
        current_total_assets - current_total_liabilities,
        current_net_assets,
        rel_tol=0.0,
        abs_tol=0.5,
    )
    previous_balance_sheet_reconciles = math.isclose(
        previous_total_assets - previous_total_liabilities,
        previous_net_assets,
        rel_tol=0.0,
        abs_tol=0.5,
    )
    if (
        not current_reconciles
        or not previous_reconciles
        or not current_balance_sheet_reconciles
        or not previous_balance_sheet_reconciles
    ):
        return None

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
        "unit": _extract_unit(lines),
        "page_number": page_number,
        "statement_format": "tesco_group",
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
