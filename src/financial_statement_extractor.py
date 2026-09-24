"""Deterministic extraction of key figures from an income-statement page."""

import math
import re
from src.pdf_numeric_text import normalize_numeric_parentheses
from src.statement_evidence_rules import extract_statement_unit, bound_consolidated_statement
from src.income_row_layout_recovery import recover_cross_page_attributable_profit
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
    r"(?:金额)?单位(?:[:：]|为)(?:人民币)?(元|千元|万元|百万元)"
)
CHINESE_NOTE_REFERENCE_PATTERN = re.compile(
    r"^(?:附注)?(?:[一二三四五六七八九十百0-9]+"
    r"(?:[（(][A-Za-z0-9]+[）)])+(?:[,，、])?"
    r"|[一二三四五六七八九十百]+、[0-9]+"
    r"|(?:\([一二三四五六七八九十百]+\)|（[一二三四五六七八九十百]+）)[0-9]+(?:\([A-Za-z0-9]+\)|（[A-Za-z0-9]+）)*)$"
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
)
ORDINARY_SHAREHOLDER_PROFIT_LABEL = "归属于母公司普通股股东"


def _ordinary_shareholder_attribution_allowed(lines, index):
    """A short ownership label is profit only inside the net-profit section."""
    preceding = [_compact_chinese_text(line) for line in lines[:index]]
    marker = next((i for i in range(len(preceding) - 1, -1, -1)
                   if preceding[i] == '按所有权归属分类'), None)
    if marker is None or index - marker > 4:
        return False
    return (any(_chinese_label_matches(line, '净利润') for line in lines[:marker])
            and not any('综合收益' in line for line in preceding)
            and _compact_chinese_text(lines[index]) == ORDINARY_SHAREHOLDER_PROFIT_LABEL)


def _normalise_lines(page_text: str) -> list[str]:
    """Remove empty lines and normalise unusual PDF spacing."""
    lines: list[str] = []
    for raw_line in normalize_numeric_parentheses(page_text).splitlines():
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
            # A sign annotation can wrap after the label. Consume only this
            # exact annotation, never another account or an arbitrary parenthesis.
            annotation = re.search(r'[（(](?:净(?:亏损)?|亏损总额|亏损|损失)(?:以)?', combined)
            if annotation and not re.search(r'[）)]', combined[annotation.start():]):
                for extra in range(end_index + 1, min(end_index + 3, len(lines))):
                    tail = combined[annotation.start():] + ''.join(
                        _compact_chinese_text(t) for t in lines[end_index+1:extra+1])
                    if re.fullmatch(r'[（(](?:净亏损|亏损总额|亏损|损失)以[“"‘]?[-−－—–][”"’]?号填列[）)]', tail):
                        return extra
                return None
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


def _continuation_financial_values(line: str) -> list[float] | None:
    """Read values from a numeric line or a line prefixed only by a note."""
    tokens = line.split()
    values = _financial_values_in_line(line)
    if values and _is_financial_values_line(line):
        return values

    nonfinancial_tokens = [
        token
        for token in tokens
        if FINANCIAL_VALUE_PATTERN.fullmatch(token) is None
    ]
    compact_nonfinancial = _compact_chinese_text(
        "".join(nonfinancial_tokens)
    )
    if values and CHINESE_NOTE_REFERENCE_PATTERN.fullmatch(
        compact_nonfinancial
    ):
        return values
    if not values and CHINESE_NOTE_REFERENCE_PATTERN.fullmatch(
        compact_nonfinancial
    ):
        return []
    return None


def _select_chinese_period_pair(
    values: list[float],
    *,
    value_column_count: int,
) -> tuple[float, float] | None:
    """Select consolidated current/prior values from a supported table row."""
    if value_column_count == 4:
        if len(values) < 4:
            return None
        current, previous, _, _ = values[-4:]
        return current, previous
    if len(values) < 2:
        return None
    return values[-2], values[-1]


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
            same_line_pair = _select_chinese_period_pair(
                same_line_values,
                value_column_count=value_column_count,
            )
            if same_line_pair is not None:
                return same_line_pair

            following_values: list[float] = []
            for following_line in lines[label_end + 1 : label_end + 7]:
                continuation_values = _continuation_financial_values(
                    following_line
                )
                if continuation_values is not None:
                    following_values.extend(continuation_values)
                    continue
                # A wrapped sign convention still belongs to this row; only
                # this explicit annotation may precede the numeric cells.
                if not following_values and re.fullmatch(
                    r'[（(](?:净亏损|亏损总额|亏损|损失)以[“"‘]?[-−－—–][”"’]?号填列[）)]',
                    _compact_chinese_text(following_line),
                ):
                    continue
                # A label may be a section heading (e.g. a bank's 营业收入
                # followed by 利息收入). Never borrow the next account's values.
                break
            following_pair = _select_chinese_period_pair(
                following_values,
                value_column_count=value_column_count,
            )
            if following_pair is not None:
                return following_pair
    return None


def _chinese_income_statement_column_count(lines: list[str]) -> int | None:
    """Identify consolidated-only and consolidated-plus-company statements."""
    compact_lines = [_compact_chinese_text(line) for line in lines]
    if any("合并及公司利润表" in line for line in compact_lines):
        return 4
    if any("合并利润表" in line for line in compact_lines):
        return 2
    return None


def _extract_unit(lines: list[str]) -> str:
    """Read a declared unit, rejecting conflicting currency/scale headers."""
    return extract_statement_unit(lines)


def _has_revenue_note_header(lines: list[str], row_index: int) -> bool:
    """Recover a glued note only under an explicit, ordered two-year header."""
    if _chinese_income_statement_column_count(lines) != 2:
        return False
    start = next((i for i, line in enumerate(lines[:row_index])
                  if _compact_chinese_text(line).startswith('项目')), None)
    if start is None:
        return False
    header = ''
    for line in lines[start:row_index]:
        compact = _compact_chinese_text(line)
        if re.match(r'^(?:[一二三四五六七八九十]+[、.．])?(?:其中：)?营业(?:总)?收入', compact):
            break
        header += compact
    match = re.fullmatch(r'项目附注[一二三四五六七八九十百]*(\d{4})年度?(\d{4})年度?', header)
    relative = re.fullmatch(r'项目附注[一二三四五六七八九十百]*本期金额上期金额', header)
    subtitle_years = [line for line in lines[:start]
                      if re.fullmatch(r'\d{4}年度', _compact_chinese_text(line))]
    unit = _extract_unit(lines).removeprefix('人民币')
    return bool(((match and int(match[1]) == int(match[2]) + 1)
                 or (relative and len(subtitle_years) == 1))
                and unit in {'元', '千元', '万元', '百万元'})


def _strict_noted_revenue_pair(lines: list[str], row_index: int, label_end: int):
    """Read exactly two cells following an exact Chinese-parenthesised note.

    Numeric references are not invented. This new path neither skips another
    account nor selects the last two cells from a damaged three-cell row.
    """
    if not _has_revenue_note_header(lines, row_index) or label_end + 1 >= len(lines):
        return None
    chinese = '一二三四五六七八九十百'
    note_line = lines[label_end + 1]
    note_end = label_end + 1
    if (re.fullmatch(rf'[{chinese}]+[.．]?[1-9]\d{{0,2}}', note_line)
            or re.fullmatch(rf'[{chinese}]+、[{chinese}]+、[1-9]\d{{0,2}}', note_line)
            or re.fullmatch(rf'(?:\([{chinese}]+\)|（[{chinese}]+）)', note_line)):
        # Wanhua and China Nuclear print the note as 七61. This is only a
        # standalone note under the same explicit note/two-year header; do
        # not split glued digits into an assumed note plus an amount.
        first = ''
    else:
        note_pattern = rf'^(?:附注)?[{chinese}]+、?(?:\([{chinese}]+\)|（[{chinese}]+）)'
        note = re.match(note_pattern, note_line)
        # Existing Jinbo original wraps 五(三十四) across two lines. Only an
        # unfinished Chinese note may join; no amount/account can bridge the gap.
        while (note is None and note_end < min(label_end + 3, len(lines) - 1)
                and re.fullmatch(rf'(?:附注)?[{chinese}]+、?[（(][{chinese}]*', note_line)):
            note_end += 1
            note_line += lines[note_end]
            note = re.match(note_pattern, note_line)
        if note is None:
            return None
        first = note_line[note.end():].strip()
    amount = r'(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?'
    cell = re.compile(rf'^(?:[-−－—–]|[-−－]?{amount}|\({amount}\)|（{amount}）)$')
    values = []
    pending = ([first] if first else []) + lines[note_end + 1:note_end + 7]
    for line in pending:
        tokens = line.split()
        if tokens and all(len(token) <= 64 and cell.fullmatch(token) for token in tokens):
            values.extend(_parse_financial_value(token) for token in tokens)
            if len(values) > 2:
                return None
            continue
        compact = _compact_chinese_text(line)
        if _damaged_revenue_tail(compact) or (re.match(r'^[+\-−－—–(（.,\d]', compact) and re.search(r'\d', compact)
                and not re.search(r'[\u4e00-\u9fff]', compact)) or re.fullmatch(
                r'(?:/|不适用|无数据|N/?A|NAN|NULL|NONE)', compact, re.IGNORECASE):
            return None
        # Any other account/annotation ends this row. If either value is
        # missing the next account cannot supply it, even if it would balance.
        break
    if len(values) != 2 or not all(math.isfinite(value) and abs(value) <= 1e24 for value in values):
        return None
    return values[0], values[1]


def _damaged_revenue_tail(text):
    """Do not treat a garbled or unit-suffixed extra cell as a row boundary."""
    return bool(re.match(r'^[?？].*\d', text) or re.fullmatch(
        r'(?:人民币)?[-−－+]?\d[\d,，.]*\s*(?:百万元|千元|万元|元)', text))


def _strict_four_column_noted_revenue(lines, row_index, label_end):
    """A combined table may cite separate group and parent notes on one row."""
    start = next((i for i, line in enumerate(lines[:row_index]) if line == '项目'), None)
    if start is None or label_end + 1 >= len(lines):
        return None
    header = ''.join(_compact_chinese_text(line) for line in lines[start:row_index])
    match = re.fullmatch(r'项目附注(\d{4})年度合并(\d{4})年度合并(\d{4})年度母公司(\d{4})年度母公司', header)
    if (not match or [int(x) for x in match.groups()] != [int(match[1]), int(match[1])-1]*2
            or _extract_unit(lines).removeprefix('人民币') not in {'元', '千元', '万元', '百万元'}):
        return None
    chinese = '一二三四五六七八九十百'
    note = rf'[（(][{chinese}]+[）)][1-9]\d{{0,2}}'
    if not re.fullmatch(note + r'[,，]' + note, lines[label_end + 1]):
        return None
    amount = r'(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?'
    cell = re.compile(rf'^(?:[-−－—–]|[-−－]?{amount}|\({amount}\)|（{amount}）)$')
    values = []
    for line in lines[label_end + 2:label_end + 9]:
        tokens = line.split()
        if tokens and all(len(token) <= 64 and cell.fullmatch(token) for token in tokens):
            values.extend(_parse_financial_value(token) for token in tokens)
            if len(values) > 4:
                return None
            continue
        compact = _compact_chinese_text(line)
        if _damaged_revenue_tail(compact) or (re.match(r'^[+\-−－—–(（.,\d]', compact) and re.search(r'\d', compact)
                and not re.search(r'[\u4e00-\u9fff]', compact)) or re.fullmatch(
                r'(?:/|不适用|无数据|N/?A|NAN|NULL|NONE)', compact, re.IGNORECASE):
            return None
        break
    if len(values) != 4 or not all(math.isfinite(value) and abs(value) <= 1e24 for value in values):
        return None
    return values[0], values[1]


def _extract_chinese_revenue_pair(lines: list[str], *, value_column_count: int):
    """An explicit operating-revenue row must never fall back to total income."""
    preferred = CHINESE_REVENUE_LABELS[:2]
    starts = []; cursor = 0; visible_operating_row = False
    while cursor < len(lines):
        # The broad presence guard deliberately sees malformed suffixes too:
        # inability to read an existing row cannot authorize a different metric.
        combined = ''
        for end in range(cursor, min(cursor + 3, len(lines))):
            combined += _compact_chinese_text(lines[end])
            without_number = re.sub(r'^(?:\d+[.．、]|[一二三四五六七八九十]+[、.．])', '', combined, count=1)
            if any(without_number.startswith(label) for label in preferred):
                visible_operating_row = True
                break
        match = next(((label, end) for label in preferred
            if (end := _chinese_label_span(lines, cursor, label)) is not None), None)
        if match is not None:
            starts.append((cursor, match[1]))
            cursor = match[1] + 1
        else:
            cursor += 1
    if visible_operating_row:
        if len(starts) != 1:
            return None
        row_index, label_end = starts[0]
        following = lines[label_end + 1] if label_end + 1 < len(lines) else ''
        if value_column_count == 4 and re.match(r'^[（(][一二三四五六七八九十百]+[）)]\d+[,，]', following):
            return _strict_four_column_noted_revenue(lines, row_index, label_end)
        # Restrict the new path to the exact family it supports, including
        # malformed members of that family which must not enter old fallback.
        if (re.match(r'^(?:附注)?[一二三四五六七八九十百]+(?:、[一二三四五六七八九十百]|、[（(]|[.．]\d|[（(][一二三四五六七八九十百]|\d)', following)
                or re.fullmatch(r'[（(][一二三四五六七八九十百]+[）)]', following)):
            return _strict_noted_revenue_pair(lines, row_index, label_end)
        return _extract_chinese_row_pair(lines, preferred, value_column_count=value_column_count)
    # Preserve the existing total-only legacy layout. Its separate semantic
    # policy is not widened by recovering one explicit operating-revenue row.
    return _extract_chinese_row_pair(lines, CHINESE_REVENUE_LABELS[2:],
                                     value_column_count=value_column_count)


def extract_income_statement_figures(
    page_number: int,
    page_text: str,
    *,
    _source_pages=None,
) -> IncomeStatementFigures | None:
    """Extract revenue and profit totals without guessing missing values."""
    # The result's Chinese profit field is attributable to the parent. A
    # consolidated total is not a substitute when that row is on the next page.
    lines = _normalise_lines(bound_consolidated_statement(page_text, "利润表"))
    if _chinese_income_statement_column_count(lines) is not None:
        # Some originals number the separate parent table as “（四）母公司
        # 利润表”. Keep the duplicate-revenue guard inside the group scope.
        enumeration = r'(?:\d+[、.．]|[一二三四五六七八九十]+[、.．]|\([一二三四五六七八九十]+\)|（[一二三四五六七八九十]+）)?'
        parent = next((i for i, line in enumerate(lines) if re.fullmatch(
            enumeration + r'(?:母公司|公司)利润表(?:[（(]续[）)])?',
            _compact_chinese_text(line))), None)
        if parent is not None:
            lines = lines[:parent]

    ordinary_shareholder_profit = False
    recovered_profit = None
    if "Group income statement" in lines:
        revenue_totals = _extract_six_column_totals(lines, "Revenue")
        profit_totals = _extract_six_column_totals(
            lines,
            "Profit/(loss) for the year",
        )
        current_period_weeks, previous_period_weeks = _extract_period_weeks(
            lines
        )
    elif (
        chinese_value_column_count := _chinese_income_statement_column_count(
            lines
        )
    ) is not None:
        revenue_totals = _extract_chinese_revenue_pair(
            lines,
            value_column_count=chinese_value_column_count,
        )
        profit_totals = _extract_chinese_row_pair(
            lines,
            CHINESE_NET_PROFIT_LABELS,
            value_column_count=chinese_value_column_count,
        )
        if profit_totals is None:
            starts = [i for i in range(len(lines))
                      if _ordinary_shareholder_attribution_allowed(lines, i)]
            if len(starts) == 1:
                profit_totals = _extract_chinese_row_pair(lines[starts[0]:],
                    (ORDINARY_SHAREHOLDER_PROFIT_LABEL,), value_column_count=chinese_value_column_count)
                ordinary_shareholder_profit = profit_totals is not None
        if profit_totals is None and _source_pages is not None:
            recovered_profit = recover_cross_page_attributable_profit(_source_pages)
            if (recovered_profit and recovered_profit['values'] is not None
                    and chinese_value_column_count == 2
                    and _extract_unit(lines).removeprefix('人民币') == recovered_profit['unit']):
                profit_totals = tuple(float(value) for value in recovered_profit['values'])
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
        **({'attributable_label': ORDINARY_SHAREHOLDER_PROFIT_LABEL}
           if ordinary_shareholder_profit else {}),
        **({'attributable_layout_recovery': {
            **recovered_profit, 'values': [str(v) for v in recovered_profit['values']]}}
           if recovered_profit and recovered_profit['values'] is not None else {}),
    }


def _with_attribution_continuation(figures, page_list):
    """Include a third page only for an explicit continuation of attribution.

    Finding revenue and parent profit on two pages does not mean the income
    table ends there. A matching repeated header and minority row can follow.
    """
    start, end = figures['page_number'], figures['end_page_number']
    if end - start >= 2:
        return figures
    selected = [(n, t) for n, t in page_list if start <= n <= end]
    if [n for n, _ in selected] != list(range(start, end + 1)):
        return figures
    lines = _normalise_lines(bound_consolidated_statement('\n'.join(t for _, t in selected), '利润表'))
    if (_chinese_income_statement_column_count(lines) != 2
            or any('少数股东损益' in line or '其他综合收益' in line or '母公司利润表' in line for line in lines)):
        return figures
    next_pages = [t for n, t in page_list if n == end + 1]
    if len(next_pages) != 1:
        return figures
    continuation = _normalise_lines(next_pages[0])
    if len(continuation) < 5 or continuation[:2] != ['项目', '附注']:
        return figures
    years = continuation[2:4]
    if (not all(re.fullmatch(r'\d{4} 年度|\d{4}年度', y) for y in years)
            or int(years[0][:4]) != int(years[1][:4]) + 1):
        return figures
    compact = [_compact_chinese_text(x) for x in lines]
    expected = ['项目', '附注'] + [_compact_chinese_text(y) for y in years]
    if not any(compact[i:i+4] == expected for i in range(len(compact)-3)):
        return figures
    for i in range(len(compact)):
        if compact[i:i+2] == ['项目', '附注'] and compact[i:i+4] != expected:
            return figures
    if _chinese_label_span(continuation, 4, '少数股东损益') is None:
        return figures
    return {**figures, 'end_page_number': end + 1}


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
            return _with_attribution_continuation(figures, page_list)
        if _chinese_income_statement_column_count(
            _normalise_lines(page_text)
        ) is None:
            continue

        for window_size in range(2, 4):
            window = page_list[page_index : page_index + window_size]
            if len(window) < window_size or [p for p, _ in window] != list(range(page_number, page_number + window_size)):
                break
            figures = extract_income_statement_figures(
                page_number=page_number,
                page_text="\n".join(text for _, text in window),
                _source_pages=window,
            )
            if figures is not None:
                figures["end_page_number"] = window[-1][0]
                return _with_attribution_continuation(figures, page_list)

    return None
