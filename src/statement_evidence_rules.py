"""Conservative rules for declared units and integer display rounding."""
import re


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
