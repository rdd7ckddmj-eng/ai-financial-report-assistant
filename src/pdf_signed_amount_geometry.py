"""Conservative, opt-in geometric evidence for one wrapped minus-sign layout.

This module never edits a PDF or its original text. A derived parser string is
returned only for a ruled, two-year consolidated income table's profit-before-
tax row. Missing glyphs, image text, inferred signs, and borderless tables are
outside this rule. The caller retains the original text and document hashes.
"""
import re


SCHEMA = 'pdf-signed-amount-geometry.v1'
MAX_PAGE_TEXT = 100_000
MAX_WORDS = 4_000
MAX_DRAWINGS = 512
MAX_DRAWING_ITEMS = 2_048
_EPS = 1.0  # PDF points; only accommodates stroke/bbox rounding.
_AMOUNT = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?'
_UNSIGNED = re.compile(rf'{_AMOUNT}\Z')
_SIGNED = re.compile(rf'(?:-?{_AMOUNT}|\({_AMOUNT}\))\Z')
_SPLIT = re.compile(rf'(?m)^(?P<sign>-)[ \t]*\n[ \t]*(?P<amount>{_AMOUNT})[ \t]*(?=\n|$)')
_YEAR = re.compile(r'(19\d{2}|20\d{2})(?:年度)?\Z')
_PREFIX = re.compile(r'^[一二三四五六七八九十]+[、.．]')
_PBT = re.compile(r'利润总额(?:\((?:亏损总额以[“"‘]?-[”"’]?号填列|亏损总额)\))?\Z')
_CHAPTER = r'(?:[（(][一二三四五六七八九十百0-9]+[）)]|[一二三四五六七八九十百0-9]+[、.．]?)'
_STOP = re.compile(r'(?m)^[ \t\u3000]*(?:' + _CHAPTER + r'[ \t\u3000]*)?'
                   r'(?:母\s*公\s*司|公\s*司|合\s*并(?:\s*及\s*公\s*司)?)\s*'
                   r'(?:资\s*产\s*负\s*债\s*表|利\s*润\s*表|现\s*金\s*流\s*量\s*表|所有者权益变动表)'
                   r'\s*(?:[（(]续[）)])?[ \t\u3000]*$')
_NOTE = re.compile(r'(?:[一二三四五六七八九十]+[、.．]\d{1,3}|\d{1,3})\Z')


def _compact(text):
    return re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')').replace(':', '：')


def _label(text):
    return bool(_PBT.fullmatch(_PREFIX.sub('', _compact(text))))


def _raw_labels(text, predicate):
    result, offset = [], 0
    for line in text.splitlines(keepends=True):
        if predicate(line.strip()):
            result.append((offset, offset + len(line), line.strip()))
        offset += len(line)
    return result


def _box(word):
    return [round(float(x), 5) for x in word[:4]]


def _center(word):
    return (word[1] + word[3]) / 2


def _unique(values):
    result = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > _EPS:
            result.append(float(value))
    return result


def _geometry(page):
    # The caller's string prefilter runs before either geometry operation.
    words = page.get_text('words')
    if not words or len(words) > MAX_WORDS:
        return None
    drawings = page.get_drawings()
    if len(drawings) > MAX_DRAWINGS or sum(len(d.get('items', [])) for d in drawings) > MAX_DRAWING_ITEMS:
        return None
    horizontal, vertical = [], []

    def line(x0, y0, x1, y1):
        if abs(y0 - y1) <= .25 and abs(x1 - x0) > 3:
            horizontal.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2))
        elif abs(x0 - x1) <= .25 and abs(y1 - y0) > 3:
            vertical.append(((x0 + x1) / 2, min(y0, y1), max(y0, y1)))

    for drawing in drawings:
        for item in drawing.get('items', []):
            if item[0] == 'l':
                line(item[1].x, item[1].y, item[2].x, item[2].y)
            elif item[0] == 're':
                rect = item[1]
                line(rect.x0, rect.y0, rect.x1, rect.y0)
                line(rect.x0, rect.y1, rect.x1, rect.y1)
                line(rect.x0, rect.y0, rect.x0, rect.y1)
                line(rect.x1, rect.y0, rect.x1, rect.y1)
    return words, horizontal, vertical


def _columns(vertical, top, bottom):
    return _unique(x for x, a, b in vertical if a <= top + _EPS and b >= bottom - _EPS)


def _row_lines(horizontal, columns):
    return _unique(y for left, right, y in horizontal
                   if left <= columns[0] + _EPS and right >= columns[-1] - _EPS)


def _enclosing_row(horizontal, columns, top, bottom):
    ys = _row_lines(horizontal, columns)
    above = [y for y in ys if y <= top + .25]
    below = [y for y in ys if y >= bottom - .25]
    if not above or not below or above[-1] >= below[0]:
        return None
    return above[-1], below[0]


def _headers(page, text, geometry, report_year):
    words, horizontal, vertical = geometry
    titles = [w for w in words if w[4] == '合并利润表']
    if len(titles) != 1:
        return []
    title = titles[0]
    years = [w for w in words if _YEAR.fullmatch(w[4])
             and title[3] < w[1] < title[3] + 120]
    found = []
    for first in years:
        same_line = sorted([w for w in years if abs(_center(w) - _center(first)) <= 3], key=lambda w: w[0])
        if len(same_line) != 2 or first != same_line[0]:
            continue
        current, previous = [int(_YEAR.fullmatch(w[4])[1]) for w in same_line]
        if current != previous + 1 or (report_year is not None and current != report_year):
            continue
        top, bottom = min(w[1] for w in same_line), max(w[3] for w in same_line)
        columns = _columns(vertical, top, bottom)
        # Only label, optional note, and two amount columns are supported.
        if len(columns) not in (4, 5):
            continue
        if not all(columns[-3+i] + _EPS < w[0] and w[2] < columns[-2+i] - _EPS
                   for i, w in enumerate(same_line)):
            continue
        row = _enclosing_row(horizontal, columns, top, bottom)
        if row is None:
            continue
        cells = _cells(words, columns, *row)
        if cells is None or _compact(_cell_text(cells[0])) != '项目':
            continue
        if len(cells) == 4 and _compact(_cell_text(cells[1])) != '附注':
            continue
        if not all(_compact(_cell_text(cell)) == f'{year}年度'
                   for cell, year in zip(cells[-2:], (current, previous))):
            continue
        found.append(dict(columns=columns, years=[current, previous], title_bbox=_box(title),
                          header_bottom=row[1], page_number=page.number + 1))
    return found


def _cells(words, columns, top, bottom):
    cells = [[] for _ in range(len(columns) - 1)]
    for word in words:
        if not (top < _center(word) < bottom and columns[0] < (word[0] + word[2]) / 2 < columns[-1]):
            continue
        if word[1] < top - _EPS or word[3] > bottom + _EPS:
            return None
        candidates = [i for i in range(len(cells))
                      if word[0] >= columns[i] - _EPS and word[2] <= columns[i+1] + _EPS]
        if len(candidates) != 1:
            return None
        cells[candidates[0]].append(word)
    return cells


def _cell_text(cell):
    # Preserve the text layer's reading order; font ascent differences can put
    # the Chinese "年度" center slightly above its adjacent Arabic year.
    return ''.join(w[4] for w in cell)


def _neighbor(words, horizontal, columns, row, *, previous):
    ys = _row_lines(horizontal, columns)
    if previous:
        options = [y for y in ys if y < row[0] - _EPS]
        limits = (options[-1], row[0]) if options else None
    else:
        options = [y for y in ys if y > row[1] + _EPS]
        limits = (row[1], options[0]) if options else None
    if limits is None:
        return None
    cells = _cells(words, columns, *limits)
    if cells is None:
        return None
    expected = '减：营业外支出' if previous else '减：所得税费用'
    if _compact(_cell_text(cells[0])) != expected:
        return None
    if any(len(c) != 1 or not _SIGNED.fullmatch(c[0][4]) for c in cells[-2:]):
        return None
    return expected


def derive_signed_amount_geometry(page, *, report_year=None, original_text=None, previous_page=None):
    """Return an auditable derived string for a uniquely established minus.

    ``page`` and optional ``previous_page`` are live PyMuPDF Page objects from
    the same document. The latter must immediately precede the former. No file
    is opened here; callers keep this work inside their existing PDF parse lock.
    Offsets use Python string indexes and a half-open [start, end) interval.
    Unsupported, over-budget or ambiguous pages return unchanged parser_text.
    """
    text = page.get_text('text') if original_text is None else original_text
    result = dict(schema=SCHEMA, parser_text=text, adjustments=[])
    if not isinstance(text, str) or len(text) > MAX_PAGE_TEXT or page.rotation:
        return result
    if report_year is not None and (type(report_year) is not int or not 1900 <= report_year <= 2099):
        return result
    labels = _raw_labels(text, _label)
    split_matches = list(_SPLIT.finditer(text))
    if len(labels) != 1 or not split_matches or len(split_matches) > 4:
        return result
    # A supplied text layer must be exactly the one used for geometry.
    if original_text is not None and page.get_text('text') != original_text:
        return result
    label_start, label_end, raw_label = labels[0]
    if len(raw_label) > 80:
        return result
    local_title = _raw_labels(text[:label_start], lambda s: s == '合并利润表')
    header_page, header_text = page, text
    if local_title:
        if len(local_title) != 1 or _STOP.search(text[local_title[0][1]:label_start]):
            return result
    else:
        if previous_page is None or previous_page.parent is not page.parent or previous_page.number + 1 != page.number:
            return result
        if previous_page.rotation or abs(previous_page.rect.width - page.rect.width) > _EPS:
            return result
        header_text = previous_page.get_text('text')
        if len(header_text) > MAX_PAGE_TEXT:
            return result
        titles = _raw_labels(header_text, lambda s: s == '合并利润表')
        if len(titles) != 1 or _STOP.search(header_text[titles[0][1]:]) or _STOP.search(text[:label_start]):
            return result
        header_page = previous_page
    geometry = _geometry(page)
    header_geometry = geometry if header_page is page else _geometry(header_page)
    if geometry is None or header_geometry is None:
        return result
    headers = _headers(header_page, header_text, header_geometry, report_year)
    if len(headers) != 1:
        return result
    header = headers[0]
    words, horizontal, vertical = geometry
    label_words = [w for w in words if _label(w[4])]
    if len(label_words) != 1:
        return result
    label_word = label_words[0]
    columns = header['columns']
    row = _enclosing_row(horizontal, columns, label_word[1], label_word[3])
    if row is None or (header_page is page and row[0] < header['header_bottom']):
        return result
    row_columns = _columns(vertical, *row)
    if len(columns) != len(row_columns) or any(abs(a-b) > _EPS for a, b in zip(columns, row_columns)):
        return result
    cells = _cells(words, columns, *row)
    if cells is None or not _label(_cell_text(cells[0])):
        return result
    if len(cells) == 4 and cells[1] and not _NOTE.fullmatch(_compact(_cell_text(cells[1]))):
        return result
    before = _neighbor(words, horizontal, columns, row, previous=True)
    after = _neighbor(words, horizontal, columns, row, previous=False)
    if before is None or after is None:
        return result
    pairs = []
    for column_index, cell in enumerate(cells[-2:]):
        other = cells[-2:][1-column_index]
        if len(other) != 1 or not _SIGNED.fullmatch(other[0][4]) or len(cell) != 2:
            continue
        sign, amount = sorted(cell, key=lambda w: _center(w))
        if sign[4] != '-' or not _UNSIGNED.fullmatch(amount[4]):
            continue
        height = amount[3] - amount[1]
        delta = _center(amount) - _center(sign)
        # Both glyph boxes must be right-aligned inside one closed cell. The
        # other year's amount is centered on this same row, not a nearby row.
        if (height <= 0 or not .85 <= (sign[3]-sign[1])/height <= 1.15
                or not .4*height <= delta <= 1.15*height
                or abs(sign[2]-amount[2]) > max(1, .12*height)
                or not 1.4*height <= row[1]-row[0] <= 3.0*height
                or abs(_center(other[0]) - (_center(sign)+_center(amount))/2) > .35*height):
            continue
        left, right = columns[-3+column_index], columns[-2+column_index]
        # The padding must agree with the adjacent numeric column as well.
        other_right = columns[-1-column_index]
        padding, other_padding = right - amount[2], other_right - other[0][2]
        if not 1 <= padding <= 12 or abs(padding-other_padding) > 2:
            continue
        if words.index(amount) != words.index(sign) + 1:
            continue
        matches = [m for m in split_matches if m['amount'] == amount[4]
                   and label_end <= m.start() and m.end() < text.find(after, label_end)]
        if len(matches) != 1 or len(matches[0].group()) > 80:
            continue
        pairs.append((column_index, sign, amount, left, right, matches[0]))
    if len(pairs) != 1:
        return result
    column_index, sign, amount, left, right, match = pairs[0]
    replacement = '-' + amount[4]
    adjustment = dict(kind='join_split_minus_in_amount_cell', page_number=page.number+1,
        report_year=header['years'][0], column_year=header['years'][column_index],
        statement='合并利润表', metric='profit_before_tax', label=raw_label,
        start_offset=match.start(), end_offset=match.end(), original_span=match.group(),
        replacement_span=replacement, sign_bbox=_box(sign), amount_bbox=_box(amount),
        cell_bbox=[left, row[0], right, row[1]], row_bbox=[columns[0], row[0], columns[-1], row[1]],
        header_page_number=header['page_number'], header_years=header['years'],
        year_column_bounds=[[columns[-3], columns[-2]], [columns[-2], columns[-1]]],
        supporting_row_labels=dict(previous=before, next=after),
        reason='明确合并利润表的连续双年度列；税前利润行由上下刻线及相邻科目限定；负号与数字唯一位于同一封闭单元格并右对齐，保持原字符只连接换行。')
    result['parser_text'] = text[:match.start()] + replacement + text[match.end():]
    result['adjustments'] = [adjustment]
    return result
