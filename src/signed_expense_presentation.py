"""Evidence for four-column statements that print expenses as signed amounts.

The convention is selected from labels and explicit cell formatting, never by
trying both arithmetic directions. This is not a full operating-profit audit.
"""
import re


def signed_expense_presentation(lines, page_numbers, columns, unit, tax_row):
    from src.general_income_reconciliation import _compact, _financial_line, _value

    marker = [i for i, line in enumerate(lines) if _compact(line) == '财务(费用)/收入']
    if not marker:
        return None
    if len(marker) != 1 or columns != 4 or unit != '千元':
        raise ValueError('带符号费用版式的四列及单位证据不完整')
    # Exact adjacent row boundaries make additional numbers, unknown notes and
    # unknown prose errors rather than quietly truncating a completed row.
    sections = (
        ('减：营业成本', '税金及附加'),
        ('税金及附加', '销售费用'),
        ('管理费用', '研发费用'),
        ('财务(费用)/收入', '其中：利息费用'),
    )
    evidence = []
    positions = []
    for label, boundary in sections:
        starts = [i for i, line in enumerate(lines) if _compact(line) == label]
        ends = [i for i, line in enumerate(lines) if _compact(line) == boundary]
        if len(starts) != 1 or len(ends) != 1 or not 1 < ends[0] - starts[0] <= 7:
            raise ValueError('费用符号依据的行或边界缺失、重复')
        start, end = starts[0], ends[0]
        cells = []; notes = []
        for line in lines[start + 1:end]:
            parsed = _financial_line(line)
            if parsed is None:
                raise ValueError('费用符号依据含未知附注或损坏数值')
            amounts, note = parsed
            if note:
                if cells or notes or amounts:
                    raise ValueError('费用符号依据的附注位置不明确')
                notes.append(line)
            cells.extend(amounts)
        if len(notes) != 1 or len(notes[0].split()) != 1 or len(cells) != 4:
            raise ValueError('费用符号依据缺少唯一附注及四个金额')
        parenthesised = lambda cell: bool(re.fullmatch(r'\([\d,，.]+\)', cell)) and _value(cell) < 0
        if not all(parenthesised(cell) for cell in cells[:2]):
            raise ValueError('合并费用未明确以括号负数列示')
        if label == '财务(费用)/收入':
            if not all(_value(cell) >= 0 and not cell.startswith('(') for cell in cells[2:]):
                raise ValueError('财务费用/收入的公司列符号证据不明确')
        elif not all(parenthesised(cell) or cell in ('-', '—', '–', '0') for cell in cells[2:]):
            raise ValueError('公司费用列未按同一带符号方式列示')
        positions.append(start)
        evidence.append(dict(label=label, raw_values=cells,
            values=[str(_value(cell)) for cell in cells],
            pages=dict(start=page_numbers[start], end=page_numbers[end - 1]),
            excerpt=' ｜ '.join(lines[start:end])))
    if positions != sorted(positions):
        raise ValueError('费用符号依据的行顺序不明确')
    tax_cells = tax_row.get('raw_values', [])
    tax_notes = tax_row.get('notes', [])
    if (tax_row.get('label') != '减：所得税费用' or len(tax_cells) != 4
            or len(tax_notes) != 1 or len(tax_notes[0].split()) != 1
            or not all(re.fullmatch(r'\([\d,，.]+\)', cell) and _value(cell) < 0 for cell in tax_cells)):
        raise ValueError('带符号费用版式的所得税行不完整或符号不一致')
    span = tax_row.get('_line_span')
    if (span is None or page_numbers[span[0]] != page_numbers[span[1]]
            or span[1] + 1 >= len(lines) or page_numbers[span[1] + 1] == page_numbers[span[1]]):
        raise ValueError('跨页所得税行末尾含未知文字或未到完整页面边界')
    return dict(kind='explicit_four_column_signed_expenses',
        note='费用以括号负数、财务收入以正数列示；所得税沿用同一带符号列示，直接加至利润总额。方向取自原文格式，未通过试算选择。',
        evidence=evidence)
