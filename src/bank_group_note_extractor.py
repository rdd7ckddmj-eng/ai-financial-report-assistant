"""Group-column bank statements with an explicit attributable-profit EPS note.

Narrow layout verified against Ping An Bank 2024/2025. Values are candidates only;
absence of minority interests is never inferred from an omitted statement row.
"""
import math
import re

from src.financial_statement_extractor import _extract_chinese_row_pair, _normalise_lines

UNIT = '(除特别注明外，金额单位均为人民币百万元)'
PARENT = '归属于母公司股东的本年净利润'
ORDINARY = '归属于母公司普通股股东的本年净利润'


def extract_group_note_bank(pages, year, window_reader):
    """Return None unless every required statement and note passes both years."""
    windows = {key: window_reader(pages, title, allow_continuation=True)
               for key, title in [('income', '合并利润表'),
                                  ('balance', '合并资产负债表'),
                                  ('cash', '合并现金流量表')]}
    try:
        for section, window in windows.items():
            if not window:
                return None
            # Validate each page header in the bounded window, including续页.
            for number, text in pages:
                if not window[0] <= number <= window[1]:
                    continue
                lines = _normalise_lines(text)
                if '本集团' not in lines or UNIT not in lines[:lines.index('本集团')]:
                    return None
                pos = lines.index('本集团')
                header = lines[pos + 1:pos + 4]
                suffix = '年12月31日' if section == 'balance' else '年度'
                if header != ['附注四', f'{year}{suffix}', f'{year-1}{suffix}']:
                    return None

        def read_text(text, *labels):
            pair = _extract_chinese_row_pair(_normalise_lines(text), labels)
            if pair is None or not all(math.isfinite(v) for v in pair):
                raise ValueError('missing explicit row')
            return pair

        def read(section, *labels):
            return read_text(windows[section][2], *labels)

        def equal(left, *right):
            if any(abs(left[i] - sum(r[i] for r in right)) > 1 for i in (0, 1)):
                raise ValueError('two-year reconciliation failed')

        revenue = read('income', '营业收入合计')
        interest = read('income', '利息净收入')
        fees = read('income', '手续费及佣金净收入')
        equal(interest, read('income', '利息收入'), read('income', '利息支出'))
        equal(fees, read('income', '手续费及佣金收入'), read('income', '手续费及佣金支出'))
        equal(revenue, interest, fees, *[read('income', label) for label in
              ('投资收益', '公允价值变动损益', '汇兑损益', '其他业务收入', '资产处置损益', '其他收益')])
        expenses = read('income', '营业支出合计')
        equal(expenses, read('income', '税金及附加'), read('income', '业务及管理费'))
        pre_impairment = read('income', '减值损失前营业利润')
        equal(pre_impairment, revenue, expenses)
        operating = read('income', '营业利润')
        equal(operating, pre_impairment, read('income', '信用减值损失'), read('income', '其他资产减值损失'))
        pretax = read('income', '利润总额')
        equal(pretax, operating, read('income', '加：营业外收入'), read('income', '减：营业外支出'))
        net = read('income', '净利润')
        equal(net, pretax, read('income', '减：所得税费用'))
        equal(net, read('income', '(一) 持续经营净利润'), read('income', '(二) 终止经营净利润'))

        # Only the explicitly headed basic-EPS table, never a general text or
        # quarterly/ordinary-shareholder figure. Multiple candidate notes reject.
        notes = []
        for number, text in pages:
            if '财务报表附注' not in text or UNIT not in _normalise_lines(text):
                continue
            marker = '基本每股收益具体计算如下：'
            if marker not in text:
                continue
            body = text.split(marker, 1)[1].split('(b)', 1)[0]
            lines = _normalise_lines(body)
            if lines[:2] != [f'{year}年度', f'{year-1}年度']:
                return None
            parent = read_text(body, PARENT)
            ordinary = read_text(body, ORDINARY)
            preferred = read_text(body, '减：母公司优先股宣告股息')
            perpetual = read_text(body, '母公司永续债利息')
            if any(v > 0 for v in (*preferred, *perpetual)):
                return None
            equal(ordinary, parent, preferred, perpetual)
            # This narrow layout has no minority-profit row. Require agreement
            # with an explicitly labelled parent figure; never derive it from net.
            equal(net, parent)
            notes.append((number, parent))
        if len(notes) != 1:
            return None
        note_page, parent = notes[0]

        assets = read('balance', '资产总计')
        liabilities = read('balance', '负债合计')
        if any(v <= 0 for v in assets) or any(v < 0 for v in liabilities):
            return None
        equal(assets, liabilities, read('balance', '股东权益合计'))
        equal(assets, read('balance', '负债及股东权益总计'))
        flows = []
        for kind in ('经营', '投资', '筹资'):
            incoming = read('cash', kind + '活动现金流入小计')
            outgoing = read('cash', kind + '活动现金流出小计')
            if any(v < 0 for v in incoming) or any(v > 0 for v in outgoing):
                return None
            flow = read('cash', kind + '活动产生的现金流量净额', kind + '活动使用的现金流量净额',
                        kind + '活动(使用)/产生的现金流量净额')
            equal(flow, incoming, outgoing)
            flows.append(flow)
        delta = read('cash', '现金及现金等价物净增加/(减少)额',
                     '现金及现金等价物净(减少)/增加额')
        equal(delta, *flows, read('cash', '汇率变动对现金及现金等价物的影响'))
        equal(read('cash', '年末现金及现金等价物余额'),
              read('cash', '加：年初现金及现金等价物余额'), delta)

        def figures(section, values):
            result = dict(unit='人民币百万元', page_number=windows[section][0],
                          end_page_number=windows[section][1])
            for key, pair in values.items():
                result['current_' + key], result['previous_' + key] = pair
            return result
        income = figures('income', dict(revenue=revenue, net_profit=parent))
        income['metric_sources'] = {'net_profit': dict(page_number=note_page,
            end_page_number=note_page, labels=[PARENT], statement='每股收益附注（归母利润）')}
        return dict(income=income,
                    balance=figures('balance', dict(total_assets=assets, total_liabilities=liabilities)),
                    cash=figures('cash', dict(operating_cash_flow=flows[0])))
    except ValueError:
        return None
