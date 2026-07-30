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
    return [
        " ".join(line.replace("\xa0", " ").split())
        for line in page_text.splitlines()
        if line.strip()
    ]


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
        "statement_format": statement_format,
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
