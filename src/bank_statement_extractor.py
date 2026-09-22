"""Narrow, signed-million bank statements; no bank investment ratios.

Supports only the explicit two-year consolidated layout tested here. A match
with failed checks returns empty figures, never falls back to generic rows.
"""
import math
import re

from src.financial_statement_extractor import _chinese_label_matches, _extract_chinese_row_pair, _normalise_lines

BANK_TEMPLATE = 'bank_signed_million_v1'
_NEXT_STATEMENT = re.compile(
    r'(?:合\s*并|母\s*公\s*司|公\s*司|银\s*行)\s*'
    r'(?:资\s*产\s*负\s*债\s*表|利\s*润\s*表|现\s*金\s*流\s*量\s*表|'
    r'股\s*东\s*权\s*益\s*变\s*动\s*表)'
)


def _window(pages, heading, *, allow_continuation=False):
    for index, (number, text) in enumerate(pages):
        lines = _normalise_lines(text)
        if heading not in lines:
            continue
        after_heading = text.split(heading, 1)[1]
        # Contents pages list the same titles followed by page ranges. Only a
        # statement date or explicit unit header can open a parsing window.
        if not re.match(r'\s*(?:(?:19|20)\d{2}\s*年|单位|[（(]除特别注明外)', after_heading):
            continue
        pieces = []
        end = number
        for offset, (page, content) in enumerate(pages[index:index + 3]):
            if page != number + offset:
                return None
            part = content.split(heading, 1)[1] if offset == 0 else content
            if offset and allow_continuation:
                # Only the exact same statement's explicitly marked continuation
                # may cross a page boundary; parent/bank-only tables still stop.
                part = re.sub(r'^' + re.escape(heading) + r'[（(]续[）)]\s*$',
                              '', part, count=1, flags=re.MULTILINE)
            stop = _NEXT_STATEMENT.search(part)
            if stop:
                part = part[:stop.start()]
                if allow_continuation and offset and not re.search(r'\d', part):
                    # A following statement's company-name prefix is not a
                    # continuation page and supplies no financial evidence.
                    part = ''
            if part.strip():
                pieces.append(part)
                end = page
            if stop:
                break
        return number, end, '\n'.join(pieces)
    return None


def extract_bank_statements(pages, report_year):
    """Return None for a nonmatch; matching but invalid layouts fail closed."""
    income = _window(pages, '合并利润表')
    if not income:
        return None
    compact_income = re.sub(r'\s+', '', income[2])
    income_lines = _normalise_lines(income[2])
    # Recognition is broader than extraction: unsupported bank statements must
    # retain the bank ratio policy, even if their revenue row lacks “合计”.
    def has_row(*labels):
        return any(_chinese_label_matches(line, label)
                   for line in income_lines for label in labels)
    if not (has_row('营业收入合计', '营业收入')
            and has_row('净手续费及佣金收入', '手续费及佣金净收入')
            and has_row('净利息收入', '利息净收入')):
        return None
    empty = dict(template=BANK_TEMPLATE, income=None, balance=None, cash=None,
        failure_reason='银行报表未通过当前模板的表头、必需科目或勾稽检查；未输出标准化金额，请核验原文。')
    if '本行股东的净利润' not in compact_income:
        from src.bank_group_note_extractor import extract_group_note_bank
        alternative = extract_group_note_bank(pages, report_year, _window)
        if alternative is not None:
            return dict(template=BANK_TEMPLATE, **alternative)
        from src.bank_unsigned_cash_extractor import extract_unsigned_cash_bank
        unsigned = extract_unsigned_cash_bank(pages, report_year, _window)
        if unsigned is not None:
            return dict(template=BANK_TEMPLATE, **unsigned)
        if '归属于母公司股东' in compact_income:
            return dict(empty, failure_reason='已识别银行合并利润表及归母利润字段，但当前版式尚未通过完整三表校验；未输出标准化金额，普通公司比例不适用。')
        return dict(empty, failure_reason='银行利润表未找到当前模板支持的“本行股东的净利润”独立行；不能用“净利润”自动替代归母利润。附注替代路径亦未通过完整检查，请人工核对口径、表头及勾稽关系。')
    windows = dict(income=income, balance=_window(pages, '合并资产负债表'),
                   cash=_window(pages, '合并现金流量表'))
    try:
        for window in windows.values():
            if not window:
                return empty
            lines = _normalise_lines(window[2])
            if '项目' not in lines:
                return empty
            unit_lines = {re.sub(r'\s+', '', line).replace(':', '：')
                          for line in lines[:lines.index('项目')]}
            if not unit_lines.intersection({
                '单位：人民币百万元',
                '（除特别注明外，货币单位均以人民币百万元列示）',
            }):
                return empty
            start = lines.index('项目') + 1
            # Inspect the actual column header, not the report date above it.
            # Balanced equations alone cannot detect swapped year columns.
            header_years = re.findall(r'(?:19|20)\d{2}年', ''.join(lines[start:start + 8]))
            if header_years != [f'{report_year}年', f'{report_year-1}年']:
                return empty

        def read(section, *labels):
            result = _extract_chinese_row_pair(_normalise_lines(windows[section][2]), labels)
            if result is None or not all(math.isfinite(v) for v in result):
                raise ValueError('missing row')
            return result

        def equal(left, *right):
            # Displayed integers in millions can differ by one rounding unit.
            if any(abs(left[i] - sum(r[i] for r in right)) > 1 for i in (0, 1)):
                raise ValueError('statement reconciliation failed')

        rev = read('income', '营业收入合计')
        interest = read('income', '净利息收入')
        equal(interest, read('income', '利息收入'), read('income', '利息支出'))
        fees = read('income', '净手续费及佣金收入')
        equal(fees, read('income', '手续费及佣金收入'), read('income', '手续费及佣金支出'))
        equal(rev, interest, fees, read('income', '其他净收入小计'))
        operating = read('income', '营业利润')
        expenses = read('income', '营业支出合计')
        if any(v > 0 for v in expenses):
            return empty
        equal(operating, rev, expenses)
        pretax = read('income', '利润总额')
        equal(pretax, operating, read('income', '加：营业外收入'), read('income', '减：营业外支出'))
        net = read('income', '净利润')
        equal(net, pretax, read('income', '减：所得税费用'))
        parent = read('income', '本行股东的净利润')
        equal(net, parent, read('income', '少数股东的净利润'))

        assets = read('balance', '资产合计')
        liabilities = read('balance', '负债合计')
        equity = read('balance', '股东权益合计')
        if any(v <= 0 for v in assets) or any(v < 0 for v in liabilities):
            return empty
        equal(assets, liabilities, equity)
        equal(assets, read('balance', '负债及股东权益总计'))

        flows = []
        for kind in ('经营', '投资', '筹资'):
            incoming = read('cash', kind + '活动现金流入小计')
            outgoing = read('cash', kind + '活动现金流出小计')
            if any(v < 0 for v in incoming) or any(v > 0 for v in outgoing):
                return empty
            net_flow = read('cash', kind + '活动产生的现金流量净额')
            equal(net_flow, incoming, outgoing)
            flows.append(net_flow)
        delta = read('cash', '现金及现金等价物净（减少）/增加额', '现金及现金等价物净增加额')
        equal(delta, *flows, read('cash', '汇率变动对现金及现金等价物的影响额'))
        opening = read('cash', '加：年初现金及现金等价物余额', '加：年初现金及现金等价物')
        closing = read('cash', '年末现金及现金等价物余额', '年末现金及现金等价物')
        equal(closing, opening, delta)

        def figures(section, values):
            result = dict(unit='人民币百万元', page_number=windows[section][0],
                          end_page_number=windows[section][1])
            for key, pair in values.items():
                result['current_' + key], result['previous_' + key] = pair
            return result
        return dict(template=BANK_TEMPLATE,
            income=figures('income', dict(revenue=rev, net_profit=parent)),
            balance=figures('balance', dict(total_assets=assets, total_liabilities=liabilities)),
            cash=figures('cash', dict(operating_cash_flow=flows[0])))
    except ValueError:
        return empty
