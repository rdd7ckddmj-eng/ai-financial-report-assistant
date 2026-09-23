"""China Life's verified 2024 transition and 2025 two-year annual layouts.

2024 restates insurance contracts but not financial instruments. Retain original
comparison columns and suppress automatic growth; never fill N/A with zero.
"""
from decimal import Decimal
import re

CHINALIFE_TEMPLATE = 'insurance_chinalife_million_v1'
UNIT = '(除特别注明外，金额单位为人民币百万元)'
END = '后附财务报表附注为本财务报表的组成部分。'
INTEGER = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
NUMBER = re.compile(rf'(?:[–—-]|-?{INTEGER}|\({INTEGER}\))')
NOTE = re.compile(r'\d{1,2}(?:\(\d+\))?')
TITLES = dict(balance='合并资产负债表', income='合并利润表', cash='合并现金流量表')
NOTES_2024 = dict(zip(
    ['保险服务收入','利息收入','投资收益','公允价值变动损益','其他业务收入','保险服务费用','承保财务损益','税金及附加','业务及管理费','信用减值损失','资产减值损失','加：营业外收入','减：营业外支出','减：所得税费用','经营活动产生的现金流量净额','五、现金及现金等价物净增加/(减少)额','加：期初现金及现金等价物余额','六、期末现金及现金等价物余额'],
    ['35','36','37','38','39','40','41','42','43','44','45','46','47','48','52(1)','52(2)','52(2)','52(2)']))
NOTES_2025 = dict(zip(
    ['保险服务收入','利息收入','投资收益','公允价值变动损益','其他业务收入','保险服务费用','承保财务损益','税金及附加','业务及管理费','信用减值损失','加：营业外收入','减：营业外支出','减：所得税费用','经营活动产生的现金流量净额','五、现金及现金等价物净增加/(减少)额','加：期初现金及现金等价物余额','六、期末现金及现金等价物余额'],
    ['30','31','32','33','34','35','36','37','38','39','40','41','42','46(1)','46(2)','46(2)','46(2)']))
NA_COLUMNS = {'利息收入': {1,2}, '利息支出': {1,2}, '信用减值损失': {1,2},
              '其他资产减值损失': {1,2}, '资产减值损失': {0}}


def _lines(text):
    lines = [re.sub(r'\s+', '', x).translate(str.maketrans('（）', '()')) for x in text.splitlines() if x.strip()]
    # This single PDF font substitution was checked visually in the 2025 CFO
    # table. Do not replace arbitrary glyphs elsewhere in the document.
    return [x.replace('五、现金及现金等价物净增加/(ⲹ少)额','五、现金及现金等价物净增加/(减少)额') for x in lines]


def matches_chinalife_issuer(company, pages):
    if company.get('code') != '601628' or company.get('name') != '中国人寿':
        return False
    cover = '\n'.join('\n'.join(_lines(t)) for n,t in pages if 1 <= n <= 2)
    if not re.search(r'(?<!\d)601628(?!\d)', cover):
        return False
    # Legal name is in the company-information page, not the image cover.
    return any('公司基本信息' in _lines(t) and
               '公司法定中文名称\n中国人寿保险股份有限公司(简称“中国人寿”)' in '\n'.join(_lines(t))
               for n,t in pages if 3 <= n <= 100)


def _window(pages, section, year):
    title = f'{year}年12月31日' + TITLES[section] if section == 'balance' else f'{year}年度'+TITLES[section]
    note = '附注十一' if year == 2024 else '附注十'
    starts = [i for i,(_,t) in enumerate(pages) if title in _lines(t) and note in _lines(t)]
    if len(starts) != 1:
        raise ValueError('missing or duplicate table')
    start = starts[0]; count = (4 if section == 'balance' else 3) if year == 2024 else 2
    dates = ([f'{y}年12月31日' for y in [year,year-1]] if section == 'balance' else [f'{year}年度',f'{year-1}年度'])
    if year == 2024:
        dates = (['2024年','12月31日','2023年','12月31日','2022年','12月31日','2022年','1月1日'] if section == 'balance' else ['2024年度','2023年度','2022年度'])
    rows = []
    for offset in range(2):
        n,text = pages[start+offset]; lines = _lines(text)
        if n != pages[start][0]+offset:
            raise ValueError('nonconsecutive continuation')
        expected = title+('(续)' if offset else '')
        headings = [x for x in lines if re.fullmatch(r'.*(?:资产负债表|利润表|现金流量表)(?:\(续\))?', x)]
        if headings != [expected] or [x for x in lines if '金额单位' in x] != [UNIT]:
            raise ValueError('wrong title or unit')
        if lines.count(note) != 1:
            raise ValueError('missing note header')
        p = lines.index(note)
        label = ('负债及股东权益' if offset else '资产') if section == 'balance' else '项目'
        prefix = lines[:p-len(dates)-1] if year == 2024 else lines[:p-1]
        if any(re.fullmatch(r'(?:\d{4}年(?:度|\d{1,2}月\d{1,2}日)?|\d{1,2}月\d{1,2}日)', x)
               or '重述' in x for x in prefix):
            raise ValueError('extra leading comparison column')
        if year == 2024:
            if lines[p-len(dates)-1:p] != dates+[label]:
                raise ValueError('year columns')
            restated = ['(已重述，','附注五、2)']*(count-1)
            if lines[p+1:p+1+len(restated)] != restated:
                raise ValueError('restated columns')
            tail = lines[p+1+len(restated):]
        else:
            if lines[p-1] != label or lines[p+1:p+1+len(dates)] != dates:
                raise ValueError('year columns')
            tail = lines[p+1+len(dates):]
        first = {'balance': ['资产：','负债：'], 'income': ['一、营业收入','六、每股收益'], 'cash':['一、经营活动产生的现金流量','三、筹资活动产生的现金流量']}[section][offset]
        if not tail or tail[0] != first or tail.count(END) != 1:
            raise ValueError('unexpected columns or unbounded table')
        rows.extend((n,x) for x in tail[:tail.index(END)])
    return dict(rows=rows,count=count,year=year)


def _read(window, label):
    count=window['count']; rows=window['rows']; year=window['year']; matches=[]
    notes=NOTES_2024 if year == 2024 else NOTES_2025
    for i,(page,line) in enumerate(rows):
        if line != label:
            continue
        cells=[]
        for _,cell in rows[i+1:i+count+3]:
            if NUMBER.fullmatch(cell) or NOTE.fullmatch(cell) or cell == '不适用':
                cells.append(cell)
            else:
                if re.match(r'(?:[\d＋+−-]|\([\d＋+−-])',cell) or cell.casefold() in {'nan','inf','infinity','null','none','na','n/a','n.a.','不详','/','缺失'}:
                    raise ValueError('malformed numeric cell')
                break
        if len(cells)==count+1 and cells[0]==notes.get(label):
            cells=cells[1:]
        if len(cells)!=count:
            raise ValueError('missing or extra cells: '+label)
        expected_na=NA_COLUMNS.get(label,set()) if year == 2024 else set()
        values=[]
        for col,cell in enumerate(cells):
            if cell=='不适用':
                if col not in expected_na:
                    raise ValueError('unexpected not-applicable field')
                values.append(None)
            elif col in expected_na:
                raise ValueError('N/A changed to amount')
            elif cell in ('–','—','-'):
                values.append(Decimal(0))
            elif NUMBER.fullmatch(cell):
                values.append(Decimal(cell.strip('()').replace(',',''))*(-1 if cell.startswith('(') else 1))
            else:
                raise ValueError('bad number')
        matches.append((tuple(values),page))
    if len(matches)!=1:
        raise ValueError('missing or duplicate row: '+label)
    return matches[0]


def _extract(pages, year):
    windows={s:_window(pages,s,year) for s in TITLES}
    def read(s,label):return _read(windows[s],label)[0]
    def equal(left,*parts):
        if any(v is None for v in left) or any(any(v is None for v in p) for p in parts):
            raise ValueError('N/A in regular equation')
        if any(abs(left[i]-sum(p[i] for p in parts))>1 for i in range(len(left))):
            raise ValueError('reconciliation')
    def sum_active(left, labels):
        # Only explicitly verified N/A columns can be absent from these sums.
        # None remains None in parsed rows; it is not a reported zero amount.
        parts=[read('income',label) for label in labels]
        for col,total in enumerate(left):
            if abs(total-sum(p[col] for p in parts if p[col] is not None))>1:
                raise ValueError('active accounting categories do not reconcile')
    revenue=read('income','一、营业收入')
    sum_active(revenue,['保险服务收入','利息收入','投资收益','其他收益','公允价值变动损益','汇兑损益','其他业务收入','资产处置损益'])
    expenses=read('income','二、营业支出')
    if any(v>0 for v in expenses):raise ValueError('expense signs')
    expense_labels=['保险服务费用','分出保费的分摊','减：摊回保险服务费用','承保财务损益','减：分出再保险财务损益','利息支出','手续费及佣金支出','税金及附加','业务及管理费','信用减值损失','其他资产减值损失','其他业务成本']
    if year==2024:expense_labels.append('资产减值损失')
    sum_active(expenses,expense_labels)
    operating=read('income','三、营业利润');equal(operating,revenue,expenses)
    pretax=read('income','四、利润总额');equal(pretax,operating,read('income','加：营业外收入'),read('income','减：营业外支出'))
    net=read('income','五、净利润');equal(net,pretax,read('income','减：所得税费用'))
    equal(net,read('income','归属于母公司股东的净利润'),read('income','少数股东损益'))
    assets=read('balance','资产总计');liabilities=read('balance','负债合计');equity=read('balance','股东权益合计')
    if any(v<=0 for v in assets) or any(v<0 for v in liabilities):raise ValueError('invalid balance')
    equal(assets,liabilities,equity);equal(assets,read('balance','负债及股东权益总计'))
    equal(equity,read('balance','归属于母公司股东的股东权益合计'),read('balance','少数股东权益'))
    flows=[]
    for kind in ['经营','投资','筹资']:
        incoming=read('cash',kind+'活动现金流入小计');outgoing=read('cash',kind+'活动现金流出小计')
        if any(v<0 for v in incoming) or any(v>0 for v in outgoing):raise ValueError('cash signs')
        flow=read('cash',kind+'活动产生的现金流量净额');equal(flow,incoming,outgoing);flows.append(flow)
    delta=read('cash','五、现金及现金等价物净增加/(减少)额')
    equal(delta,*flows,read('cash','四、汇率变动对现金及现金等价物的影响'))
    equal(read('cash','六、期末现金及现金等价物余额'),read('cash','加：期初现金及现金等价物余额'),delta)
    basis='本期与上年比较栏；2023/2022保险合同已重述，金融工具未重述，不自动计算同比；更早列仅用于勾稽' if year==2024 else '本期与年报上年比较栏原值'
    def figures(section, metrics):
        window=windows[section];result=dict(unit='人民币百万元',page_number=window['rows'][0][0],end_page_number=window['rows'][-1][0],metric_sources={})
        for key,label in metrics.items():
            values,page=_read(window,label)
            result['current_'+key],result['previous_'+key]=map(float,values[:2])
            result['metric_sources'][key]=dict(page_number=page,end_page_number=page,labels=[label],statement='保险公司合并报表',accounting_basis='保险公司合并营业收入（非保费收入）' if key=='revenue' else '合并口径',comparison_basis=basis,comparison_comparable=year!=2024)
        return result
    return dict(income=figures('income',dict(revenue='一、营业收入',net_profit='归属于母公司股东的净利润')),balance=figures('balance',dict(total_assets='资产总计',total_liabilities='负债合计')),cash=figures('cash',dict(operating_cash_flow='经营活动产生的现金流量净额')))


def extract_chinalife_statements(pages, year):
    if type(year) is not int or year not in (2024,2025):return None
    try:return _extract(pages,year)
    except (ValueError,IndexError,ArithmeticError):return None
