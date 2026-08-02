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
    end_page_number: int
    statement_format: str


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:[-−－—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
CHINESE_UNIT_PATTERN = re.compile(
    r"(?:金额)?单位(?:[:：]|为)(?:人民币)?(元|千元|万元|百万元)"
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
    lines: list[str] = []
    for raw_line in page_text.splitlines():
        line = " ".join(raw_line.replace("\xa0", " ").split())
        if not line or re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        if (
            line.endswith("年度报告")
            and "合并资产负债表" not in line
        ):
            continue
        lines.append(line)
    return lines


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
    candidates = (
        compact_line,
        re.sub(
            r"^(?:\d+[.．、]|[一二三四五六七八九十]+[、.．])",
            "",
            compact_line,
            count=1,
        ),
    )
    for candidate in candidates:
        if candidate == compact_label:
            return True
        if not candidate.startswith(compact_label):
            continue
        remainder = candidate[len(compact_label) :]
        if remainder.startswith(
            ("：", "（", "(", "-", "−", "－")
        ) or bool(re.match(r"^\d", remainder)):
            return True
    return False


def _chinese_label_span(
    lines: list[str],
    row_index: int,
    label: str,
) -> int | None:
    """Return the last line of a label split across up to three PDF lines."""
    combined = ""
    for end_index in range(row_index, min(row_index + 3, len(lines))):
        combined += _compact_chinese_text(lines[end_index])
        if _chinese_label_matches(combined, label):
            return end_index
        compact_label = _compact_chinese_text(label)
        without_prefix = re.sub(
            r"^(?:\d+[.．、]|[一二三四五六七八九十]+[、.．])",
            "",
            combined,
            count=1,
        )
        if not (
            compact_label.startswith(combined)
            or compact_label.startswith(without_prefix)
        ):
            break
    return None


def _financial_values_in_line(line: str) -> list[float]:
    """Read standalone financial tokens from one extracted PDF line."""
    return [
        _parse_financial_value(token)
        for token in line.split()
        if FINANCIAL_VALUE_PATTERN.fullmatch(token)
    ]


def _is_financial_values_line(line: str) -> bool:
    """Return whether a continuation line contains only financial tokens."""
    tokens = line.split()
    return bool(tokens) and all(
        FINANCIAL_VALUE_PATTERN.fullmatch(token) for token in tokens
    )


def _extract_chinese_row_pair(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    value_column_count: int = 2,
) -> tuple[float, float] | None:
    """Return current and prior-year values from a common A-share row."""
    for label in labels:
        for row_index in range(len(lines)):
            label_end = _chinese_label_span(lines, row_index, label)
            if label_end is None:
                continue

            same_line_values: list[float] = []
            for label_line in lines[row_index : label_end + 1]:
                same_line_values.extend(_financial_values_in_line(label_line))
            if value_column_count == 4 and len(same_line_values) >= 4:
                current, previous, _, _ = same_line_values[-4:]
                return current, previous
            if value_column_count == 2 and len(same_line_values) >= 2:
                return same_line_values[-2], same_line_values[-1]

            following_values: list[float] = []
            for following_line in lines[label_end + 1 : label_end + 7]:
                if _is_financial_values_line(following_line):
                    following_values.extend(
                        _financial_values_in_line(following_line)
                    )
                    continue
                if following_values:
                    break
            if value_column_count == 4 and len(following_values) >= 4:
                current, previous, _, _ = following_values[-4:]
                return current, previous
            if value_column_count == 2 and len(following_values) >= 2:
                return following_values[-2], following_values[-1]
    return None


def _chinese_balance_sheet_column_count(lines: list[str]) -> int | None:
    """Identify consolidated-only and consolidated-plus-company statements."""
    compact_lines = [_compact_chinese_text(line) for line in lines]
    if any("合并及公司资产负债表" in line for line in compact_lines):
        return 4
    if any("合并资产负债表" in line for line in compact_lines):
        return 2
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
    *,
    value_column_count: int = 2,
) -> BalanceSheetFigures | None:
    """Extract a common A-share consolidated balance sheet and reconcile it."""
    current_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_CURRENT_ASSETS_LABELS,
        value_column_count=value_column_count,
    )
    noncurrent_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_NONCURRENT_ASSETS_LABELS,
        value_column_count=value_column_count,
    )
    reported_total_assets = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_ASSETS_LABELS,
        value_column_count=value_column_count,
    )
    current_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_CURRENT_LIABILITIES_LABELS,
        value_column_count=value_column_count,
    )
    noncurrent_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_NONCURRENT_LIABILITIES_LABELS,
        value_column_count=value_column_count,
    )
    reported_total_liabilities = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_LIABILITIES_LABELS,
        value_column_count=value_column_count,
    )
    reported_total_equity = _extract_chinese_row_pair(
        lines,
        CHINESE_TOTAL_EQUITY_LABELS,
        value_column_count=value_column_count,
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
        "end_page_number": page_number,
        "statement_format": "chinese_a_share",
    }


def extract_balance_sheet_figures(
    page_number: int,
    page_text: str,
) -> BalanceSheetFigures | None:
    """Extract current resources and liabilities only when totals reconcile."""
    lines = _normalise_lines(page_text)
    chinese_value_column_count = _chinese_balance_sheet_column_count(lines)
    if chinese_value_column_count is not None:
        return _extract_chinese_balance_sheet_figures(
            page_number,
            lines,
            value_column_count=chinese_value_column_count,
        )
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
        "end_page_number": page_number,
        "statement_format": "tesco_group",
    }


def find_balance_sheet_figures(
    pages: Iterable[tuple[int, str]],
) -> BalanceSheetFigures | None:
    """Scan report pages and return the first reconciled group balance sheet."""
    page_list = list(pages)
    for page_index, (page_number, page_text) in enumerate(page_list):
        figures = extract_balance_sheet_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures
        if _chinese_balance_sheet_column_count(
            _normalise_lines(page_text)
        ) is None:
            continue

        for window_size in range(2, 6):
            window = page_list[page_index : page_index + window_size]
            if len(window) < window_size:
                break
            figures = extract_balance_sheet_figures(
                page_number=page_number,
                page_text="\n".join(text for _, text in window),
            )
            if figures is not None:
                figures["end_page_number"] = window[-1][0]
                return figures

    return None
