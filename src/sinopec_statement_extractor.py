"""Bounded Sinopec 2025 CAS original-text profile.

The 239-page annual report also contains IFRS statements and separate parent
statements. Only the visually verified CAS consolidated tables supply figures.
No OCR, repair, inferred values, geometry mutation or cross-basis fallback.
"""
from decimal import Decimal, InvalidOperation
import re

SINOPEC_TEMPLATE = 'sinopec_2025_cas_separate_tables_million_v1'
SINOPEC_2025_REPORT_URL = 'https://static.cninfo.com.cn/finalpage/2026-03-23/1225024063.PDF'
_LEGAL = '中国石油化工股份有限公司'
_NUM = re.compile(r'^(?:-|\d{1,3}(?:,\d{3})+|\d+|\((?:\d{1,3}(?:,\d{3})+|\d+)\))$')
_EPS = re.compile(r'^\d+\.\d{3}$')
_DATE = '截至2025年12月31日止年度'
_FOOTER = ('此财务报表已于2026年3月20日获董事会批准报出。董事长总裁财务总监'
           '（法定代表人）后附财务报表附注为本财务报表的组成部分。')


def _c(text):
    return re.sub(r'\s+', '', text)


def _lines(text):
    return [m for m in re.finditer(r'[^\r\n]+', text) if m.group().strip()]


def is_sinopec_annual_report_identity(company, pages, year):
    """Require original cover, legal identity and explicit Shanghai A-share code."""
    if (str(company.get('code')) != '600028' or company.get('name') != '中国石化'
            or type(year) is not int or year != 2025):
        return False
    pages = list(pages)
    def one(number):
        found = [text for n, text in pages if n == number]
        return _c(found[0]) if len(found) == 1 else ''
    return (one(1) == '2025年度报告'
            and '“中国石化”是指' + _LEGAL in one(4)
            and ('公司资料法定名称' + _LEGAL + '英文名称ChinaPetroleum&ChemicalCorporation'
                 '中文简称中国石化英文简称SinopecCorp.') in one(236)
            and ('股票上市地点、股票简称和股票代号A股：上海证券交易所'
                 '股票简称：中国石化股票代号：600028H股：') in one(237))


def _table(pages, number, title, balance=False):
    """Bind an observed physical/printed page and exact date/year/currency header."""
    text = dict(pages).get(number, '')
    matches = _lines(text)
    expected = [_LEGAL, str(number - 1), title,
                '于2025年12月31日' if balance else _DATE,
                '附注', '2025年', '2024年']
    if balance:
        expected += ['12月31日', '12月31日']
    expected += ['人民币', '人民币', '百万元', '百万元']
    if [_c(m.group()) for m in matches[:len(expected)]] != expected:
        raise ValueError('公司、页码、CAS表名、年度或人民币百万元双列表头不匹配：' + title)
    # This PDF has two explicitly different sets with repeated titles. An IFRS
    # title is ignored only at its observed page with its distinct intact header.
    ignored = {'合并利润表': (175, '(除每股数字外，以百万元列示)'),
               '合并现金流量表': (180, '(以百万元列示)')}
    for n, other in pages:
        ls = [_c(m.group()) for m in _lines(other)]
        # The front-matter CAS/IFRS comparison also names these statements in
        # prose; it has no legal-name primary-statement page header.
        if title not in ls or (n != number and (not ls or ls[0] != _LEGAL)):
            continue
        if ls.count(title) != 1:
            raise ValueError('同页报表标题重复：' + title)
        if n == number:
            continue
        other_number, marker = ignored.get(title, (None, None))
        if (n != other_number or ls[:9] != [_LEGAL, str(n-1), title, _DATE, marker,
                                           '附注', '截至12月31日止年度', '2025年', '2024年']):
            raise ValueError('额外、重复或无法识别会计准则的报表：' + title)
    return dict(page=number, text=text, matches=matches[len(expected):])


def _read(table, specs):
    matches, cursor, rows = table['matches'], 0, {}
    for label, note in specs:
        start = cursor
        if cursor >= len(matches) or _c(matches[cursor].group()) != _c(label):
            raise ValueError('缺失、重复或未知行：' + label)
        cursor += 1
        if note is False:
            continue
        if note is not None:
            if cursor >= len(matches) or _c(matches[cursor].group()) != note:
                raise ValueError('附注编号缺失或错位：' + label)
            cursor += 1
        values = []
        for _ in range(2):
            token = matches[cursor].group().strip() if cursor < len(matches) else ''
            pattern = _EPS if '每股收益' in label else _NUM
            if len(token) > 24 or not pattern.fullmatch(token):
                raise ValueError('两期金额缺失或格式不匹配：' + label)
            value = Decimal(0) if token == '-' else Decimal(token.strip('()').replace(',', ''))
            if token.startswith('('):
                value = -value
            if abs(value) > Decimal('1e15'):
                raise ValueError('金额超出范围：' + label)
            values.append(value)
            cursor += 1
        if label in rows:
            raise ValueError('重复金额科目：' + label)
        raw = table['text'][matches[start].start():matches[cursor-1].end()]
        rows[label] = dict(values=values, page=table['page'], note=note, excerpt=raw)
    if _c(''.join(m.group() for m in matches[cursor:])) != _FOOTER:
        raise ValueError('表尾包含额外金额、重复科目或边界不完整')
    return rows


_ASSETS = [('资产', False), ('流动资产', False), ('货币资金','5'),
    ('交易性金融资产',None), ('衍生金融资产','6'), ('应收账款','7'), ('应收款项融资','8'),
    ('预付款项','9'), ('其他应收款','10'), ('存货','11'), ('其他流动资产',None),
    ('流动资产合计',None), ('非流动资产',False), ('长期股权投资','12'),
    ('其他权益工具投资','13'), ('固定资产','14'), ('在建工程','15'), ('使用权资产','16'),
    ('无形资产','17'), ('商誉','18'), ('长期待摊费用','19'), ('递延所得税资产','20'),
    ('其他非流动资产','21'), ('非流动资产合计',None), ('资产总计',None)]
_LIABILITIES = [('负债和股东权益',False), ('流动负债',False), ('短期借款','23'),
    ('衍生金融负债','6'), ('应付票据','24'), ('应付账款','25'), ('合同负债','26'),
    ('应付职工薪酬','27'), ('应交税费','28'), ('其他应付款','29'), ('一年内到期的非流动负债','30'),
    ('其他流动负债','31'), ('流动负债合计',None), ('非流动负债',False), ('长期借款','32'),
    ('应付债券','33'), ('租赁负债','34'), ('预计负债','35'), ('递延所得税负债','20'),
    ('其他非流动负债','36'), ('非流动负债合计',None), ('负债合计',None), ('股东权益',False),
    ('股本','37'), ('资本公积','38'), ('减：库存股',None), ('其他综合收益','39'),
    ('专项储备','40'), ('盈余公积','41'), ('未分配利润',None), ('归属于母公司股东权益合计',None),
    ('少数股东权益',None), ('股东权益合计',None), ('负债和股东权益总计',None)]
_INCOME = [('营业收入','42'), ('减：营业成本','42'), ('税金及附加','43'), ('销售费用','46'),
    ('管理费用','47'), ('研发费用','48'), ('财务费用','44'), ('其中：利息费用',None),
    ('利息收入',None), ('勘探费用（包括干井成本）','49'), ('加：其他收益','50'), ('投资收益','51'),
    ('其中：对联营企业和合营企业的投资收益',None), ('公允价值变动损益','52'),
    ('信用减值转回/(损失)',None), ('资产减值损失','53'), ('资产处置收益',None),
    ('营业利润',None), ('加：营业外收入','54'), ('减：营业外支出','55'), ('利润总额',None),
    ('减：所得税费用','56'), ('净利润',None), ('按经营持续性分类：',False), ('持续经营净利润',None),
    ('终止经营净利润',None), ('按所有权归属分类：',False), ('母公司股东的净利润',None),
    ('少数股东损益',None), ('基本每股收益（人民币元）','66'), ('稀释每股收益（人民币元）','66')]
_CASH = [('经营活动产生的现金流量：',False), ('销售商品、提供劳务收到的现金',None),
    ('收到的税费返还',None), ('收到其他与经营活动有关的现金',None), ('经营活动现金流入小计',None),
    ('购买商品、接受劳务支付的现金',None), ('支付给职工以及为职工支付的现金',None),
    ('支付的各项税费',None), ('支付其他与经营活动有关的现金',None), ('经营活动现金流出小计',None),
    ('经营活动产生的现金流量净额','58(a)'), ('投资活动产生的现金流量：',False),
    ('收回投资收到的现金',None), ('取得投资收益所收到的现金',None),
    ('处置固定资产、无形资产和其他长期资产收回的现金净额',None), ('处置子公司及其他营业单位收到的现金净额',None),
    ('收到其他与投资活动有关的现金','58(d)'), ('投资活动现金流入小计',None),
    ('购建固定资产、无形资产和其他长期资产支付的现金',None), ('投资所支付的现金',None),
    ('取得子公司及其他营业单位支付的现金净额',None), ('支付其他与投资活动有关的现金','58(e)'),
    ('投资活动现金流出小计',None), ('投资活动使用的现金流量净额',None), ('筹资活动产生的现金流量：',False),
    ('吸收投资收到的现金',None), ('其中：子公司吸收少数股东投资收到的现金',None),
    ('取得借款收到的现金','58(g)'), ('收到其他与筹资活动有关的现金',None), ('筹资活动现金流入小计',None),
    ('偿还债务支付的现金',None), ('分配股利、利润或偿付利息支付的现金',None),
    ('其中：子公司支付给少数股东的股利、利润',None), ('支付其他与筹资活动有关的现金','58(f)'),
    ('筹资活动现金流出小计',None), ('筹资活动使用的现金流量净额',None),
    ('汇率变动对现金及现金等价物的影响',None), ('现金及现金等价物净减少额','58(b)'),
    ('加：期初现金及现金等价物余额',None), ('期末现金及现金等价物余额','58(c)')]


def extract_sinopec_statements(pages, year):
    """Return None for identity nonmatch; any recognized failure emits no figures."""
    pages = list(pages)
    if not is_sinopec_annual_report_identity(dict(code='600028', name='中国石化'), pages, year):
        return None
    detail = dict(status='missing_evidence', passed=False, checks=[], unit='人民币百万元',
                  pages=None, header_years=[2025,2024], tolerance='0', evidence={},
                  rounding_note='本限定原件各项关系均精确相等，不使用舍入容差放宽。',
                  tax_presentation='CAS利润表费用和所得税以正数扣减；减值损失按原文负数相加；现金流出按原文负数相加。',
                  note='中国石化CAS专用证据尚未全部通过。')
    failure = dict(template=SINOPEC_TEMPLATE, income=None, balance=None, cash=None,
                   income_reconciliation=detail, failure_reason='')
    try:
        numbers = [n for n,t in pages]
        if any(type(n) is not int or n < 1 for n in numbers) or numbers != sorted(set(numbers)):
            raise ValueError('物理页码重复、无效或次序不符')
        audits = [(n,t) for n,t in pages if '一、审计意见' in _c(t) and '审计报告' in _c(t)]
        if len(audits) != 1 or audits[0][0] != 89:
            raise ValueError('缺少唯一的原件CAS审计意见页')
        audit_text = _c(audits[0][1])
        for required in (_LEGAL+'全体股东：', '毕马威华振审字第2603847号',
                         '2025年12月31日的合并及母公司资产负债表',
                         '2025年度的合并及母公司利润表、合并及母公司现金流量表',
                         '按照中华人民共和国财政部颁布的企业会计准则'):
            if required not in audit_text:
                raise ValueError('审计意见公司、年度或CAS依据不匹配')
        tables = dict(assets=_table(pages,95,'合并资产负债表',True),
                      liabilities=_table(pages,96,'合并资产负债表（续）',True),
                      income=_table(pages,99,'合并利润表'), cash=_table(pages,102,'合并现金流量表'))
        inc = _read(tables['income'], _INCOME)
        bal = {**_read(tables['assets'],_ASSETS), **_read(tables['liabilities'],_LIABILITIES)}
        cash = _read(tables['cash'],_CASH)
        checks = dict(income=[], balance=[], cash=[])
        def evidence(rows):
            return {label: dict(values=list(map(str,row['values'])), pages=dict(start=row['page'],end=row['page']),
                                excerpt=row['excerpt'],raw_excerpt=row['excerpt'],note=row['note'],
                                unit='人民币元' if '每股收益' in label else '人民币百万元') for label,row in rows.items()}
        detail['pages'] = dict(start=99,end=99)
        detail['evidence'] = evidence(inc)
        failure['statement_evidence'] = dict(income=evidence(inc),balance=evidence(bal),cash=evidence(cash))
        def equation(section, rows, left, positive, negative=()):
            check = dict(key=f'{section}_{len(checks[section])+1}', label=left+' = '+' + '.join(positive)
                         + ''.join(' - '+x for x in negative),passed=False)
            for i,period in enumerate(('current','previous')):
                computed = sum((rows[x]['values'][i] for x in positive),Decimal(0)) - sum((rows[x]['values'][i] for x in negative),Decimal(0))
                reported = rows[left]['values'][i]
                check[period] = dict(left=str(computed),right=str(reported),difference=str(computed-reported),passed=computed==reported)
            check['passed'] = check['current']['passed'] and check['previous']['passed']
            checks[section].append(check)
        def sign(rows, labels, positive):
            for label in labels:
                if any(v < 0 if positive else v > 0 for v in rows[label]['values']):
                    raise ValueError('原文正负呈列不符合限定模板：'+label)
        costs = ['减：营业成本','税金及附加','销售费用','管理费用','研发费用','财务费用','勘探费用（包括干井成本）']
        sign(inc,costs+['营业收入','其中：利息费用','利息收入','减：营业外支出','减：所得税费用'],True)
        sign(inc,['资产减值损失'],False)
        equation('income',inc,'营业利润',['营业收入','加：其他收益','投资收益','公允价值变动损益','信用减值转回/(损失)','资产减值损失','资产处置收益'],costs)
        equation('income',inc,'利润总额',['营业利润','加：营业外收入'],['减：营业外支出'])
        equation('income',inc,'净利润',['利润总额'],['减：所得税费用'])
        equation('income',inc,'净利润',['持续经营净利润','终止经营净利润'])
        equation('income',inc,'净利润',['母公司股东的净利润','少数股东损益'])
        equation('income',inc,'基本每股收益（人民币元）',['稀释每股收益（人民币元）'])
        for total,specs,first in [('流动资产合计',_ASSETS,'流动资产'),('非流动资产合计',_ASSETS,'非流动资产'),
                                   ('流动负债合计',_LIABILITIES,'流动负债'),('非流动负债合计',_LIABILITIES,'非流动负债')]:
            labels = [x[0] for x in specs]
            components = labels[labels.index(first)+1:labels.index(total)]
            sign(bal,components+[total],True)
            equation('balance',bal,total,components)
        equation('balance',bal,'资产总计',['流动资产合计','非流动资产合计'])
        equation('balance',bal,'负债合计',['流动负债合计','非流动负债合计'])
        equation('balance',bal,'归属于母公司股东权益合计',['股本','资本公积','其他综合收益','专项储备','盈余公积','未分配利润'],['减：库存股'])
        equation('balance',bal,'股东权益合计',['归属于母公司股东权益合计','少数股东权益'])
        equation('balance',bal,'资产总计',['负债合计','股东权益合计'])
        equation('balance',bal,'负债和股东权益总计',['资产总计'])
        if any(v <= 0 for v in bal['资产总计']['values']):
            raise ValueError('资产总计必须大于零')
        incoming = [['销售商品、提供劳务收到的现金','收到的税费返还','收到其他与经营活动有关的现金'],
                    ['收回投资收到的现金','取得投资收益所收到的现金','处置固定资产、无形资产和其他长期资产收回的现金净额','处置子公司及其他营业单位收到的现金净额','收到其他与投资活动有关的现金'],
                    ['吸收投资收到的现金','取得借款收到的现金','收到其他与筹资活动有关的现金']]
        outgoing = [['购买商品、接受劳务支付的现金','支付给职工以及为职工支付的现金','支付的各项税费','支付其他与经营活动有关的现金'],
                    ['购建固定资产、无形资产和其他长期资产支付的现金','投资所支付的现金','取得子公司及其他营业单位支付的现金净额','支付其他与投资活动有关的现金'],
                    ['偿还债务支付的现金','分配股利、利润或偿付利息支付的现金','支付其他与筹资活动有关的现金']]
        nets = ['经营活动产生的现金流量净额','投资活动使用的现金流量净额','筹资活动使用的现金流量净额']
        for kind, ins, outs, net in zip(('经营','投资','筹资'),incoming,outgoing,nets):
            tin,tout=kind+'活动现金流入小计',kind+'活动现金流出小计'
            sign(cash,ins+[tin],True); sign(cash,outs+[tout],False)
            equation('cash',cash,tin,ins); equation('cash',cash,tout,outs)
            equation('cash',cash,net,[tin,tout])
        equation('cash',cash,'现金及现金等价物净减少额',nets+['汇率变动对现金及现金等价物的影响'])
        equation('cash',cash,'期末现金及现金等价物余额',['加：期初现金及现金等价物余额','现金及现金等价物净减少额'])
        sign(cash,['加：期初现金及现金等价物余额','期末现金及现金等价物余额'],True)
        for sub,total,positive in [('其中：子公司吸收少数股东投资收到的现金','吸收投资收到的现金',True),
                                   ('其中：子公司支付给少数股东的股利、利润','分配股利、利润或偿付利息支付的现金',False)]:
            sign(cash,[sub],positive)
            if any(abs(cash[sub]['values'][i]) > abs(cash[total]['values'][i]) for i in (0,1)):
                raise ValueError('少数股东现金子项目超过所属总项')
        detail['checks'] = checks['income']
        failure['statement_reconciliation'] = checks
        if not all(c['passed'] for cs in checks.values() for c in cs):
            detail.update(status='mismatch',note='中国石化CAS三表勾稽出现差额，未输出标准化金额。')
            failure['failure_reason']=detail['note']; return failure
        def figures(rows, fields, first, last):
            result = dict(unit='人民币百万元',page_number=first,end_page_number=last,metric_sources={})
            for field,label in fields.items():
                row=rows[label]
                result['current_'+field],result['previous_'+field]=map(float,row['values'])
                result['metric_sources'][field]=dict(page_number=row['page'],end_page_number=row['page'],labels=[label],
                    statement='中国企业会计准则合并报表（母公司及IFRS报表不提供金额）',
                    comparison_basis='本年报CAS合并报表2024比较栏原值；不替换为其他口径或年度。',
                    raw_excerpt=row['excerpt'],unit='人民币百万元')
            return result
        detail.update(status='passed',passed=True,note='中国石化2025 CAS合并三表双期组成与合计通过Decimal精确勾稽；仍待人工核验。')
        return dict(template=SINOPEC_TEMPLATE,
                    income=figures(inc,dict(revenue='营业收入',net_profit='母公司股东的净利润'),99,99),
                    balance=figures(bal,dict(total_assets='资产总计',total_liabilities='负债合计'),95,96),
                    cash=figures(cash,dict(operating_cash_flow=nets[0]),102,102),
                    income_reconciliation=detail,statement_reconciliation=checks,
                    statement_evidence=failure['statement_evidence'],
                    audit_evidence=dict(page=89,excerpt=audits[0][1],accounting_standard='中国企业会计准则'))
    except (ValueError,InvalidOperation,IndexError,TypeError) as error:
        detail.update(status='missing_evidence',passed=False,note='中国石化CAS专用证据不足：'+str(error)+'。')
        failure['failure_reason']=detail['note']; return failure
