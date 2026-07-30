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
    end_page_number: int
    statement_format: str


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:[-−－—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
WEEKS_PATTERN = re.compile(r"^(\d+) weeks(?: ended)?$", re.IGNORECASE)
CHINESE_UNIT_PATTERN = re.compile(
    r"单位[:：](?:人民币)?(元|千元|万元|百万元)"
)
CHINESE_CASH_FLOW_LABELS = {
    "operating": (
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
    ),
    "investing": (
        "投资活动产生的现金流量净额",
        "投资活动现金流量净额",
    ),
    "financing": (
        "筹资活动产生的现金流量净额",
        "筹资活动现金流量净额",
    ),
    "net_change": (
        "五、现金及现金等价物净增加额",
        "现金及现金等价物净增加额",
    ),
    "opening": (
        "加：期初现金及现金等价物余额",
        "期初现金及现金等价物余额",
    ),
    "exchange": (
        "四、汇率变动对现金及现金等价物的影响",
        "汇率变动对现金及现金等价物的影响",
    ),
    "ending": (
        "六、期末现金及现金等价物余额",
        "期末现金及现金等价物余额",
    ),
}


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    lines: list[str] = []
    for raw_line in page_text.splitlines():
        line = " ".join(raw_line.replace("\xa0", " ").split())
        if not line or re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        if (
            line.endswith("年度报告")
            and "合并现金流量表" not in line
        ):
            continue
        lines.append(line)
    return lines


def _parse_financial_value(value: str) -> float:
    """Convert values such as '3,906' and '(706)' into numbers."""
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


def _cash_flow_rows_reconcile(
    extracted_rows: dict[str, tuple[float, float] | None],
    *,
    net_change_includes_exchange: bool,
) -> bool:
    """Verify cash-flow sections and opening-to-ending cash for both years."""
    if any(values is None for values in extracted_rows.values()):
        return False

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

    for period_index in (0, 1):
        section_total = (
            operating[period_index]
            + investing[period_index]
            + financing[period_index]
        )
        ending_cash = opening[period_index] + net_change[period_index]
        if net_change_includes_exchange:
            section_total += exchange[period_index]
        else:
            ending_cash += exchange[period_index]

        if not math.isclose(
            section_total,
            net_change[period_index],
            rel_tol=0.0,
            abs_tol=0.5,
        ):
            return False
        if not math.isclose(
            ending_cash,
            ending[period_index],
            rel_tol=0.0,
            abs_tol=0.5,
        ):
            return False
    return True


def extract_cash_flow_figures(
    page_number: int,
    page_text: str,
) -> CashFlowFigures | None:
    """Extract cash-flow totals only when both cash reconciliations pass."""
    lines = _normalise_lines(page_text)
    if any("合并现金流量表" in line for line in lines):
        extracted_rows = {
            name: _extract_chinese_row_pair(lines, labels)
            for name, labels in CHINESE_CASH_FLOW_LABELS.items()
        }
        net_change_includes_exchange = True
        statement_format = "chinese_a_share"
    elif "Group cash flow statement" in lines:
        row_labels = {
            "operating": (
                "Net cash generated from/(used in) operating activities"
            ),
            "investing": (
                "Net cash generated from/(used in) investing activities"
            ),
            "financing": (
                "Net cash generated from/(used in) financing activities"
            ),
            "net_change": (
                "Net increase/(decrease) in cash and cash equivalents"
            ),
            "opening": "Cash and cash equivalents at the beginning of the year",
            "exchange": "Effect of foreign exchange rate changes",
            "ending": "Cash and cash equivalents at the end of the year",
        }
        extracted_rows = {
            name: _extract_row_pair(lines, label)
            for name, label in row_labels.items()
        }
        net_change_includes_exchange = False
        statement_format = "tesco_group"
    else:
        return None

    if not _cash_flow_rows_reconcile(
        extracted_rows,
        net_change_includes_exchange=net_change_includes_exchange,
    ):
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

    current_weeks, previous_weeks = _extract_period_weeks(lines)
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
        "unit": _extract_unit(lines),
        "page_number": page_number,
        "end_page_number": page_number,
        "statement_format": statement_format,
    }


def find_cash_flow_figures(
    pages: Iterable[tuple[int, str]],
) -> CashFlowFigures | None:
    """Scan report pages and return the first reconciled cash-flow statement."""
    page_list = list(pages)
    for page_index, (page_number, page_text) in enumerate(page_list):
        figures = extract_cash_flow_figures(
            page_number=page_number,
            page_text=page_text,
        )
        if figures is not None:
            return figures
        if "合并现金流量表" not in page_text:
            continue

        for window_size in range(2, 5):
            window = page_list[page_index : page_index + window_size]
            if len(window) < window_size:
                break
            figures = extract_cash_flow_figures(
                page_number=page_number,
                page_text="\n".join(text for _, text in window),
            )
            if figures is not None:
                figures["end_page_number"] = window[-1][0]
                return figures

    return None
