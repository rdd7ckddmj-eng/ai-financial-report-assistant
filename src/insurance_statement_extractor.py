"""Conservative Ping An consolidated million-yuan template (2024 fixture).

Only explicit two-year columns and signed expenses are supported. All three
statements must reconcile; no general-company fallback is permitted.
"""
from decimal import Decimal
import re
from src.financial_statement_extractor import _normalise_lines

INSURANCE_TEMPLATE = 'insurance_signed_million_v1'
UNIT = '（除特别注明外，金额单位为人民币百万元）'
END = '后附财务报表附注为财务报表的组成部分。'
TITLES = {'income': '合并利润表', 'balance': '合并资产负债表', 'cash': '合并现金流量表'}
NUMBER = re.compile(r'(?:[–—-]|-?\d[\d,]*|\(\d[\d,]*\))')
NOTE = re.compile(r'\d{1,2}(?:\(\d+\))*')
ROW_NOTES = dict(zip(
    ('保险服务收入', '银行业务利息净收入', '银行业务利息收入', '银行业务利息支出',
     '非保险业务手续费及佣金净收入', '非保险业务手续费及佣金收入', '非保险业务手续费及佣金支出',
     '非银行业务利息收入', '投资收益', '公允价值变动损益', '其他业务收入', '保险服务费用',
     '承保财务损益', '税金及附加', '业务及管理费', '其他业务成本', '其他资产减值损失',
     '信用减值损失', '加：营业外收入', '减：营业外支出', '减：所得税费用', '少数股东权益',
     '经营活动产生的现金流量净额', '五、现金及现金等价物净（减少）╱增加额', '六、年末现金及现金等价物余额'),
    ('42','43','43','43','44','44','44','45','46','47','48','49','31(5)','50','51(1)','51(2)',
     '52','53','54','55','56','41','59(1)','59(2)','59(5)')))


def _window(pages, section, year):
    title = TITLES[section]
    suffix = '年12月31日' if section == 'balance' else '年度'
    columns = [f'{year}{suffix}', f'{year-1}{suffix}']
    candidates = []
    for i, (number, text) in enumerate(pages):
        lines = _normalise_lines(text)
        if lines and lines[0] == '目录':
            continue
        if title not in lines:
            continue
        # A repeated heading on the next balance page belongs to the same table.
        if i and pages[i-1][0] == number-1 and title in _normalise_lines(pages[i-1][1]):
            continue
        body = []
        complete = False
        for offset, (page, text) in enumerate(pages[i:i+3]):
            lines = _normalise_lines(text)
            if page != number+offset:
                raise ValueError('nonconsecutive pages')
            headings = [x for x in lines if re.fullmatch(r'.*(?:资产负债表|利润表|现金流量表)', x)]
            if any(x != title for x in headings):
                raise ValueError('mixed statements')
            if offset == 0 and UNIT not in lines:
                raise ValueError('missing unit')
            if any('金额单位' in x and x != UNIT for x in lines):
                raise ValueError('conflicting unit')
            pos = lines.index('附注八')
            if lines[pos+1:pos+3] != columns:
                raise ValueError('year columns')
            part = lines[pos+3:]
            if END in part:
                part = part[:part.index(END)]
                complete = True
            body.extend((page, x) for x in part)
            if complete:
                break
        if not complete:
            raise ValueError('unbounded statement')
        candidates.append(body)
    if len(candidates) != 1:
        raise ValueError('missing or duplicate statement')
    return candidates[0]


def _read(window, label):
    matches = []
    for i, (page, line) in enumerate(window):
        if line != label:
            continue
        cells = []
        for _, value in window[i+1:i+5]:
            if not NUMBER.fullmatch(value) and not NOTE.fullmatch(value):
                break
            cells.append(value)
        if len(cells) == 3 and cells[0] == ROW_NOTES.get(label):
            cells = cells[1:]
        if len(cells) != 2:
            raise ValueError('ambiguous cells: '+label)
        def parse(v):
            if v in ('–', '—', '-'):
                return Decimal(0)
            return Decimal(v.strip('()').replace(',', '')) * (-1 if v.startswith('(') else 1)
        matches.append((tuple(map(parse, cells)), page))
    if len(matches) != 1:
        raise ValueError('missing or duplicate row: '+label)
    return matches[0]


def extract_insurance_statements(pages, year):
    try:
        windows = {key: _window(pages, key, year) for key in TITLES}
        def read(section, label):
            return _read(windows[section], label)[0]
        def equal(left, *parts):
            # Integer million-yuan table: permit at most one displayed unit.
            if any(abs(left[i]-sum(p[i] for p in parts)) > 1 for i in (0, 1)):
                raise ValueError('reconciliation')
        revenue = read('income', '营业收入合计')
        equal(revenue, *[read('income', x) for x in ('保险服务收入','银行业务利息净收入','非保险业务手续费及佣金净收入','非银行业务利息收入','投资收益','公允价值变动损益','汇兑损益','其他业务收入','资产处置损益','其他收益')])
        for prefix in ('银行业务利息', '非保险业务手续费及佣金'):
            equal(read('income', prefix+'净收入'), read('income', prefix+'收入'), read('income', prefix+'支出'))
        expenses = read('income', '营业支出合计')
        if any(v > 0 for v in expenses):
            raise ValueError('unsigned expenses')
        equal(expenses, *[read('income', x) for x in ('保险服务费用','分出保费的分摊','减：摊回保险服务费用','承保财务损益','减：分出再保险财务损益','税金及附加','业务及管理费','提取保费准备金','非银行业务利息支出','其他业务成本','其他资产减值损失','信用减值损失')])
        operating = read('income', '三、营业利润'); equal(operating, revenue, expenses)
        pretax = read('income', '四、利润总额'); equal(pretax, operating, read('income', '加：营业外收入'), read('income', '减：营业外支出'))
        net = read('income', '五、净利润'); equal(net, pretax, read('income', '减：所得税费用'))
        parent = read('income', '归属于母公司股东的净利润'); equal(net, parent, read('income', '少数股东损益'))
        assets = read('balance', '资产总计'); liabilities = read('balance', '负债合计'); equity = read('balance', '股东权益合计')
        if any(v <= 0 for v in assets) or any(v < 0 for v in liabilities):
            raise ValueError('invalid balance')
        equal(assets, liabilities, equity); equal(assets, read('balance', '负债和股东权益总计'))
        equal(equity, read('balance', '归属于母公司股东权益合计'), read('balance', '少数股东权益'))
        flows = []
        labels = ('经营活动产生的现金流量净额', '投资活动使用的现金流量净额', '筹资活动产生╱（使用）的现金流量净额')
        for kind, label in zip(('经营', '投资', '筹资'), labels):
            incoming = read('cash', kind+'活动现金流入小计'); outgoing = read('cash', kind+'活动现金流出小计')
            if any(v < 0 for v in incoming) or any(v > 0 for v in outgoing):
                raise ValueError('cash signs')
            flow = read('cash', label); equal(flow, incoming, outgoing); flows.append(flow)
        delta = read('cash', '五、现金及现金等价物净（减少）╱增加额')
        equal(delta, *flows, read('cash', '四、汇率变动对现金及现金等价物的影响'))
        equal(read('cash', '六、年末现金及现金等价物余额'), read('cash', '加：年初现金及现金等价物余额'), delta)
        def figures(section, metrics):
            window = windows[section]
            result = dict(unit='人民币百万元', page_number=window[0][0], end_page_number=window[-1][0], metric_sources={})
            for key, label in metrics.items():
                values, page = _read(window, label)
                result['current_'+key], result['previous_'+key] = map(float, values)
                result['metric_sources'][key] = dict(page_number=page, end_page_number=page, labels=[label], statement='保险集团合并报表')
            return result
        return dict(income=figures('income', dict(revenue='营业收入合计', net_profit='归属于母公司股东的净利润')),
                    balance=figures('balance', dict(total_assets='资产总计', total_liabilities='负债合计')),
                    cash=figures('cash', dict(operating_cash_flow=labels[0])))
    except (ValueError, IndexError):
        return None
