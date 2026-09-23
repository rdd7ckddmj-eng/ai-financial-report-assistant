"""Verified PICC 2024 and CPIC/NCI 2024–2025 issuer-specific layouts.

These profiles do not imply all insurance reports are supported. We validate
both years (and NCI's parent columns) before returning consolidated candidates.
"""
from decimal import Decimal
from copy import deepcopy
import re

TEMPLATES = {
    '601319': 'insurance_picc_million_v1',
    '601601': 'insurance_cpic_million_v1',
    '601336': 'insurance_nci_four_column_v1',
}
TOTAL_REVENUE_TEMPLATES = frozenset(TEMPLATES[c] for c in ('601319', '601601'))
VERIFIED_YEARS = {'601319': frozenset({2024}),
                  '601601': frozenset({2024, 2025}),
                  '601336': frozenset({2024, 2025})}
TITLES = dict(balance='资产负债表', income='利润表', cash='现金流量表')
END = '后附财务报表附注为本财务报表的组成部分'
INTEGER = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
NUMBER = re.compile(rf'(?:[－–—-]|-?{INTEGER}|\({INTEGER}\))')
NOTE = re.compile(r'\d{1,2}(?:\(\d+\))?(?:[/、]\d{1,2}(?:\(\d+\))?)*')


def _compact(value):
    return re.sub(r'\s+', '', value).translate(str.maketrans('（）／╱', '()//'))


def _lines(text):
    lines = [v for line in text.splitlines() if (v := _compact(line))]
    # An NCI subrow wraps before 投资收益; keep it distinct from the main row.
    return '\n'.join(lines).replace('其中：对联营企业和合营企业的\n投资收益', '其中：对联营企业和合营企业的投资收益').splitlines()


# Row-note identifiers are checked, not guessed from a small numeric first cell.
PROFILES = {
    '601319': dict(header='附注七', unit='除另有注明外，金额单位均为人民币百万元',
        revenue='一、营业总收入', expenses='二、营业总支出', expense_sign=1,
        revenue_parts=['保险服务收入','利息收入','投资收益','其他收益','公允价值变动损益','汇兑收益','其他业务收入','资产处置收益'],
        expense_parts=['保险服务费用','分出保费的分摊','减：摊回保险服务费用','承保财务损失','减：分出再保险财务收益','转回提取保费准备金','利息支出','税金及附加','业务及管理费','信用减值(转回)/损失','其他资产减值损失','其他业务成本'],
        parent_profit='1.归属于母公司股东的净利润', minority_profit='2.少数股东损益',
        investment='投资活动使用的现金流量净额', financing='筹资活动产生/(使用)的现金流量净额',
        delta='五、现金及现金等价物净增加/(减少)额', tax='减：所得税费用',
        notes={'保险服务收入':'34','利息收入':'35','投资收益':'36','其他收益':'37','公允价值变动损益':'38','其他业务收入':'39','承保财务损失':'40','利息支出':'41','业务及管理费':'42','信用减值(转回)/损失':'43','加：营业外收入':'44','减：营业外支出':'44','减：所得税费用':'45','少数股东权益':'33','经营活动产生的现金流量净额':'48(1)','五、现金及现金等价物净增加/(减少)额':'48(2)','六、年末现金及现金等价物余额':'49'}),
    '601601': dict(header='附注六', unit='除特别注明外，金额单位均为人民币百万元',
        revenue='一、营业总收入', expenses='二、营业总支出', expense_sign=-1,
        revenue_parts=['保险服务收入','利息收入','投资收益','其他收益','公允价值变动收益/(损失)','汇兑(损失)/收益','其他业务收入','资产处置收益'],
        expense_parts=['保险服务费用','分出保费的分摊','减：摊回保险服务费用','承保财务损失','减：分出再保险财务收益','提取保费准备金','利息支出','手续费及佣金支出','税金及附加','业务及管理费','信用减值损失','其他资产减值损失','其他业务成本'],
        parent_profit='归属于母公司股东的净利润', minority_profit='少数股东损益',
        investment='投资活动使用的现金流量净额', financing='筹资活动产生的现金流量净额',
        delta='五、现金及现金等价物净增加/(减少)额', tax='减：所得税',
        notes={'保险服务收入':'33','利息收入':'34','投资收益':'35','公允价值变动收益/(损失)':'36','其他业务收入':'37','资产处置收益':'38','承保财务损失':'39','减：分出再保险财务收益':'39','利息支出':'40','税金及附加':'41','业务及管理费':'42','信用减值损失':'43','其他业务成本':'44','加：营业外收入':'45','减：营业外支出':'46','减：所得税':'47','少数股东权益':'32','经营活动产生的现金流量净额':'52','五、现金及现金等价物净增加/(减少)额':'52','加：年初现金及现金等价物余额':'51、52','六、年末现金及现金等价物余额':'51、52'}),
    '601336': dict(header='附注', unit='除特别注明外，金额单位为人民币百万元',
        revenue='一、营业收入', expenses='二、营业支出', expense_sign=-1,
        revenue_parts=['保险服务收入','利息收入','投资收益','公允价值变动损益','汇兑收益','其他收益','其他业务收入'],
        expense_parts=['保险服务费用','分出保费的分摊','减：摊回保险服务费用','承保财务损失','减：分出再保险财务收益','利息支出','税金及附加','业务及管理费','信用减值损失','其他资产减值损失','其他业务成本'],
        parent_profit='归属于母公司股东的净利润', minority_profit='少数股东损益',
        investment='投资活动产生的现金流量净额', financing='筹资活动产生的现金流量净额',
        delta='五、现金及现金等价物净增加额', tax='减：所得税费用',
        notes={'保险服务收入':'38','利息收入':'39/54(4)','投资收益':'40/54(5)','公允价值变动损益':'41','其他收益':'42','保险服务费用':'43','承保财务损失':'44','减：分出再保险财务收益':'44','税金及附加':'45','业务及管理费':'45','信用减值损失':'46','其他资产减值损失':'47','其他业务成本':'45','减：所得税费用':'48','经营活动产生的现金流量净额':'51(1)/54(6)','五、现金及现金等价物净增加额':'51(2)/54(6)','六、年末现金及现金等价物余额':'51(3)/54(6)'}),
}


def _profile(code, year):
    """Keep changed row labels and note numbers scoped to an observed year."""
    profile = deepcopy(PROFILES[code])
    if year == 2025 and code == '601601':
        replacements = {'公允价值变动收益/(损失)': '公允价值变动收益',
                        '汇兑(损失)/收益': '汇兑损失',
                        profile['delta']: '五、现金及现金等价物净增加额'}
        profile['revenue_parts'] = [replacements.get(x, x) for x in profile['revenue_parts']]
        profile['delta'] = replacements[profile['delta']]
        profile['notes'] = {replacements.get(k, k): v for k, v in profile['notes'].items()}
    if year == 2025 and code == '601336':
        profile['revenue_parts'] = ['汇兑损益' if x == '汇兑收益' else x for x in profile['revenue_parts']]
        profile['notes'] = {
            '保险服务收入':'39', '利息收入':'40/56(4)', '投资收益':'41/56(5)',
            '公允价值变动损益':'42', '其他收益':'43', '保险服务费用':'44',
            '承保财务损失':'45', '减：分出再保险财务收益':'45',
            '税金及附加':'46', '业务及管理费':'46', '信用减值损失':'47',
            '其他资产减值损失':'48', '其他业务成本':'46', '加：营业外收入':'49',
            '减：所得税费用':'50', '经营活动产生的现金流量净额':'53(1)/56(6)',
            '五、现金及现金等价物净增加额':'53(2)/56(6)',
            '六、年末现金及现金等价物余额':'53(3)/56(6)',
        }
    return profile


def _window(pages, section, year, code):
    profile = _profile(code, year)
    nci = code == '601336'
    title = ('合并及公司' if nci else '合并') + TITLES[section]
    starts = [i for i, (_, t) in enumerate(pages)
              if title in _lines(t) and profile['header'] in _lines(t)]
    if len(starts) != 1:
        raise ValueError('missing or duplicate statement')
    start = starts[0]
    count = 4 if nci else 2
    length = 1 if code == '601601' and section == 'cash' else 2
    columns = []
    for y in [year, year-1] * (2 if nci else 1):
        if section == 'balance':
            columns.extend([f'{y}年', '12月31日'] if nci or code == '601601' else [f'{y}年12月31日'])
        else:
            columns.append(f'{y}年' if code == '601601' else f'{y}年度')
    rows = []
    for offset in range(length):
        page, text = pages[start+offset]
        if page != pages[start][0]+offset:
            raise ValueError('nonconsecutive pages')
        lines = _lines(text)
        headings = [x for x in lines if re.fullmatch(r'.*(?:资产负债表|利润表|现金流量表)(?:\(续\))?', x)]
        expected = title if offset == 0 else title+'(续)'
        if (offset == 0 or not nci) and (not headings or any(x != expected for x in headings)):
            raise ValueError('wrong statement title')
        if nci and offset and headings:
            raise ValueError('unverified continuation')
        units = [x for x in lines if '金额单位' in x]
        if (offset == 0 or not nci) and len(units) != 1:
            raise ValueError('missing unit')
        if any(not x.endswith('('+profile['unit']+')') for x in units):
            raise ValueError('conflicting unit')
        if lines.count(profile['header']) != 1:
            raise ValueError('ambiguous column header')
        pos = lines.index(profile['header'])
        if nci and lines[pos-3:pos] != ['合并','公司','资产' if offset == 0 else '负债及股东权益'] and section == 'balance':
            raise ValueError('group/parent order')
        if nci and section != 'balance' and lines[pos-2:pos] != ['合并','公司']:
            raise ValueError('group/parent order')
        if lines[pos+1:pos+1+len(columns)] != columns:
            raise ValueError('year columns')
        tail = lines[pos+1+len(columns):]
        first_rows = {
            'balance': (('资产', '负债和股东权益') if code == '601319'
                        else ('货币资金', '交易性金融负债' if nci else '衍生金融负债')),
            'income': (profile['revenue'], '五、净利润'),
            'cash': ('一、经营活动产生的现金流量',
                     '三、筹资活动产生/(使用)的现金流量' if code == '601319'
                     else '三、筹资活动产生的现金流量'),
        }
        if not tail or tail[0] != first_rows[section][offset]:
            raise ValueError('extra or unverified column header')
        # NCI's 2025 income/cash PDF stores the visual footer before the header
        # in its text layer. Bound it by the physical page and exact header;
        # allow this ordering only for the observed issuer/year/sections.
        prefix_footer = nci and year == 2025 and section in {'income', 'cash'}
        endings = [i for i,x in enumerate(lines) if x.rstrip('。.') == END]
        if len(endings) != 1:
            raise ValueError('unbounded statement')
        if prefix_footer:
            if endings[0] >= pos:
                raise ValueError('unverified footer order')
            part = tail
        else:
            if endings[0] < pos+1+len(columns):
                raise ValueError('unverified footer order')
            part = lines[pos+1+len(columns):endings[0]]
        # NCI wraps this exact label; do not concatenate arbitrary rows.
        if nci:
            part = ('\n'.join(part)
                    .replace('归属于母公司股东的\n股东权益合计','归属于母公司股东的股东权益合计')
                    .replace('归属于母公司股东的股东\n权益合计','归属于母公司股东的股东权益合计')
                    .splitlines())
        rows.extend((page, x) for x in part)
    return dict(rows=rows, columns=count, profile=profile, nci=nci)


def _read(window, label):
    rows, count = window['rows'], window['columns']
    matches = []
    for i, (page, text) in enumerate(rows):
        if text != label:
            continue
        cells = []
        for _, value in rows[i+1:i+count+3]:
            if not (NUMBER.fullmatch(value) or NOTE.fullmatch(value) or value == '/'):
                # An extra malformed/decimal/N/A cell is still a column, not a
                # row boundary. Only a text label may terminate a numeric row.
                if not re.search(r'[\u4e00-\u9fff]', value) or value in {'不适用', '无'}:
                    raise ValueError('invalid amount or extra column: '+label)
                break
            cells.append(value)
        expected_note = window['profile']['notes'].get(label)
        if len(cells) == count+1 and expected_note and cells[0] == expected_note:
            cells = cells[1:]
        if len(cells) != count:
            raise ValueError('ambiguous cells: '+label)
        values = []
        for col, cell in enumerate(cells):
            if cell == '/':
                if not window['nci'] or col < 2 or label not in {'归属于母公司股东的净利润','少数股东损益','少数股东权益'}:
                    raise ValueError('unexpected N/A')
                values.append(None)  # Never treat not-applicable as zero.
            elif not NUMBER.fullmatch(cell):
                raise ValueError('invalid amount')
            elif cell in ('－','–','—','-'):
                values.append(Decimal(0))
            else:
                values.append(Decimal(cell.strip('()').replace(',','')) * (-1 if cell.startswith('(') else 1))
        if window['nci'] and label in {'归属于母公司股东的净利润','少数股东损益','少数股东权益'} and values[2:] != [None,None]:
            raise ValueError('parent N/A changed')
        matches.append((tuple(values), page))
    if len(matches) != 1:
        raise ValueError('missing or duplicate row: '+label)
    return matches[0]


def _extract(pages, year, code):
    profile = _profile(code, year)
    windows = {key: _window(pages, key, year, code) for key in TITLES}
    def read(section, label):
        return _read(windows[section], label)[0]
    def equal(left, *parts):
        if any(v is None for v in left) or any(any(v is None for v in p) for p in parts):
            raise ValueError('N/A in equation')
        if any(abs(left[i]-sum(p[i] for p in parts)) > 1 for i in range(len(left))):
            raise ValueError('reconciliation')
    revenue = read('income', profile['revenue'])
    equal(revenue, *[read('income', x) for x in profile['revenue_parts']])
    expenses = read('income', profile['expenses'])
    if any(v*profile['expense_sign'] < 0 for v in expenses):
        raise ValueError('expense signs')
    equal(expenses, *[read('income', x) for x in profile['expense_parts']])
    operating = read('income', '三、营业利润')
    equal(operating, revenue, tuple(-profile['expense_sign']*v for v in expenses))
    pretax = read('income', '四、利润总额')
    equal(pretax, operating, read('income','加：营业外收入'), read('income','减：营业外支出'))
    net = read('income','五、净利润')
    equal(net, pretax, read('income',profile['tax']))
    parent = read('income',profile['parent_profit'])
    minority = read('income',profile['minority_profit'])
    equal(net[:2], parent[:2], minority[:2])
    assets = read('balance','资产总计'); liabilities = read('balance','负债合计'); equity = read('balance','股东权益合计')
    if any(v <= 0 for v in assets) or any(v < 0 for v in liabilities):
        raise ValueError('invalid balance')
    equal(assets, liabilities, equity)
    equal(assets, read('balance','负债及股东权益总计' if code == '601336' else '负债和股东权益总计'))
    attributable = read('balance','归属于母公司股东的股东权益合计' if code == '601336' else '归属于母公司股东权益合计')
    minority_equity = read('balance','少数股东权益')
    equal(equity[:2], attributable[:2], minority_equity[:2])
    if code == '601336':
        equal(equity[2:], attributable[2:])
    flows = []
    for kind, label in zip(('经营','投资','筹资'), ('经营活动产生的现金流量净额',profile['investment'],profile['financing'])):
        incoming = read('cash',kind+'活动现金流入小计'); outgoing = read('cash',kind+'活动现金流出小计')
        if any(v < 0 for v in incoming) or any(v > 0 for v in outgoing):
            raise ValueError('cash signs')
        flow = read('cash',label); equal(flow,incoming,outgoing); flows.append(flow)
    delta = read('cash',profile['delta'])
    equal(delta,*flows,read('cash','四、汇率变动对现金及现金等价物的影响'+('额' if code == '601336' else '')))
    equal(read('cash','六、年末现金及现金等价物余额'),read('cash','加：年初现金及现金等价物余额'),delta)
    def figures(section, metrics):
        window = windows[section]
        result = dict(unit='人民币百万元',page_number=window['rows'][0][0],end_page_number=window['rows'][-1][0],metric_sources={})
        for key,label in metrics.items():
            values,page = _read(window,label)
            result['current_'+key],result['previous_'+key] = map(float,values[:2])
            result['metric_sources'][key] = dict(page_number=page,end_page_number=page,labels=[label],statement='保险公司合并报表',
                accounting_basis=('合并营业总收入（保险报表，非保费收入）' if code in ('601319','601601') else '保险公司合并营业收入（非保费收入）') if key == 'revenue' else '合并口径（页面同时列示公司口径）' if code == '601336' else '合并口径',
                comparison_basis='合并本期与上年比较栏原值；母公司列仅用于勾稽' if code == '601336' else '合并本期与年报上年比较栏原值')
        return result
    return dict(income=figures('income',dict(revenue=profile['revenue'],net_profit=profile['parent_profit'])),
                balance=figures('balance',dict(total_assets='资产总计',total_liabilities='负债合计')),
                cash=figures('cash',dict(operating_cash_flow='经营活动产生的现金流量净额')))


def extract_insurance_group_statements(pages, year, code):
    # Only the sampled year is enabled until another year's layout is tested.
    if year not in VERIFIED_YEARS.get(code, ()):
        return None
    try:
        return _extract(pages,year,code)
    except (ValueError, IndexError, ArithmeticError):
        return None
