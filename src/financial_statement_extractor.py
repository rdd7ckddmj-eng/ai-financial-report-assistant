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
    end_page_number: int
    current_period_weeks: int | None
    previous_period_weeks: int | None


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:[-−－—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
WEEKS_PATTERN = re.compile(r"^(\d+) weeks ended$", re.IGNORECASE)
CHINESE_UNIT_PATTERN = re.compile(
    r"单位[:：](?:人民币)?(元|千元|万元|百万元)"
)
CHINESE_REVENUE_LABELS = (
    "其中：营业收入",
    "营业收入",
    "一、营业总收入",
    "营业总收入",
)
CHINESE_NET_PROFIT_LABELS = (
    "归属于母公司股东的净利润",
    "归属于母公司所有者的净利润",
    "五、净利润",
    "净利润",
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
            and "合并利润表" not in line
        ):
            continue
        lines.append(line)
    return lines


def _parse_financial_value(value: str) -> float:
    """Convert PDF table values such as '1,787' or '(153)' into numbers."""
    normalised = (
        value.replace("，", ",")
        .replace("（", "(")
        .replace("）", ")")
        .replace("−", "-")
        .replace("－", "-")
    )
    if normalised in {"-", "—", "–"}:
        return 0.0

    is_parenthesised = normalised.startswith("(") and normalised.endswith(")")
    cleaned_value = normalised.strip("()").replace(",", "")
    number = float(cleaned_value)
    if is_parenthesised and number > 0:
        return -number
    return number


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


def _compact_chinese_text(value: str) -> str:
    """Remove spacing differences without translating statement labels."""
    return re.sub(r"\s+", "", value).replace(":", "：")


def _chinese_label_matches(line: str, label: str) -> bool:
    """Match an exact row label or the same label followed by values."""
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
            if len(same_line_values) >= 2:
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


def extract_income_statement_figures(
    page_number: int,
    page_text: str,
) -> IncomeStatementFigures | None:
    """Extract revenue and profit totals without guessing missing values."""
    lines = _normalise_lines(page_text)

    if "Group income statement" in lines:
        revenue_totals = _extract_six_column_totals(lines, "Revenue")
        profit_totals = _extract_six_column_totals(
            lines,
            "Profit/(loss) for the year",
        )
        current_period_weeks, previous_period_weeks = _extract_period_weeks(
            lines
        )
    elif any("合并利润表" in line for line in lines):
        revenue_totals = _extract_chinese_row_pair(
            lines,
            CHINESE_REVENUE_LABELS,
        )
        profit_totals = _extract_chinese_row_pair(
            lines,
            CHINESE_NET_PROFIT_LABELS,
        )
        current_period_weeks, previous_period_weeks = None, None
    else:
        return None

    if revenue_totals is None or profit_totals is None:
        return None

    unit = _extract_unit(lines)
    current_revenue, previous_revenue = revenue_totals
    current_net_profit, previous_net_profit = profit_totals

    return {
        "current_revenue": current_revenue,
        "previous_revenue": previous_revenue,
        "current_net_profit": current_net_profit,
        "previous_net_profit": previous_net_profit,
        "unit": unit,
        "page_number": page_number,
        "end_page_number": page_number,
        "current_period_weeks": current_period_weeks,
        "previous_period_weeks": previous_period_weeks,
    }


def find_income_statement_figures(
    pages: Iterable[tuple[int, str]],
) -> IncomeStatementFigures | None:
    """Scan report pages and return the first supported income statement."""
    page_list = list(pages)
    for page_index, (page_number, page_text) in enumerate(page_list):
        figures = extract_income_statement_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures
        if "合并利润表" not in page_text:
            continue

        for window_size in range(2, 4):
            window = page_list[page_index : page_index + window_size]
            if len(window) < window_size:
                break
            figures = extract_income_statement_figures(
                page_number=page_number,
                page_text="\n".join(text for _, text in window),
            )
            if figures is not None:
                figures["end_page_number"] = window[-1][0]
                return figures

    return None
