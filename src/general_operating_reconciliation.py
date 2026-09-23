"""Conservative, exhaustive arithmetic for a two-column direct income layout.

This deliberately does not infer blank amounts or generalise a total-revenue
layout into an operating-revenue layout. It is an additional evidence layer;
unsupported layouts retain the older tax/attribution checks with a scope note.
"""
from decimal import Decimal, InvalidOperation, localcontext
import re


_ALIASES = {
    'operating_revenue': ('营业收入',),
    'operating_cost': ('减：营业成本',),
    'operating_taxes': ('税金及附加',),
    'selling_expense': ('销售费用',),
    'administrative_expense': ('管理费用',),
    'research_expense': ('研发费用',),
    'financial_expense': ('财务费用',),
    'interest_expense_detail': ('其中：利息费用',),
    'interest_income_detail': ('利息收入',),
    'other_income': ('加：其他收益',),
    'investment_income': ('投资收益/(损失)', '投资收益',),
    'associate_income_detail': ('其中：对联营企业和合营企业的投资收益/(损失)',
        '其中：对联营企业和合营企业的投资收益', '其中：对联营企业的投资收益'),
    'derecognition_detail': ('以摊余成本计量的金融资产终止确认收益',
        '以摊余成本计量的金融资产终止确认损失'),
    'fair_value_income': ('公允价值变动收益(损失)', '公允价值变动收益'),
    'credit_impairment': ('信用减值利得(损失)', '信用减值损失'),
    'asset_impairment': ('资产减值利得(损失)', '资产减值损失'),
    'disposal_income': ('资产处置收益(损失)', '资产处置收益'),
    'operating_profit': ('营业利润',),
    'nonoperating_income': ('加：营业外收入',),
    'nonoperating_expense': ('减：营业外支出',),
    'profit_before_tax': ('利润总额',),
}
_COSTS = ('operating_cost', 'operating_taxes', 'selling_expense',
          'administrative_expense', 'research_expense', 'financial_expense')
_GAINS = ('other_income', 'investment_income', 'fair_value_income',
          'credit_impairment', 'asset_impairment', 'disposal_income')
_DETAILS = ('interest_expense_detail', 'interest_income_detail',
            'associate_income_detail', 'derecognition_detail')
_REQUIRED = ('operating_revenue',) + _COSTS + _GAINS + (
    'operating_profit', 'nonoperating_income', 'nonoperating_expense', 'profit_before_tax')
_ORDER = tuple(_ALIASES)


def check_direct_operating_reconciliation(lines, page_numbers, column_count, income, *, tolerance):
    """Consume the entire operating-revenue-to-pre-tax-profit window.

    The caller already validated the consolidated scope, period headings,
    units and annual-report identity. All values are in those original units.
    Missing/unknown rows cannot be silently skipped, even if arithmetic would
    balance without them. The explicit child rows are never added twice.
    """
    # Local import avoids a module cycle with the owning reconciliation hook.
    from src.general_income_reconciliation import (
        _compact, _financial_line, _match_label, _value,
    )

    result = dict(status='unsupported_layout', passed=False, checks=[], evidence={},
        unit=income.get('unit', ''), pages=None, tolerance=str(tolerance),
        note='营业收入至税前利润的增强检查尚未支持该版式；仍仅展示已有税后与利润归属检查。')
    if column_count != 2:
        result['note'] = '四列或非两列版式未执行经营分项增强检查；不据此宣称全利润表勾稽通过。'
        return result
    if any(re.search(r'营业总收入|营业总成本', _compact(line)) for line in lines):
        result['note'] = '营业总收入/总成本版式未执行直接列示经营分项检查，不能把营业收入替代营业总收入。'
        return result
    def positions(label):
        found = []; cursor = 0
        while cursor < len(lines):
            match = _match_label(lines, cursor, label)
            if match is not None:
                found.append(cursor)
                cursor = match[0] + 1
            else:
                cursor += 1
        return found

    starts = positions('营业收入')
    ends = positions('利润总额')
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        result.update(status='missing_evidence', note='经营分项窗口的营业收入或利润总额行缺失、重复或顺序不明确。')
        return result

    has_note_header = any(re.fullmatch(r'(?:项目)?附注[一二三四五六七八九十百]*(?:\d{4}年(?:度)?)*',
        _compact(line)) for line in lines[:starts[0]])
    # Integer note references require an explicit note column. A three-cell
    # row without this header is an extra monetary cell, never an assumed note.
    def match_row(index):
        for key, aliases in _ALIASES.items():
            for label in aliases:
                match = _match_label(lines, index, label, compact_notes=has_note_header)
                if match is not None:
                    return key, label, match
        return None

    try:
        rows = {}; cursor = starts[0]; last_order = -1
        result['evidence'] = rows
        while cursor <= ends[0]:
            match = match_row(cursor)
            if match is None:
                raise ValueError('经营分项中有未识别科目、页眉或金额行，未将其省略')
            key, label, (end, tail) = match
            if key in rows:
                raise ValueError('经营分项中同一科目重复出现：' + label)
            order = _ORDER.index(key)
            if order <= last_order:
                raise ValueError('经营分项或其子项的先后关系不明确：' + label)
            last_order = order
            pieces = []; notes = []; last = end
            pending = ([(tail, end)] if tail else [])
            next_line = end + 1
            # Read the full cells, not only the first two. An extra cell must
            # cause rejection, including on the final pre-tax-profit row.
            while pending or next_line < len(lines):
                text, number = pending.pop(0) if pending else (lines[next_line], next_line)
                if number == next_line:
                    next_line += 1
                parsed = _financial_line(text, compact_notes=has_note_header)
                if parsed is None:
                    # Next text is processed as a row on the next iteration;
                    # unknown/malformed text therefore cannot end a row safely.
                    next_line = number
                    break
                amounts, is_note = parsed
                if is_note:
                    if pieces or notes:
                        raise ValueError('附注重复或出现在金额列之后')
                    notes.append(text)
                pieces.extend(amounts)
                last = number
            if (has_note_header and key not in ('operating_profit', 'profit_before_tax')
                    and len(pieces) == 3 and not notes
                    and re.fullmatch(r'[1-9]\d{0,2}', pieces[0])):
                notes.append(pieces.pop(0))
            if len(pieces) != 2:
                raise ValueError('经营分项不是完整的本期/比较期两列：' + label)
            values = tuple(_value(token) for token in pieces)
            # Preserve the next boundary: a damaged number after two valid
            # cells is not allowed to disappear after the last required row.
            if next_line < len(lines):
                token = _compact(lines[next_line])
                if (re.match(r'^[+\-—–(.,\d]', token) and re.search(r'\d', token)
                        and not re.search(r'[\u4e00-\u9fff]', token)) or re.fullmatch(
                        r'(?:不适用|无数据|N/?A|NAN|NULL|NONE)', token, re.IGNORECASE):
                    raise ValueError('金额列后存在损坏或额外的数值')
            rows[key] = dict(label=label, values=[str(value) for value in values],
                pages=dict(start=page_numbers[cursor], end=page_numbers[last]),
                excerpt=' ｜ '.join(lines[cursor:last + 1]), notes=notes,
                coefficient=(-1 if key in _COSTS or key == 'nonoperating_expense'
                    else 0 if key in _DETAILS or key in ('operating_profit', 'profit_before_tax') else 1),
                role='已包含于上级科目，不重复加总' if key in _DETAILS else '公式金额或校验目标')
            if key == 'profit_before_tax':
                # Stop only at the existing tax row, not arbitrary extra
                # business items hidden between pre-tax profit and income tax.
                if next_line >= len(lines) or _match_label(lines, next_line, '减：所得税费用',
                        compact_notes=has_note_header) is None:
                    raise ValueError('利润总额之后未紧接明确的所得税费用行')
                cursor = next_line
                break
            cursor = next_line
        result['evidence'] = rows
        missing = [key for key in _REQUIRED if key not in rows]
        if missing:
            raise ValueError('必需经营科目缺失，未补零：' + '、'.join(_ALIASES[key][0] for key in missing))
        result['pages'] = dict(start=page_numbers[starts[0]], end=rows['profit_before_tax']['pages']['end'])

        def value(key, index):
            return Decimal(rows[key]['values'][index])

        def add_check(key, label, calculate, allowed):
            item = dict(key=key, label=label, passed=False)
            for period, index in (('current', 0), ('previous', 1)):
                with localcontext() as ctx:
                    ctx.prec = 50
                    left, right = calculate(index)
                    difference = left - right
                item[period] = dict(left=str(left), right=str(right), difference=str(difference),
                                    passed=abs(difference) <= allowed)
            item['passed'] = item['current']['passed'] and item['previous']['passed']
            result['checks'].append(item)

        revenue = []
        for field in ('current_revenue', 'previous_revenue'):
            supplied = income.get(field)
            if supplied is None or isinstance(supplied, bool):
                raise ValueError('快照输出营业收入缺失或无效')
            amount = Decimal(str(supplied))
            if not amount.is_finite() or abs(amount) > Decimal('1e24'):
                raise ValueError('快照输出营业收入无效')
            revenue.append(amount)
        allowed = Decimal(str(tolerance))
        add_check('operating_profit_components', '合并：营业收入减成本费用加各项收益等于营业利润',
            lambda i: (value('operating_revenue', i) - sum(value(k, i) for k in _COSTS)
                       + sum(value(k, i) for k in _GAINS), value('operating_profit', i)), allowed)
        add_check('operating_to_profit_before_tax', '合并：营业利润加营业外收入减营业外支出等于利润总额',
            lambda i: (value('operating_profit', i) + value('nonoperating_income', i)
                       - value('nonoperating_expense', i), value('profit_before_tax', i)), allowed)
        add_check('selected_operating_revenue', '输出营业收入与原文营业收入行一致',
            lambda i: (value('operating_revenue', i), revenue[i]), Decimal('.01'))
        result['passed'] = all(item['passed'] for item in result['checks'])
        result['status'] = 'passed' if result['passed'] else 'mismatch'
        result['note'] = ('两期直接列示经营分项至营业利润、营业外收支至税前利润及输出营业收入通过检查；'
            '减值行保留原文正负号，利息与投资收益的明细未重复加总。这不是完整财务审计。'
            if result['passed'] else '已取得完整经营分项，但营业利润、税前利润或输出营业收入与原文存在不一致。')
    except (ValueError, InvalidOperation, IndexError, TypeError) as exc:
        result.update(status='missing_evidence', passed=False, checks=[],
            note='经营分项增强检查未完成：' + str(exc) + '；缺失和歧义金额未补零，未宣称增强检查通过。')
    return result
