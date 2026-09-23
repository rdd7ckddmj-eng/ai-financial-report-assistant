"""Conservative rules for declared units and integer display rounding."""
import re


def consistent_statement_unit(units):
    """Recognise RMB spelling aliases without changing the recorded originals."""
    if len(units) != 3 or not all(isinstance(unit, str) and unit for unit in units):
        return None
    canonical = [unit.removeprefix('人民币') for unit in units]
    if len(set(canonical)) == 1 and canonical[0] in {'元', '千元', '万元', '百万元', '亿元'}:
        return units[0]
    return None


def _standalone_header_units(lines):
    """Inspect every title/continuation header in the bounded table window."""
    compact = [re.sub(r'\s+', '', x) for x in lines if x.strip()]
    units = set()
    for index, text in enumerate(compact):
        if not re.fullmatch(r'(?:人民币(?:百万元|千元|万元|元)|美元|港元|欧元|日元)', text):
            continue
        for start in range(max(0, index - 4), index):
            if not re.fullmatch(r'合并(?:及公司)?(?:资产负债表|利润表|现金流量表)(?:[（(]续[）)])?', compact[start]):
                continue
            # Only a reporting date/page number may separate title and unit.
            if all(re.fullmatch(r'(?:\d{4}年(?:\d{1,2}月\d{1,2}日|度)?|\d{1,4}|人民币(?:百万元|千元|万元|元)|美元|港元|欧元|日元)', x)
                   for x in compact[start+1:index]):
                units.add(text)
    return units


def standalone_statement_unit(lines):
    units = _standalone_header_units(lines)
    return next(iter(units)) if len(units) == 1 and all(x.startswith('人民币') for x in units) else ''


def extract_statement_unit(lines):
    """Keep all explicit declarations consistent, never pick a convenient one."""
    explicit=[]
    for line in lines:
        compact=re.sub(r'\s+', '', line).replace(':','：')
        if re.fullmatch(r'[£$€](?:k|m|bn)?', compact, re.IGNORECASE):
            explicit.append(compact)
        for m in re.finditer(r'(?:金额)?单位(?:[：]|(?:均)?为[：]?)(?:人民币)?(百万元|千元|万元|元|美元|港元|欧元|日元)',compact):
            explicit.append(('人民币' if '人民币' in compact else '')+m[1])
        currency=re.search(r'币种[：]?(美元|港元|欧元|日元)', compact)
        if currency:
            explicit.append(currency[1])
    # Header-only standalone declarations may not be silently overridden by
    # another standalone unit or a conflicting "单位：..." declaration.
    standalone=list(_standalone_header_units(lines))
    canonical={x.removeprefix('人民币') for x in explicit+standalone}
    if len(canonical)>1 or canonical & {'美元','港元','欧元','日元'}:
        return ''
    if explicit:
        return explicit[0]
    return standalone_statement_unit(lines)


def bound_consolidated_statement(text, kind):
    """Stop a concatenated consolidated table before an independent parent table."""
    group=re.search(r'合\s*并(?:\s*及\s*公\s*司)?\s*'+kind,text)
    if not group:
        return text
    # A physical page may start with the tail of the preceding parent table.
    text=text[group.start():]
    parent=re.search(r'(?m)^[ \t]*(?:\d+[、.．][ \t]*)?(?:母\s*公\s*司|公\s*司)\s*'+kind+r'\s*(?:[（(]续[）)])?[ \t]*$',text)
    if parent:
        return text[:parent.start()]
    return text


def integer_rounding_tolerance(unit, rows, lines):
    """One display unit only for explicitly scaled, integer-only statements.

    This is a bounded display-rounding allowance, not a materiality threshold.
    Preserve the existing half-unit rule in every other case.
    """
    normalized = re.sub(r'\s+', '', unit).removeprefix('人民币')
    if normalized not in {'千元', '万元', '百万元'}:
        return 0.5
    if any(re.search(r'\d\.\d', line) for line in lines):
        return 0.5
    if not rows or any(pair is None for pair in rows):
        return 0.5
    if not all(float(value).is_integer() for pair in rows for value in pair):
        return 0.5
    return 1.0


def inherit_statement_units(page_list, statements):
    """Fill missing units only inside one explicit, bounded financial section.

    Original page text remains untouched. Ambiguous/mixed declarations are not
    inherited, and an explicit local-unit conflict blocks all unit validation.
    """
    if len(statements) != 3 or any(s is None for s in statements):
        return
    candidates = []
    for page, text in page_list:
        compact = re.sub(r'[ \t\u3000]', '', text)
        header = re.search(r'(?m)^[一二三四五六七八九十]+[、．.]财务报表\s*$', compact)
        declaration = re.search(r'财务附注中报表的单位为[:：](?:人民币)?(千元|万元|百万元|元)', compact)
        balance = re.search(r'合并资产负债表', compact)
        if header and declaration and balance and header.end() <= declaration.start() < balance.start():
            candidates.append((page, declaration.group(1), declaration.group(0)))
    if len(candidates) != 1:
        return
    page, unit, excerpt = candidates[0]
    start = min(s['page_number'] for s in statements)
    end = max(s['end_page_number'] for s in statements)
    if start != page or end - page > 20:
        return
    scope = [(p, text) for p, text in page_list if page <= p <= end]
    if [p for p, _ in scope] != list(range(page, end + 1)):
        return
    # Do not carry a general unit into notes or a later numbered section.
    for p, text in scope:
        if p > page and re.search(r'(?m)^\s*[三四五六七八九十]+[、．.]\s*(?:公司|企业|财务报表附注|合并财务报表|重要会计)', text):
            return
        compact = re.sub(r'\s+', '', text)
        declarations = re.findall(r'单位(?:为[:：]?|[:：])(?:人民币)?(千元|万元|百万元|元|美元|港元)', compact)
        declarations += [value.removeprefix('人民币') for value in _standalone_header_units(text.splitlines())]
        declarations += re.findall(r'币种[:：]?(美元|港元|欧元|日元)', compact)
        if any(value != unit for value in declarations):
            for statement in statements:
                statement['unit'] = ''
            return
    for statement in statements:
        local = re.sub(r'\s+', '', statement.get('unit', '')).removeprefix('人民币')
        if local and local != unit:
            for item in statements:
                item['unit'] = ''
            return
    for statement in statements:
        if not statement.get('unit'):
            statement['unit'] = unit
            statement['unit_source_note'] = f'单位来源：PDF第{page}页财务报表总说明“{excerpt}”。'
