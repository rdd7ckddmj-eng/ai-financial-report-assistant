"""Bounded PetroChina 2024/2025 PRC-GAAP signed four-column report profile.

The negative-expense convention is an issuer/layout rule established from the
original tables, never selected by trying alternative arithmetic. All four
columns and all listed income/cash/balance components must pass Decimal checks.
"""
from decimal import Decimal, InvalidOperation
import re

from src.financial_statement_extractor import _normalise_lines

PETROCHINA_TEMPLATE = 'petrochina_signed_fourcols_million_v1'
_LEGAL = '中国石油天然气股份有限公司'
_UNIT = '(除特别注明外，金额单位为人民币百万元)'
_YEARS = (2024, 2025)
_NUMBER = re.compile(r'^(?:-|\d{1,3}(?:,\d{3})+|\d+|\((?:\d{1,3}(?:,\d{3})+|\d+)\))$')


def _compact(text):
    return re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')').replace(':', '：')


def is_petrochina_annual_report_identity(company, pages, year):
    """Bind the observed complete Chinese A-share cover and legal-name field."""
    if (str(company.get('code')) != '601857' or company.get('name') != '中国石油'
            or type(year) is not int or year not in _YEARS):
        return False
    first = [text for number, text in pages if number == 1]
    if len(first) != 1:
        return False
    cover = _compact(first[0])
    prefix = f'{_LEGAL}{year}年度报告(A股股票代码：601857)'
    if not cover.startswith(prefix) or '摘要' in cover or '英文' in cover:
        return False
    front = ''.join(_compact(t) for n, t in pages if 1 <= n <= 10)
    return '公司注册中文名称：' + _LEGAL + '公司英文名称：PetroChinaCompanyLimited' in front


def _table(pages, year, kind, continuation=False):
    suffix = '年12月31日' if kind == '资产负债表' else '年度'
    title = f'{year}{suffix}合并及公司{kind}' + ('(续)' if continuation else '')
    found = []
    for number, text in pages:
        lines = _normalise_lines(text)
        compact = [_compact(line) for line in lines]
        if title not in compact:
            continue
        if compact.count(title) != 1:
            raise ValueError('同页重复报表标题')
        start = compact.index(title)
        if start < 1 or compact[start - 1] != _LEGAL or compact[start + 1:start + 2] != [_UNIT]:
            raise ValueError('报表公司法定名称或人民币百万元声明不匹配')
        body_label = '流动负债' if continuation else ('流动资产' if kind == '资产负债表' else ('营业收入' if kind == '利润表' else '经营活动产生的现金流量'))
        try:
            body = compact.index(body_label, start + 2)
        except ValueError:
            raise ValueError('报表表头与首个项目边界缺失')
        years = ''.join(f'{y}{suffix}' for y in (year, year - 1, year, year - 1))
        expected = (years + ('负债及股东权益' if continuation else '资产') + '附注合并合并公司公司'
                    if kind == '资产负债表' else '项目附注' + years + '合并合并公司公司')
        if ''.join(compact[start + 2:body]) != expected:
            raise ValueError('合并/公司、本期/比较期四列表头存在错位或未知内容')
        found.append(dict(page=number, lines=lines[body:], title=title))
    if len(found) != 1:
        raise ValueError('报表缺失或重复：' + title)
    return found[0]


def _parse(table, specs, stop):
    """Consume every required row in order; unknown rows/cells cannot be skipped.

    Each observed note reference is specified separately from the four amounts.
    This prevents a missing amount from being supplied by a bare numeric note.
    """
    lines = table['lines']; cursor = 0; rows = {}
    for label, note in specs:
        # Wrapped Chinese labels are joined only until the exact expected label.
        joined = ''; end = None
        for j in range(cursor, min(cursor + 4, len(lines))):
            joined += _compact(lines[j])
            if joined == _compact(label):
                end = j; break
        if end is None:
            raise ValueError('缺失、重复或未知报表行：' + label)
        start = cursor; cursor = end + 1
        if note is False:  # Explicit nonmonetary section heading.
            continue
        if note is not None:
            if cursor >= len(lines) or _compact(lines[cursor]) != note:
                raise ValueError('附注编号缺失或错位：' + label)
            cursor += 1
        tokens = []
        while cursor < len(lines) and len(tokens) < 4:
            parts = lines[cursor].split()
            if not parts or not all(_NUMBER.fullmatch(p) for p in parts):
                raise ValueError('金额格式或列数不完整：' + label)
            tokens.extend(parts); cursor += 1
        if len(tokens) != 4:
            raise ValueError('金额不是四列：' + label)
        values = []
        for token in tokens:
            if len(token) > 30:
                raise ValueError('金额长度超出范围')
            number = Decimal(0) if token == '-' else Decimal(token.strip('()').replace(',', ''))
            if token.startswith('('):
                number = -number
            if abs(number) > Decimal('1e15'):
                raise ValueError('金额超出支持范围')
            values.append(number)
        rows[label] = dict(values=values, page=table['page'], note=note,
                           excerpt=' ｜ '.join(lines[start:cursor]))
    # No arbitrary prose, fifth amount, duplicate tail row or damaged token may
    # occur before the observed following section/footer.
    if cursor >= len(lines) or _compact(lines[cursor]) != _compact(stop):
        raise ValueError('末行之后不是明确的报表边界')
    return rows


_INCOME = [
    ('营业收入','42'), ('减：营业成本','42'), ('税金及附加','43'), ('销售费用','44'),
    ('管理费用','45'), ('研发费用','46'), ('财务费用','47'), ('其中：利息费用',None),
    ('利息收入',None), ('加：其他收益','48'), ('投资收益','49'),
    ('其中：对联营企业和合营企业的投资收益',None), ('公允价值变动收益','50'),
    ('信用减值损失','51'), ('资产减值损失','52'), ('资产处置收益','53'),
    ('营业利润',None), ('加：营业外收入','54(a)'), ('减：营业外支出','54(b)'),
    ('利润总额',None), ('减：所得税费用','55'), ('净利润',None),
    ('按经营持续性分类：',False), ('持续经营净利润',None), ('终止经营净利润',None),
    ('按所有权归属分类：',False), ('归属于母公司股东的净利润',None), ('少数股东损益',None),
]
_ASSETS = [
    ('流动资产',False), ('货币资金','7'), ('交易性金融资产',None), ('衍生金融资产','8'),
    ('应收账款','9'), ('应收款项融资','10'), ('预付款项','11'), ('其他应收款','12'),
    ('存货','13'), ('其他流动资产','14'), ('流动资产合计',None), ('非流动资产',False),
    ('其他权益工具投资',None), ('长期股权投资','15'), ('固定资产','16'), ('油气资产','17'),
    ('在建工程','18'), ('使用权资产','19'), ('无形资产','20'), ('商誉','21'),
    ('长期待摊费用','22'), ('递延所得税资产','36'), ('其他非流动资产','23'),
    ('非流动资产合计',None), ('资产总计',None),
]
_LIABILITIES = [
    ('流动负债',False), ('短期借款','25'), ('交易性金融负债',None), ('衍生金融负债','8'),
    ('应付票据','26'), ('应付账款','27'), ('合同负债','28'), ('应付职工薪酬','29'),
    ('应交税费','30'), ('其他应付款','31'), ('一年内到期的非流动负债','32'),
    ('其他流动负债',None), ('流动负债合计',None), ('非流动负债',False),
    ('长期借款','33'), ('应付债券','34'), ('租赁负债','19'), ('预计负债','35'),
    ('递延所得税负债','36'), ('其他非流动负债',None), ('非流动负债合计',None),
    ('负债合计',None), ('股东权益',False), ('股本','37'), ('资本公积','38'),
    ('专项储备',None), ('其他综合收益','57'), ('盈余公积','39'), ('未分配利润','40'),
    ('归属于母公司股东权益合计',None), ('少数股东权益','41'), ('股东权益合计',None),
    ('负债及股东权益总计',None),
]
_CASH = [
    ('经营活动产生的现金流量',False), ('销售商品、提供劳务收到的现金',None),
    ('收到其他与经营活动有关的现金','59(a)'), ('经营活动现金流入小计',None),
    ('购买商品、接受劳务支付的现金',None), ('支付给职工以及为职工支付的现金',None),
    ('支付的各项税费',None), ('支付其他与经营活动有关的现金','59(b)'),
    ('经营活动现金流出小计',None), ('经营活动产生的现金流量净额','59(f)'),
    ('投资活动产生的现金流量',False), ('收回投资收到的现金','59(c)'),
    ('取得投资收益所收到的现金',None), ('处置固定资产、油气资产、无形资产和其他长期资产收回的现金净额',None),
    ('处置子公司及其他营业单位收到的现金净额',None), ('投资活动现金流入小计',None),
    ('购建固定资产、油气资产、无形资产和其他长期资产支付的现金',None), ('投资支付的现金','59(d)'),
    ('取得子公司及其他营业单位支付的现金净额',None), ('投资活动现金流出小计',None),
    ('投资活动使用的现金流量净额',None), ('筹资活动产生的现金流量',False),
    ('吸收投资收到的现金',None), ('其中：子公司吸收少数股东投资收到的现金',None),
    ('取得借款收到的现金',None), ('筹资活动现金流入小计',None), ('偿还债务支付的现金',None),
    ('同一控制下企业合并支付的对价',None), ('分配股利、利润或偿付利息支付的现金',None),
    ('其中：子公司支付给少数股东的股利、利润',None), ('支付其他与筹资活动有关的现金','59(e)'),
    ('筹资活动现金流出小计',None), ('筹资活动使用的现金流量净额',None),
    ('汇率变动对现金及现金等价物的影响',None),
]
_FOOTER = '后附财务报表附注为财务报表的组成部分'


def extract_petrochina_statements(pages, year):
    """Return None for a nonmatch; recognized failures contain no figures."""
    pages = list(pages)
    if not is_petrochina_annual_report_identity(dict(code='601857', name='中国石油'), pages, year):
        return None
    detail = dict(status='missing_evidence', passed=False, checks=[], unit='人民币百万元', pages=None,
                  header_years=[year, year - 1], tolerance='1',
                  rounding_note='整数百万元报表允许最多1个原文显示单位的舍入差；差额逐项保留。',
                  tax_presentation='中国石油限定四列模板：费用、所得税和现金流出以原文负数相加，不重复扣减。',
                  note='专用报表证据尚未全部通过。', evidence={})
    failed = dict(template=PETROCHINA_TEMPLATE, income=None, balance=None, cash=None,
                  income_reconciliation=detail, failure_reason='')
    try:
        numbers = [n for n, _ in pages]
        if len(numbers) != len(set(numbers)) or numbers != sorted(numbers):
            raise ValueError('物理页面重复或顺序不正确')
        tables = dict(income=_table(pages, year, '利润表'), assets=_table(pages, year, '资产负债表'),
                      liabilities=_table(pages, year, '资产负债表', True), cash=_table(pages, year, '现金流量表'))
        start = tables['assets']['page']
        if [tables[k]['page'] for k in ('assets','liabilities','income','cash')] != list(range(start, start + 4)):
            raise ValueError('四张原文表页不连续或次序不符')
        audits = []
        for n, text in pages:
            compact = _compact(text)
            if start - 8 <= n < start and '审计报告' in compact and '一、审计意见' in compact:
                if (f'{year}年12月31日的合并及公司资产负债表' in compact
                        and f'{year}年度的合并及公司利润表' in compact
                        and '按照中华人民共和国财政部颁布的企业会计准则' in compact
                        and _LEGAL + '全体股东' in compact):
                    audits.append(dict(page=n, excerpt=text))
        if len(audits) != 1:
            raise ValueError('所选报表前缺少唯一明确的中国企业会计准则审计意见')
        inc = _parse(tables['income'], _INCOME, '其他综合收益的税后净额')
        bal = {**_parse(tables['assets'], _ASSETS, _FOOTER), **_parse(tables['liabilities'], _LIABILITIES, _FOOTER)}
        delta_label = '现金及现金等价物净(减少)/增加额' if year == 2024 else '现金及现金等价物净增加/(减少)额'
        cash = _parse(tables['cash'], _CASH + [(delta_label,'59(g)'), ('加：年初现金及现金等价物余额',None),
                        ('年末现金及现金等价物余额','59(i)')], _FOOTER)
        detail['pages'] = dict(start=tables['income']['page'], end=tables['income']['page'])
        detail['evidence'] = {label: dict(values=[str(v) for v in row['values']], pages=dict(start=row['page'],end=row['page']),
                                         excerpt=row['excerpt'], note=row['note']) for label, row in inc.items()}
        all_checks = dict(income=[], balance=[], cash=[])
        def values(rows, label):
            return rows[label]['values']
        def signs(rows, labels, positive):
            for label in labels:
                if any(v < 0 if positive else v > 0 for v in values(rows, label)):
                    raise ValueError('原文正负呈列不符合限定模板：' + label)
        def equation(section, rows, left, right):
            for offset, scope in ((0,'合并'),(2,'公司')):
                check = dict(key=f'{section}_{len(all_checks[section])+1}', label=scope+'：'+' + '.join(right)+' = '+left, passed=False)
                for period, i in (('current',offset),('previous',offset+1)):
                    computed = sum((values(rows, label)[i] for label in right), Decimal(0))
                    reported = values(rows, left)[i]; difference = computed - reported
                    check[period] = dict(left=str(computed), right=str(reported), difference=str(difference), passed=abs(difference)<=1)
                check['passed'] = check['current']['passed'] and check['previous']['passed']
                all_checks[section].append(check)
        costs = ['减：营业成本','税金及附加','销售费用','管理费用','研发费用','财务费用']
        signs(inc, costs + ['信用减值损失','资产减值损失','减：营业外支出','减：所得税费用'], False)
        signs(inc, ['营业收入','其中：利息费用','利息收入','加：营业外收入'], True)
        operating = ['营业收入'] + costs + ['加：其他收益','投资收益','公允价值变动收益','信用减值损失','资产减值损失','资产处置收益']
        equation('income', inc, '营业利润', operating)
        equation('income', inc, '利润总额', ['营业利润','加：营业外收入','减：营业外支出'])
        equation('income', inc, '净利润', ['利润总额','减：所得税费用'])
        equation('income', inc, '净利润', ['持续经营净利润','终止经营净利润'])
        equation('income', inc, '净利润', ['归属于母公司股东的净利润','少数股东损益'])
        if any(values(inc,'少数股东损益')[i] != 0 or values(bal,'少数股东权益')[i] != 0 for i in (2,3)):
            raise ValueError('公司列包含非零少数股东项目')
        groups = [('流动资产合计', _ASSETS, '流动资产', '流动资产合计'),
                  ('非流动资产合计', _ASSETS, '非流动资产', '非流动资产合计'),
                  ('流动负债合计', _LIABILITIES, '流动负债', '流动负债合计'),
                  ('非流动负债合计', _LIABILITIES, '非流动负债', '非流动负债合计'),
                  ('归属于母公司股东权益合计', _LIABILITIES, '股东权益', '归属于母公司股东权益合计')]
        for total, specs, first, last in groups:
            labels = [x[0] for x in specs]; components = labels[labels.index(first)+1:labels.index(last)]
            if first != '股东权益': signs(bal, components + [total], True)
            equation('balance', bal, total, components)
        equation('balance', bal, '资产总计', ['流动资产合计','非流动资产合计'])
        equation('balance', bal, '负债合计', ['流动负债合计','非流动负债合计'])
        equation('balance', bal, '股东权益合计', ['归属于母公司股东权益合计','少数股东权益'])
        equation('balance', bal, '资产总计', ['负债合计','股东权益合计'])
        equation('balance', bal, '负债及股东权益总计', ['资产总计'])
        if any(v <= 0 for v in values(bal,'资产总计')): raise ValueError('资产总计必须大于零')
        incoming = [
            ['销售商品、提供劳务收到的现金','收到其他与经营活动有关的现金'],
            ['收回投资收到的现金','取得投资收益所收到的现金','处置固定资产、油气资产、无形资产和其他长期资产收回的现金净额','处置子公司及其他营业单位收到的现金净额'],
            ['吸收投资收到的现金','取得借款收到的现金']]
        outgoing = [
            ['购买商品、接受劳务支付的现金','支付给职工以及为职工支付的现金','支付的各项税费','支付其他与经营活动有关的现金'],
            ['购建固定资产、油气资产、无形资产和其他长期资产支付的现金','投资支付的现金','取得子公司及其他营业单位支付的现金净额'],
            ['偿还债务支付的现金','同一控制下企业合并支付的对价','分配股利、利润或偿付利息支付的现金','支付其他与筹资活动有关的现金']]
        net_labels = ['经营活动产生的现金流量净额','投资活动使用的现金流量净额','筹资活动使用的现金流量净额']
        for kind, ins, outs, net in zip(('经营','投资','筹资'), incoming, outgoing, net_labels):
            tin = kind+'活动现金流入小计'; tout = kind+'活动现金流出小计'
            signs(cash, ins + [tin], True); signs(cash, outs + [tout], False)
            equation('cash', cash, tin, ins); equation('cash', cash, tout, outs)
            equation('cash', cash, net, [tin,tout])
        signs(cash, ['其中：子公司吸收少数股东投资收到的现金'], True)
        signs(cash, ['其中：子公司支付给少数股东的股利、利润'], False)
        for sub,total in [('其中：子公司吸收少数股东投资收到的现金','吸收投资收到的现金'),
                          ('其中：子公司支付给少数股东的股利、利润','分配股利、利润或偿付利息支付的现金')]:
            if any(values(cash,sub)[i] != 0 for i in (2,3)):
                raise ValueError('公司列包含非零子公司少数股东现金项目')
            if any(abs(values(cash,sub)[i]) > abs(values(cash,total)[i]) for i in range(4)):
                raise ValueError('现金子项目超过所属总项')
        equation('cash', cash, delta_label, net_labels+['汇率变动对现金及现金等价物的影响'])
        equation('cash', cash, '年末现金及现金等价物余额', ['加：年初现金及现金等价物余额',delta_label])
        signs(cash, ['加：年初现金及现金等价物余额','年末现金及现金等价物余额'], True)
        detail['checks'] = all_checks['income']
        failed['statement_reconciliation'] = all_checks
        if not all(c['passed'] for section in all_checks.values() for c in section):
            detail.update(status='mismatch', note='中国石油专用四列表中存在超出舍入容差的金额关系差额，未输出标准化金额。')
            failed['failure_reason'] = detail['note']; return failed
        income_lines = tables['income']['lines']
        note_start = next((i for i, line in enumerate(income_lines) if _compact(line).startswith('注释：')), None)
        comparison_note = ''
        if note_start is not None:
            note_end = next((i for i in range(note_start, len(income_lines)) if _compact(income_lines[i]) == _FOOTER), None)
            if note_end is None: raise ValueError('比较期说明边界缺失')
            comparison_note = ' '.join(income_lines[note_start:note_end])
        def figures(section, rows, fields, source_pages):
            figure = dict(unit='人民币百万元',page_number=min(source_pages),end_page_number=max(source_pages),metric_sources={})
            for field,label in fields.items():
                row=rows[label]
                figure['current_'+field],figure['previous_'+field]=map(float,row['values'][:2])
                figure['metric_sources'][field]=dict(page_number=row['page'],end_page_number=row['page'],labels=[label],
                    statement='合并及公司报表（仅取合并列；公司两列也已核对）',
                    comparison_basis='本年报合并比较栏原值；不替换为其他年度披露。'+(comparison_note if section == 'income' else ''))
            return figure
        detail.update(status='passed',passed=True,note='中国石油限定模板的四列利润组成、税前至税后及利润归属均通过Decimal检查；资产负债和完整现金关系亦通过，仍待人工核验。')
        return dict(template=PETROCHINA_TEMPLATE,
            income=figures('income',inc,dict(revenue='营业收入',net_profit='归属于母公司股东的净利润'),[tables['income']['page']]),
            balance=figures('balance',bal,dict(total_assets='资产总计',total_liabilities='负债合计'),[tables['assets']['page'],tables['liabilities']['page']]),
            cash=figures('cash',cash,dict(operating_cash_flow=net_labels[0]),[tables['cash']['page']]),
            income_reconciliation=detail,statement_reconciliation=all_checks,
            audit_evidence=audits[0], comparison_note=comparison_note)
    except (ValueError,InvalidOperation,IndexError,TypeError) as error:
        detail.update(status='missing_evidence',passed=False,note='中国石油专用模板证据不足：'+str(error)+'。')
        failed['failure_reason']=detail['note']; return failed
