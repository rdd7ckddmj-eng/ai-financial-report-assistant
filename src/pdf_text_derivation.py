"""Replay a bounded PDF-layout correction without replacing original evidence."""
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
import math
import re

MAX_DOCUMENT_ADJUSTMENTS = 8
_SPAN = re.compile(r'-[ \t]*\n[ \t]*(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)[ \t]*')
_LABEL = re.compile(r'^(?:[一二三四五六七八九十]+[、.．])?利润总额(?:[（(](?:亏损总额以[“"‘]?-[”"’]?号填列|亏损总额)[）)])?$')


def _line_positions(text, expected):
    matches, offset = [], 0
    for line in text.splitlines(keepends=True):
        if line.strip() == expected:
            matches.append((offset, offset + len(line)))
        offset += len(line)
    return matches


def _consistent_layout(item, original):
    """Check producer-record consistency, without claiming a second PDF reading."""
    sign, amount, cell, row = (item[k] for k in ('sign_bbox', 'amount_bbox', 'cell_bbox', 'row_bbox'))
    def inside(inner, outer):
        return all((inner[0] >= outer[0]-1, inner[1] >= outer[1]-1,
                    inner[2] <= outer[2]+1, inner[3] <= outer[3]+1))
    bounds = item.get('year_column_bounds')
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(not isinstance(b, list) or len(b) != 2
                   or any(type(n) not in (float, int) or not math.isfinite(n) or not 0 <= n <= 20000 for n in b)
                   or b[0] >= b[1] for b in bounds)):
        return False
    selected = bounds[item['header_years'].index(item['column_year'])]
    height = amount[3]-amount[1]
    delta = (amount[1]+amount[3]-sign[1]-sign[3])/2
    if (not inside(sign, cell) or not inside(amount, cell) or not inside(cell, row)
            or abs(bounds[0][1]-bounds[1][0]) > 1
            or bounds[0][0] < row[0]-1 or abs(bounds[1][1]-row[2]) > 1
            or abs(cell[0]-selected[0]) > 1 or abs(cell[2]-selected[1]) > 1
            or abs(cell[1]-row[1]) > 1 or abs(cell[3]-row[3]) > 1
            or not .85 <= (sign[3]-sign[1])/height <= 1.15
            or not .4*height <= delta <= 1.15*height
            or abs(sign[2]-amount[2]) > max(1, .12*height)
            or not 1.4*height <= row[3]-row[1] <= 3*height):
        return False
    neighbors = {'previous': '减：营业外支出', 'next': '减：所得税费用'}
    if item.get('supporting_row_labels') != neighbors:
        return False
    label = _line_positions(original, item['label'])
    before = _line_positions(original, neighbors['previous'])
    after = _line_positions(original, neighbors['next'])
    return (len(label) == len(before) == len(after) == 1
            and before[0][1] <= label[0][0] < label[0][1] <= item['start_offset']
            and item['end_offset'] <= after[0][0])


def preserve_original_income_excerpts(detail, adjustments, pages):
    """Separate an original row from the parser's normalized/derived excerpt."""
    by_number = dict(pages)
    for item in adjustments:
        evidence = detail.get('evidence', {}).get(item['metric'])
        if not evidence or 'excerpt' not in evidence or 'parser_excerpt' in evidence:
            continue
        original = by_number[item['page_number']]
        start = _line_positions(original, item['label'])[0][0]
        end = _line_positions(original, item['supporting_row_labels']['next'])[0][0]
        evidence['parser_excerpt'] = evidence['excerpt']
        evidence['excerpt'] = original[start:end].rstrip()
        evidence['excerpt_kind'] = 'original_pdf_text'
        evidence['processing_note'] = '金额计算使用parser_excerpt中的派生文本；excerpt保留原PDF行及负号换行。'


def compact_report_text_adjustments(report):
    """Keep a bounded processing summary in a case; full coordinates stay in the workpaper."""
    records = report.get('text_adjustments', [])
    if not isinstance(records, list) or len(records) > MAX_DOCUMENT_ADJUSTMENTS:
        raise ValueError('负号处理记录数量或结构无效。')
    result = []
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError('负号处理记录无效。')
        span, replacement = item.get('original_span'), item.get('replacement_span')
        match = _SPAN.fullmatch(span) if isinstance(span, str) and len(span) <= 80 else None
        year, page = item.get('column_year'), item.get('page_number')
        label = item.get('label')
        if (not match or replacement != '-' + match['amount']
                or item.get('kind') != 'join_split_minus_in_amount_cell'
                or type(report.get('report_year')) is not int or type(year) is not int
                or year not in (report['report_year'], report['report_year'] - 1)
                or type(page) is not int or not 1 <= page <= 1000
                or not isinstance(label, str) or len(label) > 80
                or not _LABEL.fullmatch(re.sub(r'\s+', '', label))):
            raise ValueError('负号处理记录的页码、年度、科目或原字符连接不一致。')
        result.append(dict(kind=item['kind'], page_number=page, column_year=year,
            label=label, original_span=span, replacement_span=replacement))
    return result


def replay_financial_geometry(page, *, pdf_fingerprint, report_year):
    """Validate this extraction's metadata and replay exact sign joins only.

    The producer proves geometry while the PDF is open. This consumer checks
    provenance, offsets, scope and permitted text changes; it does not claim
    independently re-reading coordinates or authenticate an imported archive.
    """
    original = str(page.get('text', ''))
    derivation = page.get('financial_geometry')
    if derivation is None:
        return original, []
    error = 'PDF版面处理记录与原文不一致，不能使用派生文本。'
    if not isinstance(derivation, Mapping) or derivation.get('schema') != 'pdf-signed-amount-geometry.v1':
        raise ValueError(error)
    adjustments = derivation.get('adjustments')
    if (derivation.get('document_sha256') != pdf_fingerprint
            or derivation.get('original_text_sha256') != sha256(original.encode()).hexdigest()
            or not isinstance(adjustments, list) or not 1 <= len(adjustments) <= 2):
        raise ValueError(error)
    try:
        if len(json.dumps(adjustments, ensure_ascii=False, allow_nan=False).encode()) > 16000:
            raise ValueError(error)
    except (TypeError, OverflowError) as exc:
        raise ValueError(error) from exc
    cursor = 0
    pieces = []
    for item in adjustments:
        if not isinstance(item, Mapping):
            raise ValueError(error)
        start, end = item.get('start_offset'), item.get('end_offset')
        span, replacement = item.get('original_span'), item.get('replacement_span')
        if (type(start) is not int or type(end) is not int or not cursor <= start < end <= len(original)
                or not isinstance(span, str) or len(span) > 80 or original[start:end] != span
                or not isinstance(replacement, str)):
            raise ValueError(error)
        matched = _SPAN.fullmatch(span)
        if not matched or replacement != '-' + matched['amount']:
            raise ValueError(error)
        if (item.get('kind') != 'join_split_minus_in_amount_cell'
                or type(item.get('page_number')) is not int or item['page_number'] != page.get('page_number')
                or type(item.get('report_year')) is not int or item['report_year'] != report_year
                or type(item.get('column_year')) is not int or item['column_year'] not in (report_year, report_year - 1)
                or item.get('header_years') != [report_year, report_year - 1]
                or type(item.get('header_page_number')) is not int
                or item['header_page_number'] not in (page['page_number'], page['page_number'] - 1)
                or item.get('statement') != '合并利润表' or item.get('metric') != 'profit_before_tax'
                or not _LABEL.fullmatch(re.sub(r'\s+', '', str(item.get('label', ''))))):
            raise ValueError(error)
        for name in ('sign_bbox', 'amount_bbox', 'cell_bbox', 'row_bbox'):
            box = item.get(name)
            if (not isinstance(box, (list, tuple)) or len(box) != 4
                    or any(type(n) not in (float, int) or not math.isfinite(n) or not 0 <= n <= 20000 for n in box)
                    or not box[0] < box[2] or not box[1] < box[3]):
                raise ValueError(error)
        if not _consistent_layout(item, original):
            raise ValueError(error)
        pieces.extend((original[cursor:start], replacement))
        cursor = end
    pieces.append(original[cursor:])
    parsed = ''.join(pieces)
    if derivation.get('parser_text') != parsed:
        raise ValueError(error)
    return parsed, deepcopy(adjustments)
