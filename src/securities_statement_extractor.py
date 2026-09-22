"""Explicit four-column securities statements, initially Huatai 2024.

Group current/prior and parent current/prior are validated independently. Signed
cash outflows and signed income costs are never converted with abs().
"""
from decimal import Decimal
import re
from src.financial_statement_extractor import _normalise_lines, _chinese_label_span

SECURITIES_TEMPLATE = 'securities_group_parent_yuan_v1'
_TITLES = {'income':'合并及母公司利润表','balance':'合并及母公司资产负债表','cash':'合并及母公司现金流量表'}
_NUMBER = re.compile(r'^(?:[-—–]|[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[）)]?)$')
_NOTE = re.compile(r'^\d{1,3}(?:[（(]\d+[）)])+$')


def _window(pages, title, year, section):
    found=[]
    for index,(number,text) in enumerate(pages):
        lines=_normalise_lines(text)
        compact=[re.sub(r'\s+','',line) for line in lines]
        if title not in compact:continue
        pieces=[]
        for offset,(page,content) in enumerate(pages[index:index+3]):
            ls=_normalise_lines(content);cs=[re.sub(r'\s+','',line) for line in ls]
            heading=title if offset==0 else title+'-续'
            if heading not in cs:break
            if page!=number+offset:raise ValueError('nonconsecutive pages')
            start=cs.index(heading)
            pos=cs.index('附注五',start)
            if cs[pos-2:pos]!=['本集团','本公司']:raise ValueError('column groups')
            suffix='年12月31日' if section=='balance' else '年度'
            expected=[]
            for y in (year,year-1,year,year-1):expected.extend([f'{y}{suffix}','人民币元'])
            if cs[pos+1:pos+9]!=expected:raise ValueError('year/unit columns')
            body=ls[pos+9:]
            # A second statement on the same page is not a continuation.
            if any(re.search(r'(?:合并|母公司).*(?:资产负债表|利润表|现金流量表)',v) for v in body):raise ValueError('mixed statements')
            pieces.append((page,body))
        if len(pieces) == 3 and index+3 < len(pages) and title+'-续' in [re.sub(r'\s+','',x) for x in _normalise_lines(pages[index+3][1])]:
            raise ValueError('statement exceeds three pages')
        if pieces:found.append(pieces)
    if len(found)!=1:raise ValueError('missing or duplicate statement')
    return found[0]


def _read(window,label):
    lines=[line for _,body in window for line in body]
    matches=[]
    for i in range(len(lines)):
        end=_chinese_label_span(lines,i,label)
        if end is None:continue
        tokens=[]
        # Supported table has label-only lines, then optional note and four cells.
        for line in lines[end+1:end+8]:
            compact=re.sub(r'\s+','',line)
            if _NOTE.fullmatch(compact) and not tokens:continue
            parts=line.split()
            if not parts or not all(_NUMBER.fullmatch(t) for t in parts):break
            tokens.extend(parts)
        if len(tokens)==5 and re.fullmatch(r'\d{1,3}',tokens[0]):tokens=tokens[1:]
        if len(tokens)!=4:raise ValueError('not exactly four cells: '+label)
        values=[]
        for token in tokens:
            if token in ('-','—','–'):values.append(Decimal(0));continue
            token=token.replace('，',',').replace('（','(').replace('）',')').replace('−','-').replace('－','-')
            sign=-1 if token.startswith('(') else 1
            values.append(sign*Decimal(token.strip('()').replace(',','')))
        matches.append(tuple(values))
    if len(matches)!=1:raise ValueError('missing or duplicate row: '+label)
    return matches[0]


def extract_securities_statements(pages,year):
    try:
        windows={k:_window(pages,v,year,k) for k,v in _TITLES.items()}
        def read(section,label):return _read(windows[section],label)
        def equal(left,*parts):
            if any(abs(left[i]-sum(p[i] for p in parts))>Decimal('.01') for i in range(4)):
                raise ValueError('four-column reconciliation')
        rev=read('income','营业总收入')
        equal(rev,*[read('income',s) for s in ('手续费及佣金净收入','利息净收入','投资收益','其他收益','公允价值变动(损失)/收益','汇兑收益/(损失)','其他业务收入','资产处置收益')])
        equal(read('income','利息净收入'),read('income','其中：利息收入'),read('income','利息支出'))
        costs=read('income','营业总支出')
        if any(v>0 for v in costs):raise ValueError('unsigned expenses')
        equal(costs,*[read('income',s) for s in ('税金及附加','业务及管理费','信用减值损失','其他业务成本')])
        operating=read('income','营业利润');equal(operating,rev,costs)
        pretax=read('income','利润总额');equal(pretax,operating,read('income','加：营业外收入'),read('income','减：营业外支出'))
        net=read('income','净利润');equal(net,pretax,read('income','减：所得税费用'))
        parent=read('income','归属于母公司股东的净利润');minor=read('income','少数股东损益');equal(net,parent,minor)
        if any(minor[i]!=0 for i in (2,3)):raise ValueError('parent-only minority profit')
        assets=read('balance','资产总计');liabilities=read('balance','负债合计');equity=read('balance','股东权益合计')
        if any(v<=0 for v in assets) or any(v<0 for v in liabilities):raise ValueError('invalid assets/liabilities')
        equal(assets,liabilities,equity);equal(assets,read('balance','负债和股东权益总计'))
        minor_equity=read('balance','少数股东权益')
        equal(equity,read('balance','归属于母公司股东权益合计'),minor_equity)
        if any(minor_equity[i]!=0 for i in (2,3)):raise ValueError('parent-only minority equity')
        flows=[]
        labels=('经营活动产生/(使用)的现金流量净额','投资活动使用的现金流量净额','筹资活动(使用)/产生的现金流量净额')
        for kind,label in zip(('经营','投资','筹资'),labels):
            incoming=read('cash',kind+'活动现金流入小计');outgoing=read('cash',kind+'活动现金流出小计')
            if any(v<0 for v in incoming) or any(v>0 for v in outgoing):raise ValueError('cash signs')
            flow=read('cash',label);equal(flow,incoming,outgoing);flows.append(flow)
        delta=read('cash','现金及现金等价物净增加/(减少)额')
        equal(delta,*flows,read('cash','汇率变动对现金及现金等价物的影响'))
        equal(read('cash','年末现金及现金等价物余额'),read('cash','加：年初现金及现金等价物余额'),delta)
        def figures(section,values,sources):
            start,end=windows[section][0][0],windows[section][-1][0]
            result=dict(unit='人民币元',page_number=start,end_page_number=end,
                metric_sources={k:dict(page_number=start,end_page_number=end,labels=[v],statement='合并及母公司报表（仅取本集团列）') for k,v in sources.items()})
            for key,value in values.items():result['current_'+key],result['previous_'+key]=map(float,value[:2])
            return result
        return dict(income=figures('income',dict(revenue=rev,net_profit=parent),dict(revenue='营业总收入',net_profit='归属于母公司股东的净利润')),
            balance=figures('balance',dict(total_assets=assets,total_liabilities=liabilities),dict(total_assets='资产总计',total_liabilities='负债合计')),
            cash=figures('cash',dict(operating_cash_flow=flows[0]),dict(operating_cash_flow=labels[0])))
    except (ValueError,IndexError):return None
