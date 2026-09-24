"""Deterministic extraction and reconciliation of cash-flow figures."""

import math
import re
from src.pdf_numeric_text import normalize_numeric_parentheses
from src.statement_evidence_rules import integer_rounding_tolerance, extract_statement_unit, bound_consolidated_statement
from src.statement_page_layout_recovery import recover_printed_statement_page_numbers
from collections.abc import Iterable
from typing import NotRequired, TypedDict


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
    layout_recoveries: NotRequired[list[dict]]


FINANCIAL_VALUE_PATTERN = re.compile(
    r"^(?:[-−－—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$"
)
UNIT_PATTERN = re.compile(r"^[£$€](?:k|m|bn)?$", re.IGNORECASE)
WEEKS_PATTERN = re.compile(r"^(\d+) weeks(?: ended)?$", re.IGNORECASE)
CHINESE_UNIT_PATTERN = re.compile(
    r"(?:金额)?单位(?:[:：]|为)(?:人民币)?(元|千元|万元|百万元)"
)
CHINESE_CASH_FLOW_LABELS = {
    "operating": (
        "经营活动产生/(使用)的现金流量净额",
        "经营活动产生/（使用）的现金流量净额",
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
    ),
    "investing": (
        "投资活动（使用）/产生的现金流量净额",
        "投资活动(使用)/产生的现金流量净额",
        "投资活动产生/(使用)的现金流量净额",
        "投资活动产生/（使用）的现金流量净额",
        "投资活动使用的现金流量净额",
        "投资活动产生的现金流量净额",
        "投资活动现金流量净额",
    ),
    "financing": (
        "筹资活动(使用)产生的现金流量净额",
        "筹资活动（使用）产生的现金流量净额",
        "筹资活动(使用)/产生的现金流量净额",
        "筹资活动（使用）/产生的现金流量净额",
        "筹资活动产生/(使用)的现金流量净额",
        "筹资活动产生/（使用）的现金流量净额",
        "筹资活动使用的现金流量净额",
        "筹资活动产生的现金流量净额",
        "筹资活动现金流量净额",
    ),
    "net_change": (
        "五、现金及现金等价物净增加(减少)额",
        "五、现金及现金等价物净增加/(减少)额",
        "五、现金及现金等价物净增加/（减少）额",
        "五、现金及现金等价物净(减少)/增加额",
        "五、现金及现金等价物净（减少）/增加额",
        "五、现金及现金等价物净增加额",
        "现金及现金等价物净增加额",
        "五、现金及现金等价物净减少额",
        "现金及现金等价物净减少额",
    ),
    "opening": (
        "加：年初现金及现金等价物余额",
        "年初现金及现金等价物余额",
        "加：期初现金及现金等价物余额",
        "期初现金及现金等价物余额",
    ),
    "exchange": (
        "四、汇率变动对现金及现金等价物的影响额",
        "四、汇率变动对现金及现金等价物的影响",
        "汇率变动对现金及现金等价物的影响",
    ),
    "ending": (
        "六、年末现金及现金等价物余额",
        "年末现金及现金等价物余额",
        "六、期末现金及现金等价物余额",
        "期末现金及现金等价物余额",
    ),
}


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    lines: list[str] = []
    for raw_line in normalize_numeric_parentheses(page_text).splitlines():
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
        ) or bool(re.match(r"^\d", remainder)) or bool(
            re.match(
                r"^(?:附注)?[一二三四五六七八九十百]+[（(]",
                remainder,
            )
        ):
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


def _has_recovery_header(lines: list[str]) -> bool:
    """Require an explicit note column and ordered two-year columns."""
    # These layout recoveries do not apply to combined group/company tables.
    if _chinese_cash_flow_column_count(lines) != 2:
        return False
    start = next((i for i, line in enumerate(lines)
                  if _compact_chinese_text(line).startswith("项目")), None)
    if start is None:
        return False
    header = ""
    for line in lines[start:start + 6]:
        compact = _compact_chinese_text(line)
        if "经营活动" in compact:
            break
        header += compact
    match = re.fullmatch(r"项目附注(\d{4})年度?(\d{4})年度?", header)
    return bool(match and int(match[1]) == int(match[2]) + 1)


def _has_named_period_note_header(lines: list[str]) -> bool:
    """Recognise the existing Hikvision note column, without new recoveries."""
    if _chinese_cash_flow_column_count(lines) != 2:
        return False
    header = ""
    for index, line in enumerate(lines):
        if not _compact_chinese_text(line).startswith("项目"):
            continue
        for part in lines[index:index + 6]:
            if "经营活动" in part:
                break
            header += _compact_chinese_text(part)
        break
    return header == "项目附注本年发生额上年发生额"


def _has_explicit_standalone_note_header(lines: list[str]) -> bool:
    """Allow one complete note cell under observed, unambiguous headers.

    This does not enable the two-column interleaved-label recovery. Combined
    group/company statements must also declare all four ordered column roles.
    """
    if _has_named_period_note_header(lines):
        return True
    columns = _chinese_cash_flow_column_count(lines)
    compact = [_compact_chinese_text(line).replace('（', '(').replace('）', ')')
               for line in lines]
    end = next((i for i, line in enumerate(compact)
                if re.fullmatch(r'一、经营活动产生(?:/\(使用\))?的现金流量[：:]?', line)), None)
    if end is None:
        return False
    start = next((i for i, line in enumerate(compact[:end])
                  if line.startswith('项目') or line == '项' or line == '附注'), None)
    if start is None:
        return False
    header = ''.join(compact[start:end])
    if columns == 2:
        match = re.fullmatch(r'(?:项目)?附注(\d{4})年度?(\d{4})年度?'
                             r'(?:\((?:已)?重述\))?', header)
        return bool(match and int(match[1]) == int(match[2]) + 1)
    if columns != 4:
        return False
    match = re.fullmatch(r'项目附注(\d{4})年度(\d{4})年度(\d{4})年度(\d{4})年度'
                         r'合并合并公司公司', header)
    if match is None:
        match = re.fullmatch(r'项目附注(\d{4})年度合并(\d{4})年度合并'
                             r'(\d{4})年度母公司(\d{4})年度母公司', header)
    return bool(match and [int(year) for year in match.groups()]
                == [int(match[1]), int(match[1]) - 1] * 2)


def _qualified_note_style(lines: list[str]) -> str | None:
    """Recognise two observed note-column headers before the first cash row."""
    end = next((i for i, line in enumerate(lines) if re.fullmatch(
        r'一、经营活动产生的现金流量[：:]?', _compact_chinese_text(line))), None)
    if end is None or _chinese_cash_flow_column_count(lines) != 2:
        return None
    compact = [_compact_chinese_text(line) for line in lines[:end]]
    start = next((i for i, line in enumerate(compact)
                  if line in {'项', '项目'} or line.startswith('附注')), None)
    if start is None:
        return None
    header = ''.join(compact[start:])
    numbered = re.fullmatch(r'附注[一二三四五六七八九十]+(20\d{2})年(20\d{2})年', header)
    if numbered and int(numbered[1]) == int(numbered[2]) + 1:
        return 'numbered_note_column'
    if header == '项目附注本期发生额上期发生额':
        return 'chinese_ordinal_note_column'
    return None


def _strict_recovery_values(line: str) -> list[float] | None:
    """New recovery paths require complete, bounded financial cells."""
    amount = r"(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?"
    cell = re.compile(rf"^(?:[-−－—–]|[-−－]?{amount}|\({amount}\)|（{amount}）)$")
    tokens = line.split()
    if not tokens or any(len(t) > 64 or not cell.fullmatch(t) for t in tokens):
        return None
    values = [_parse_financial_value(t) for t in tokens]
    return values if all(math.isfinite(v) and abs(v) <= 1e24 for v in values) else None


def _joined_note_values(line: str) -> list[float] | None:
    """Read a Chinese note followed by amounts without inserting digits."""
    note = re.match(r"^(?:附注)?[一二三四五六七八九十百]+、"
                    r"[（(][一二三四五六七八九十百]+[）)]", line)
    if note is None:
        return None
    tail = line[note.end():].strip()
    if not tail:
        return []
    return _strict_recovery_values(tail)


def _invalid_numeric_boundary(line: str) -> bool:
    """Do not treat corrupted or unavailable amounts as a new text row."""
    compact = _compact_chinese_text(line)
    return bool(re.fullmatch(r"(?:无数据|不适用|N/?A|NAN|NULL|NONE|[+-]?INF(?:INITY)?)",
                            compact, re.IGNORECASE)
                or (re.match(r"^[+\-−－—–(（.,\d]", compact)
                    and re.search(r"\d", compact)
                    and not re.search(r"[\u4e00-\u9fff]", compact)))


def _standalone_note(line: str) -> bool:
    compact = _compact_chinese_text(line)
    # Called only under an explicit note + two-period column header. Existing
    # originals also print 七79 and 七、79（4）; these are whole note cells,
    # not permission to skip arbitrary Chinese text before the amounts.
    return bool(re.fullmatch(r"(?:附注)?(?:[一二三四五六七八九十百]+、?[1-9]\d{0,2}"
        r"(?:[（(][A-Za-z0-9]{1,8}[）)])*"
        r"|[一二三四五六七八九十百]+(?:[（(][A-Za-z0-9]+[）)])+"
        r"|[一二三四五六七八九十百]+、[1-9]\d{0,2}[（(][1-9]\d?[）)][a-z])", compact))


def _interleaved_label_pair(lines, row_index, label):
    """Accept only exact label-prefix, two amounts, then exact label-tail."""
    prefix = _compact_chinese_text(lines[row_index])
    target = _compact_chinese_text(label)
    if len(prefix) < 6 or prefix == target or not target.startswith(prefix):
        return None
    values = []
    for end in range(row_index + 1, min(row_index + 5, len(lines))):
        line = lines[end]
        if _is_financial_values_line(line):
            cells = _strict_recovery_values(line)
            if cells is None:
                return None
            values.extend(cells)
            if len(values) > 2:
                return None
            continue
        # No unrelated account, missing suffix, reversed label, or extra cell
        # may be skipped in order to reach a convenient pair of amounts.
        if len(values) != 2 or prefix + _compact_chinese_text(line) != target:
            return None
        if end + 1 < len(lines) and (_is_financial_values_line(lines[end + 1])
                                     or _invalid_numeric_boundary(lines[end + 1])):
            return None
        return (values[0], values[1]), end
    return None


def _recovery_original_spans(recoveries, source_pages):
    """Attach exact original text and physical pages; reject ambiguous spans."""
    records = []
    for page, text in source_pages:
        offset = 0
        for raw in text.splitlines(keepends=True):
            normalized = _normalise_lines(raw)
            if normalized:
                records.append((normalized[0], page, offset, offset + len(raw)))
            offset += len(raw)
    by_page = dict(source_pages)
    for recovery in recoveries:
        wanted = recovery.pop("normalized_lines")
        matches = [i for i in range(len(records) - len(wanted) + 1)
                   if [r[0] for r in records[i:i + len(wanted)]] == wanted]
        if len(matches) != 1:
            return False
        selected = records[matches[0]:matches[0] + len(wanted)]
        parts = []
        for page in dict.fromkeys(r[1] for r in selected):
            rows = [r for r in selected if r[1] == page]
            parts.append({"page_number": page,
                          "original_text": by_page[page][rows[0][2]:rows[-1][3]]})
        recovery["source_spans"] = parts
    return True


def _extract_chinese_row_pair(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    value_column_count: int = 2,
    recoveries: list | None = None,
    strict_values: bool = False,
) -> tuple[float, float] | None:
    """Return current and prior-year values from a common A-share row."""
    recovery_header = _has_recovery_header(lines)
    standalone_note_header = _has_explicit_standalone_note_header(lines)
    qualified_note_style = _qualified_note_style(lines)
    strict_values = strict_values or bool(qualified_note_style)
    if recovery_header or strict_values or standalone_note_header:
        starts = set()
        for index, line in enumerate(lines):
            compact = _compact_chinese_text(line)
            if any(_chinese_label_span(lines, index, label) is not None
                   or (len(compact) >= 6 and _compact_chinese_text(label).startswith(compact))
                   for label in labels):
                starts.add(index)
        if len(starts) != 1:
            return None
    for label in labels:
        for row_index in range(len(lines)):
            label_end = _chinese_label_span(lines, row_index, label)
            if label_end is None:
                if recovery_header:
                    recovered = _interleaved_label_pair(lines, row_index, label)
                    if recovered is not None:
                        pair, end = recovered
                        if recoveries is not None:
                            recoveries.append(dict(kind="amounts_inside_wrapped_label", label=label,
                                normalized_lines=lines[row_index:end + 1]))
                        return pair
                continue

            same_line_values: list[float] = []
            for label_line in lines[row_index : label_end + 1]:
                same_line_values.extend(_financial_values_in_line(label_line))
            if strict_values:
                # Footer removal must not leave the legacy "take last two"
                # fallback free to discard an extra monetary cell.
                merged = ' '.join(lines[row_index:label_end + 1])
                pattern = ''.join(re.escape(char) + r'\s*' for char in label)
                match = re.match(pattern, merged)
                if match is None:
                    merged = re.sub(r'^(?:\d+[.．、]|[一二三四五六七八九十百]+[、.．])\s*', '', merged)
                    match = re.match(pattern, merged)
                if match is None:
                    return None
                tail = merged[match.end():].strip()
                same_line_values = _strict_recovery_values(tail) if tail else []
                if same_line_values is None:
                    return None
            if not strict_values and value_column_count == 4 and len(same_line_values) >= 4:
                current, previous, _, _ = same_line_values[-4:]
                return current, previous
            if not strict_values and value_column_count == 2 and len(same_line_values) >= 2:
                return same_line_values[-2], same_line_values[-1]

            following_values: list[float] = same_line_values if strict_values else []
            note_recovery = False
            sign_caption_recovery = False
            standalone_notes = 0
            lettered_note_recovery = False
            qualified_note_recovery = False
            last = label_end
            following_lines = lines[label_end + 1:] if strict_values else lines[label_end + 1:label_end + 7]
            for last, following_line in enumerate(following_lines, label_end + 1):
                if (qualified_note_style and last == label_end + 1 and not following_values):
                    note_cell = _compact_chinese_text(following_line)
                    valid_note = (bool(re.fullmatch(r'[1-9]\d{0,2}', note_cell))
                        if qualified_note_style == 'numbered_note_column' else
                        bool(re.fullmatch(r'[一二三四五六七八九十]+、[（(][一二三四五六七八九十百]+[）)]', note_cell)))
                    if valid_note:
                        qualified_note_recovery = True
                        continue
                if _is_financial_values_line(following_line):
                    if (strict_values or note_recovery or sign_caption_recovery or standalone_notes) and _strict_recovery_values(following_line) is None:
                        return None
                    following_values.extend(
                        _financial_values_in_line(following_line)
                    )
                    continue
                if (recovery_header and last == label_end + 1
                    and label in CHINESE_CASH_FLOW_LABELS['net_change']
                    and re.fullmatch(r'[（(]净减少以[“"\'][-－−][”"\']号填列[）)]',
                                     _compact_chinese_text(following_line))):
                    # This is the sign convention printed below the same row,
                    # not a new account or permission to skip arbitrary text.
                    sign_caption_recovery = True
                    continue
                if recovery_header and not following_values:
                    noted = _joined_note_values(following_line)
                    if noted is not None:
                        following_values.extend(noted)
                        note_recovery = True
                        continue
                if (standalone_note_header and value_column_count == 2
                    and last == label_end + 1 and not following_values):
                    # One whole note cell may share a line with its amount.
                    # A real whitespace boundary is required; do not split or
                    # invent a number inside an unrecognised note string.
                    adjacent = re.fullmatch(
                        r'((?:附注)?[一二三四五六七八九十百]+、[1-9]\d{0,2}'
                        r'(?:[（(][A-Za-z0-9]+[）)])*)\s+(.+)', following_line)
                    if adjacent and _standalone_note(adjacent[1]):
                        noted = _strict_recovery_values(adjacent[2])
                        if noted is None:
                            return None
                        following_values.extend(noted)
                        note_recovery = True
                        continue
                if (recovery_header or strict_values or standalone_notes or note_recovery) and _invalid_numeric_boundary(following_line):
                    return None
                if following_values:
                    break
                if qualified_note_recovery:
                    # The qualified column has already consumed its one note.
                    # It may not also use a legacy note-skipping path.
                    return None
                if note_recovery:
                    break
                if recovery_header or strict_values or standalone_note_header:
                    parenthesized_note = bool((strict_values or standalone_note_header) and re.fullmatch(
                        r'[（(][一二三四五六七八九十百]+[）)][1-9]\d{0,2}(?:[（(][A-Za-z0-9]+[）)])*',
                        _compact_chinese_text(following_line)))
                    if _standalone_note(following_line) or parenthesized_note:
                        standalone_notes += 1
                        if (strict_values or standalone_note_header) and standalone_notes > 1:
                            return None
                        lettered_note_recovery = bool(re.fullmatch(
                            r'[一二三四五六七八九十百]+、[1-9]\d{0,2}[（(][1-9]\d?[）)][a-z]',
                            _compact_chinese_text(following_line)))
                        continue
                # Any unrecognised text ends this row, including in tables
                # without an explicit note column. A blank amount must not
                # borrow a later account's cells merely because they reconcile.
                break
            if strict_values and len(following_values) != value_column_count:
                return None
            if qualified_note_recovery and recoveries is not None:
                end = last if _is_financial_values_line(lines[last]) else last - 1
                recoveries.append(dict(kind=qualified_note_style, label=label,
                    normalized_lines=lines[row_index:end + 1]))
            if standalone_notes and len(following_values) != value_column_count:
                return None
            if lettered_note_recovery and recoveries is not None:
                end = last if _is_financial_values_line(lines[last]) else last - 1
                recoveries.append(dict(kind='lettered_statement_note', label=label,
                    normalized_lines=lines[row_index:end + 1]))
            if note_recovery or sign_caption_recovery:
                # A newly recognised note must leave exactly two cells. Never
                # select the last two from an ambiguous three-cell row.
                if len(following_values) != 2:
                    return None
                if recoveries is not None:
                    end = last if _is_financial_values_line(lines[last]) else last - 1
                    recoveries.append(dict(kind=("wrapped_net_change_sign_caption" if sign_caption_recovery
                                                 else "chinese_note_adjacent_to_amount"), label=label,
                        normalized_lines=lines[row_index:end + 1]))
                return following_values[0], following_values[1]
            if strict_values:
                return following_values[0], following_values[1]
            if value_column_count == 4 and len(following_values) >= 4:
                current, previous, _, _ = following_values[-4:]
                return current, previous
            if value_column_count == 2 and len(following_values) >= 2:
                return following_values[-2], following_values[-1]
    return None


def _chinese_cash_flow_column_count(lines: list[str]) -> int | None:
    """Identify consolidated-only and consolidated-plus-company statements."""
    compact_lines = [_compact_chinese_text(line) for line in lines]
    if any("合并及公司现金流量表" in line for line in compact_lines):
        return 4
    if any("合并现金流量表" in line for line in compact_lines):
        return 2
    return None


def _extract_unit(lines: list[str]) -> str:
    """Read a declared unit, rejecting conflicting currency/scale headers."""
    return extract_statement_unit(lines)


def _bounded_cash_flow_text(page_text: str) -> str:
    text = bound_consolidated_statement(page_text, "现金流量表")
    # Some issuers number the independent parent table as “（六）母公司…”.
    # Stop before that title as well; a repeated cash total there is not a
    # second group row and may never repair missing consolidated evidence.
    parent = re.search(r"(?m)^[ \t]*(?:(?:[（(][一二三四五六七八九十百0-9]+[）)]"
                       r"|[一二三四五六七八九十百0-9]+[、.．])[ \t]*)?"
                       r"(?:母\s*公\s*司|公\s*司)\s*现金流量表"
                       r"\s*(?:[（(]续[）)])?[ \t]*$", text)
    return text[:parent.start()] if parent else text


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
    tolerance: float = 0.5,
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
            abs_tol=tolerance,
        ):
            return False
        if not math.isclose(
            ending_cash,
            ending[period_index],
            rel_tol=0.0,
            abs_tol=tolerance,
        ):
            return False
    return True


def extract_cash_flow_figures(
    page_number: int,
    page_text: str,
    *,
    source_pages: list[tuple[int, str]] | None = None,
) -> CashFlowFigures | None:
    """Extract cash-flow totals only when both cash reconciliations pass."""
    # A page footer is not a third financial cell. Only remove a standalone
    # final integer matching this physical page, separated by a blank line.
    original_pages = source_pages or [(page_number, page_text)]
    if source_pages is not None and "\n".join(t for _, t in source_pages) != page_text:
        return None
    page_recovery = recover_printed_statement_page_numbers(original_pages, "现金流量表")
    parser_pages = page_recovery[0] if page_recovery else original_pages
    clean_text = "\n".join(re.sub(
        rf'(?:\r?\n[ \t]*){{2,}}{number}[ \t]*(?:\r?\n[ \t]*)*\Z',
        '\n', text) for number, text in parser_pages)
    lines = _normalise_lines(_bounded_cash_flow_text(clean_text))
    chinese_value_column_count = _chinese_cash_flow_column_count(lines)
    recoveries = []
    if chinese_value_column_count is not None:
        extracted_rows = {
            name: _extract_chinese_row_pair(
                lines,
                labels,
                value_column_count=chinese_value_column_count,
                recoveries=recoveries,
                strict_values=clean_text != page_text,
            )
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

    tolerance = (integer_rounding_tolerance(_extract_unit(lines), list(extracted_rows.values()), lines)
                 if chinese_value_column_count is not None else 0.5)
    if not _cash_flow_rows_reconcile(
        extracted_rows,
        net_change_includes_exchange=net_change_includes_exchange,
        tolerance=tolerance,
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

    if recoveries and not _recovery_original_spans(recoveries, source_pages or [(page_number, page_text)]):
        return None
    if page_recovery:
        recoveries.append(page_recovery[1])
    current_weeks, previous_weeks = _extract_period_weeks(lines)
    figures = {
        "rounding_note": ("整数缩放单位勾稽：允许最多1个原始单位差异，仍待人工复核。" if tolerance == 1 else ""),
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
    if recoveries:
        figures["layout_recoveries"] = recoveries
    return figures


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
        if _chinese_cash_flow_column_count(
            _normalise_lines(page_text)
        ) is None:
            continue

        for window_size in range(2, 5):
            window = page_list[page_index : page_index + window_size]
            if len(window) < window_size or [p for p, _ in window] != list(range(page_number, page_number + window_size)):
                break
            figures = extract_cash_flow_figures(
                page_number=page_number,
                page_text="\n".join(text for _, text in window),
                source_pages=window,
            )
            if figures is not None:
                figures["end_page_number"] = window[-1][0]
                return figures

    return None
