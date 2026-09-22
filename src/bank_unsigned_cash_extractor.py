"""Narrow bank layout: signed income expenses, unsigned cash outflows.

Validated on Bank of Ningbo 2024/2025. All figures remain review candidates.
"""
import math
import re
from src.financial_statement_extractor import _extract_chinese_row_pair, _normalise_lines


def extract_unsigned_cash_bank(pages, year, window_reader):
    windows = {key: window_reader(pages, title, allow_continuation=True)
               for key, title in [('income', '合并利润表'),
                                  ('balance', '合并资产负债表'),
                                  ('cash', '合并现金流量表')]}
    try:
        for section, window in windows.items():
            if not window:
                return None
            for number, text in pages:
                if not window[0] <= number <= window[1]:
                    continue
                lines = [re.sub(r'\s+', '', line) for line in _normalise_lines(text)]
                if '附注五' not in lines:
                    return None
                pos = lines.index('附注五')
                if '人民币百万元' not in lines[:pos]:
                    return None
                suffix = '年12月31日' if section == 'balance' else '年度'
                if lines[pos+1:pos+3] != [f'{year}{suffix}', f'{year-1}{suffix}']:
                    return None
                if re.match(r'(?:19|20)\d{2}年', lines[pos+3]):
                    return None

        def read(section, *labels):
            pair = _extract_chinese_row_pair(_normalise_lines(windows[section][2]), labels)
            if pair is None or not all(math.isfinite(v) for v in pair):
                raise ValueError('missing row')
            return pair

        def equal(left, *right):
            # One displayed million is a rounding tolerance, not an audit threshold.
            if any(abs(left[i] - sum(r[i] for r in right)) > 1 for i in (0, 1)):
                raise ValueError('two-year reconciliation failed')

        revenue = read('income', '营业收入')
        interest = read('income', '利息净收入')
        fees = read('income', '手续费及佣金净收入')
        equal(interest, read('income', '利息收入'), read('income', '利息支出'))
        equal(fees, read('income', '手续费及佣金收入'), read('income', '手续费及佣金支出'))
        equal(revenue, interest, fees, *[read('income', label) for label in
              ('投资收益', '其他收益', '公允价值变动损益', '汇兑损益', '其他业务收入', '资产处置收益')])
        expenses = read('income', '营业支出')
        if any(v > 0 for v in expenses):
            return None
        equal(expenses, *[read('income', label) for label in
              ('税金及附加', '业务及管理费', '信用减值损失', '其他业务成本')])
        operating = read('income', '营业利润')
        equal(operating, revenue, expenses)
        pretax = read('income', '利润总额')
        equal(pretax, operating, read('income', '营业外收入'), read('income', '营业外支出'))
        net = read('income', '净利润')
        equal(net, pretax, read('income', '所得税费用'))
        parent_label = '其中：归属于母公司股东的净利润'
        parent = read('income', parent_label)
        equal(net, parent, read('income', '少数股东损益'))

        assets = read('balance', '资产总计')
        liabilities = read('balance', '负债合计')
        equity = read('balance', '股东权益合计')
        if any(v <= 0 for v in assets) or any(v < 0 for v in liabilities):
            return None
        equal(equity, read('balance', '归属于母公司股东的权益'), read('balance', '少数股东权益'))
        equal(assets, liabilities, equity)
        equal(assets, read('balance', '负债及股东权益总计'))
        flows = []
        for kind in ('经营', '投资', '筹资'):
            incoming = read('cash', kind + '活动现金流入小计')
            outgoing = read('cash', kind + '活动现金流出小计')
            if any(v < 0 for v in (*incoming, *outgoing)):
                return None
            flow = read('cash', kind + '活动产生的现金流量净额', kind + '活动使用的现金流量净额',
                        kind + '活动产生/(使用)的现金流量净额')
            # This layout prints outflows as positive magnitudes; never abs()
            # an unexpected negative value, which could conceal a wrong layout.
            equal(flow, incoming, tuple(-v for v in outgoing))
            flows.append(flow)
        delta = read('cash', '本年现金及现金等价物净增加额')
        equal(delta, *flows, read('cash', '汇率变动对现金及现金等价物的影响额'))
        equal(read('cash', '年末现金及现金等价物余额'),
              read('cash', '加：年初现金及现金等价物余额'), delta)

        def figures(section, values, sources=None):
            result = dict(unit='人民币百万元', page_number=windows[section][0],
                          end_page_number=windows[section][1])
            for key, pair in values.items():
                result['current_' + key], result['previous_' + key] = pair
            if sources:
                result['metric_sources'] = {key: dict(page_number=windows[section][0],
                    end_page_number=windows[section][1], labels=[label], statement='利润表')
                    for key, label in sources.items()}
            return result
        return dict(income=figures('income', dict(revenue=revenue, net_profit=parent),
                                   dict(revenue='营业收入', net_profit=parent_label)),
                    balance=figures('balance', dict(total_assets=assets, total_liabilities=liabilities)),
                    cash=figures('cash', dict(operating_cash_flow=flows[0])))
    except (ValueError, IndexError):
        return None
