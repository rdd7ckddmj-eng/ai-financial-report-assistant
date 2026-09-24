"""Recognise printed page-number runs in explicit continued statement tables.

The PDF text and its physical page numbers remain the source of record. Only
the verified page-number lines are omitted from the parser view, never cells.
"""
import re


def _compact(text):
    return re.sub(r'\s+', '', text)


def _period_header(lines, kind):
    """Require the same complete column header on each physical page."""
    prefix = ''.join(_compact(line) for line in lines[:25])
    if kind == '资产负债表':
        pattern = (r'项目附注(\d{4})年12月31日(\d{4})年12月31日'
                   r'(?=流动资产|非流动资产|流动负债|应付票据|递延所得税负债|非流动负债)')
        match = re.search(pattern, prefix)
        if match:
            return ('dated_two_columns', int(match[1]), int(match[2]))
        match = re.search(r'(\d{4})年(\d{4})年(?:资产|负债及股东权益)附注'
                          r'12月31日12月31日合并合并', prefix)
        if match:
            return ('split_date_group_columns', int(match[1]), int(match[2]))
    if kind in {'现金流量表', '利润表'}:
        match = re.search(r'项目附注(\d{4})年度(\d{4})年度(\d{4})年度(\d{4})年度'
                          r'合并合并公司公司', prefix)
        if match and match.groups()[:2] == match.groups()[2:]:
            return ('ordered_group_company_columns', int(match[1]), int(match[2]))
    return None


def recover_printed_statement_page_numbers(source_pages, kind):
    """Return a parser view plus exact evidence, or None for other layouts.

    A number alone is insufficient. Require adjacent physical pages, the same
    complete ordered period header, consecutive printed numbers with one fixed
    offset, and repeated annual-report footer identities. For the trailing
    variant at least two pages must additionally print the annual-report title.
    """
    if len(source_pages) < 2 or kind not in {'资产负债表', '现金流量表', '利润表'}:
        return None
    physical = [number for number, _ in source_pages]
    if physical != list(range(physical[0], physical[0] + len(physical))):
        return None
    first = _compact(source_pages[0][1])
    if ('合并' + kind not in first and '合并及公司' + kind not in first):
        return None
    all_text = '\n'.join(text for _, text in source_pages)
    if re.search(r'(?:母公司|(?<!及)公司)\s*' + kind, all_text):
        return None
    records = []
    for physical_page, text in source_pages:
        raw = text.splitlines(keepends=True)
        nonempty = [(i, line) for i, line in enumerate(raw) if line.strip()]
        header = _period_header([line for _, line in nonempty], kind)
        if header is None or header[1] != header[2] + 1:
            return None
        year = str(header[1])
        # A title date cannot disagree with the declared value columns.
        title_years = re.findall(r'(\d{4})年(?:12月31日|度)合并(?:及公司)?' + kind,
                                _compact(text))
        if any(value != year for value in title_years):
            return None
        index = None
        mode = None
        company = None
        report_footer = False
        if len(nonempty) > 1 and re.fullmatch(r'\d{2,4}', nonempty[0][1].strip()):
            footer_text = _compact(nonempty[1][1])
            company_match = re.fullmatch(r'([\u4e00-\u9fff]+股份有限公司)' + year + '年?年度报告', footer_text)
            if company_match is None:
                company_match = re.fullmatch(year + r'年?年度报告([\u4e00-\u9fff]+股份有限公司)', footer_text)
            if company_match:
                index, company, mode = nonempty[0][0], company_match[1], 'leading_footer'
                report_footer = True
        if index is None and kind == '资产负债表' and header[0] == 'dated_two_columns':
            last = len(nonempty) - 1
            if _compact(nonempty[last][1]) == year + '年度报告':
                report_footer = True
                last -= 1
            if last >= 0 and re.fullmatch(r'\d{2,4}', nonempty[last][1].strip()):
                index, mode = nonempty[last][0], 'trailing_footer'
        if index is None:
            return None
        printed = int(raw[index].strip())
        if printed <= 0 or printed > physical_page:
            return None
        records.append(dict(page_number=physical_page, printed=printed, header=header,
                            mode=mode, company=company, report_footer=report_footer,
                            index=index, raw=raw))
    if len({record['header'] for record in records}) != 1:
        return None
    if len({record['mode'] for record in records}) != 1:
        return None
    if len({record['page_number'] - record['printed'] for record in records}) != 1:
        return None
    if records[0]['mode'] == 'leading_footer':
        if len({record['company'] for record in records}) != 1:
            return None
    elif sum(record['report_footer'] for record in records) < 2:
        return None
    clean_pages = []
    spans = []
    for record in records:
        raw, index = record['raw'], record['index']
        clean_pages.append((record['page_number'], ''.join(raw[:index] + raw[index + 1:])))
        spans.append(dict(page_number=record['page_number'], original_text=raw[index],
                          printed_page_number=record['printed']))
    return clean_pages, dict(kind='consecutive_printed_statement_page_numbers',
                             statement=kind, source_spans=spans,
                             physical_to_printed_offset=physical[0] - records[0]['printed'],
                             header_years=list(records[0]['header'][1:]))
