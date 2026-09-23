"""Strict CITIC Securities 2024/2025 PRC full-report statement profile.

Separate group/parent tables, year-specific column/row layout, exact Decimal
reconciliation. Cash net movements retain their signs inside disclosed sections.
A failed profile never returns partial financial candidates.
"""
from decimal import Decimal
import re

CITIC_SECURITIES_TEMPLATE = 'securities_citic_separate_yuan_v1'
_LEGAL = '中信证券股份有限公司'
_UNIT = '(除另有注明外，金额单位均为人民币元)'
_FOOTER = '后附财务报表附注为本财务报表的组成部分。'
_AMOUNT = r'(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
_NUMBER = re.compile(rf'^(?:-|{_AMOUNT}|\({_AMOUNT}\))$')
_SKIP = {'资产', '负债', '股东权益', '金融投资：', '一、经营活动产生的现金流量',
         '二、投资活动产生的现金流量', '三、筹资活动产生的现金流量',
         '(一)按经营持续性分类', '(二)按所有权归属分类', '按经营持续性分类'}


def _compact(text):
    return re.sub(r'\s+', '', text).replace('（', '(').replace('）', ')')


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _label(text):
    return re.sub(r'^(?:[一二三四五六七八九十]+、|\([一二三四五六七八九十]+\)|\(\d+\)|\d+[.．])', '', _compact(text))


def is_citic_annual_report_identity(company, pages, year):
    """Exact front-matter legal name and A-share table, within 20 physical pages."""
    if (str(company.get('code')) != '600030' or company.get('name') != '中信证券'
            or type(year) is not int or year not in (2024, 2025)):
        return False
    front = [(n, t) for n, t in pages if 1 <= n <= 20]
    heading = _compact('\n'.join(t for n, t in front if n <= 2))
    if any(t in heading for t in ('年度报告摘要', '年报摘要', '年度报告英文', '年报英文')):
        return False
    texts = [_compact(t) for _, t in front]
    legal = any('公司的中文名称中信证券股份有限公司公司的中文简称中信证券公司的外文名称' in t for t in texts)
    code = '600030' if year == 2024 else '600030.SH'
    stock = any(f'A股上交所中信证券{code}不适用H股' in t for t in texts)
    # 2024's extractable cover puts the year after 年度报告; 2025's cover
    # digits have a broken font map, so bind exact annual headers in the text.
    if year == 2024:
        title = any(n == 1 and '中信证券年度报告2024CITICSECURITIESAnnualReport股票代码:600030' == _compact(t) for n, t in front)
    else:
        title = any(f'{year}年年度报告' == _compact(line) for _, t in front for line in t.splitlines())
    return legal and stock and title


def _window(pages, year, kind):
    parent, section = kind.split('_')
    title = ('合并' if parent == 'group' else '母公司') + {'income': '利润表', 'balance': '资产负债表', 'cash': '现金流量表'}[section]
    starts = [i for i, (_, text) in enumerate(pages) if title in [_compact(s) for s in _lines(text)]]
    if len(starts) != 1:
        raise ValueError('主表缺失或重复：' + title)
    start = starts[0]; count = len(_ROW_LAYOUTS[year][kind]); pieces = []
    for offset in range(count):
        if start + offset >= len(pages):
            raise ValueError('缺少连续报表页：' + title)
        number, text = pages[start + offset]
        lines = _lines(text); cs = [_compact(s) for s in lines]
        heading = title + ('(续)' if offset else '')
        if number != pages[start][0] + offset or cs.count(heading) != 1:
            raise ValueError('报表续页或物理页不连续：' + title)
        pos = cs.index(heading)
        if pos != 2 or not re.fullmatch(r'第\d+页', cs[0]):
            raise ValueError('报表前缀包含未支持的内容：' + title)
        date = f'{year}年12月31日' if section == 'balance' else f'{year}年度'
        if pos == 0 or cs[pos - 1] != _LEGAL or cs[pos + 1:pos + 4] != [date, _UNIT, '本集团' if parent == 'group' else '本公司']:
            raise ValueError('编制公司、年度、人民币单位或主体表头不匹配：' + title)
        note = '附注六' if parent == 'parent' and section != 'cash' else '附注五'
        if section == 'balance':
            expected = ([note, f'{year}年', '12月31日', f'{year-1}年', '12月31日'] if year == 2024
                else [f'{year}年', f'{year-1}年', note, '12月31日', '12月31日'])
        else:
            expected = [note, f'{year}年度', f'{year-1}年度']
            if year == 2025 and kind == 'group_income':
                expected += ['(已重述)']
        cursor = pos + 4
        if cs[cursor:cursor + len(expected)] != expected:
            raise ValueError('本期/比较期列或重述标记不匹配：' + title)
        cursor += len(expected)
        if cs.count(_FOOTER) != 1:
            raise ValueError('报表结束标记缺失或重复：' + title)
        end = cs.index(_FOOTER)
        suffix = [str(number - (4 if year == 2024 else 3))]
        if year == 2024:
            suffix += ['第十节财务报告']
        elif number % 2:
            suffix += ['2025年年度报告', _LEGAL, '财', '务', '报', '告']
        if cs[end + 1:] != suffix:
            raise ValueError('报表页脚包含未支持的内容：' + title)
        if end <= cursor:
            raise ValueError('报表为空：' + title)
        approval = [i for i in range(cursor, end) if cs[i].startswith('此财务报表已于')]
        if approval:
            if len(approval) != 1 or offset != count - 1:
                raise ValueError('董事会批准位置不明确：' + title)
            expected_approval = [f'此财务报表已于{year+1}年3月26日获董事会批准。',
                '张佑君', '公司负责人', '张皓', '主管会计工作负责人', '西志颖', '会计机构负责人']
            if cs[approval[0]:end] != expected_approval:
                raise ValueError('董事会批准或签名区包含未支持的内容：' + title)
            end = approval[0]
        elif offset == count - 1:
            raise ValueError('报表末页缺少董事会批准及签名区：' + title)
        pieces.append((number, lines[cursor:end]))
    if start + count < len(pages) and title + '(续)' in [_compact(s) for s in _lines(pages[start + count][1])]:
        raise ValueError('存在未支持的额外续页：' + title)
    return dict(pages=pieces, title=title, restated=year == 2025 and kind == 'group_income')


def _parse_page(number, lines, expected_layout, expected_sections):
    records = []; text_parts = []; tokens = []; note = None; index = 0; sections = []
    while index < len(lines):
        line = lines[index]; compact = _compact(line)
        if compact in _SKIP:
            if text_parts or tokens or note:
                raise ValueError('行内插入未完成的章节标题')
            sections.append(compact)
            index += 1
            continue
        if compact == '八、每股收益':
            if text_parts or tokens or note or index + 1 >= len(lines) or not re.fullmatch(r'\d{1,2}', lines[index + 1]):
                raise ValueError('每股收益附注格式不明确')
            sections.append(compact + '@' + lines[index + 1])
            index += 2
            continue
        parts = line.split()
        if parts and all(_NUMBER.fullmatch(part) for part in parts):
            if not text_parts:
                raise ValueError('金额缺少明确科目')
            tokens.extend(parts); index += 1
            if index == len(lines) or not all(_NUMBER.fullmatch(part) for part in lines[index].split()):
                if len(tokens) != 2:
                    raise ValueError('每行必须为本期/比较期两个金额')
                label = _label(''.join(text_parts))
                if any(len(t) > 32 for t in tokens):
                    raise ValueError('金额字符长度超出专项支持范围')
                values = tuple(Decimal(0) if t == '-' else (-1 if t.startswith('(') else 1) * Decimal(t.strip('()').replace(',', '')) for t in tokens)
                if any(not v.is_finite() or abs(v) > Decimal('1e15') for v in values):
                    raise ValueError('金额绝对值超出人民币元专项支持范围')
                records.append(dict(label=label, note=note, values=values, page_number=number,
                    excerpt=' ｜ '.join(text_parts + ([note] if note else []) + tokens)))
                text_parts = []; tokens = []; note = None
        elif re.fullmatch(r'\d{1,2}', compact):
            if not text_parts or note is not None or tokens:
                raise ValueError('附注编号不能充当金额或额外列')
            note = compact; index += 1
        else:
            # Reject amount-like damaged tokens, rather than silently treating
            # them as the boundary after two already parsed amounts.
            if (re.match(r'^(?:\(?[\d,]+[,.]|\d+xyz|[-−－]|不适用|N/?A)', compact, re.I)
                    and not re.match(r'^\d+[.．][\u4e00-\u9fff]', compact)):
                raise ValueError('损坏或未知金额符号')
            text_parts.append(line); index += 1
    if text_parts or tokens or note:
        raise ValueError('报表末尾有未完成的科目或金额')
    actual = '|'.join(r['label'] + ('@' + r['note'] if r['note'] else '') for r in records)
    if actual != expected_layout or '|'.join(sections) != expected_sections:
        raise ValueError('科目、附注、顺序或两列完整性不匹配')
    return records


def _read_window(window, layouts, sections):
    records = [r for (number, lines), layout, section in zip(window['pages'], layouts, sections)
               for r in _parse_page(number, lines, layout, section)]
    if len({r['label'] for r in records}) != len(records):
        raise ValueError('报表存在重复科目')
    return {r['label']: r for r in records}


def _audit(pages, start, year):
    found = []
    for number, text in pages:
        if not start - 10 <= number < start:
            continue
        compact = _compact(text)
        if all(s in compact for s in ('中信证券股份有限公司全体股东：', '一、审计意见',
                f'{year}年12月31日的合并及母公司资产负债表', f'{year}年度的合并及母公司利润表',
                '中华人民共和国财政部颁布的企业会计准则')):
            found.append(dict(page_number=number, end_page_number=number, excerpt=text))
    if len(found) != 1:
        raise ValueError('缺少与年度、公司和所选报表对应的中国准则审计意见')
    return found[0]


class _Mismatch(ValueError):
    pass


def extract_citic_securities_statements(pages, year):
    if not is_citic_annual_report_identity(dict(code='600030', name='中信证券'), pages, year):
        return None
    checks = {'income': [], 'balance': [], 'cash': []}
    windows = {}
    try:
        if len({n for n, _ in pages}) != len(pages) or [n for n, _ in pages] != sorted(n for n, _ in pages):
            raise ValueError('物理页号重复或倒序')
        windows = {k: _window(pages, year, k) for k in _ROW_LAYOUTS[year]}
        tables = {k: _read_window(windows[k], _ROW_LAYOUTS[year][k], _SECTION_LAYOUTS[year][k]) for k in windows}
        audit = _audit(pages, windows['group_balance']['pages'][0][0], year)
        restatement = None
        if year == 2025:
            evidence = [(n, t) for n, t in pages if all(s in _compact(t) for s in (
                '31重要会计政策变更', '标准仓单交易相关会计处理实施问答',
                '原按总额确认收入成本', '差额计入投资收益', '对可比期间财务报表数据进行追溯调整'))]
            if len(evidence) != 1:
                raise ValueError('缺少唯一的仓单会计政策比较期追溯说明')
            restatement = dict(page_number=evidence[0][0], end_page_number=evidence[0][0], excerpt=evidence[0][1])

        def value(kind, label):
            return tables[kind][label]['values']

        def eq(kind, key, label, left, *signed_parts):
            row = dict(key=kind + '_' + key, label=('合并：' if kind.startswith('group') else '母公司：') + label)
            for i, period in enumerate(('current', 'previous')):
                right = sum(sign * part[i] for sign, part in signed_parts)
                diff = left[i] - right
                row[period] = dict(left=str(left[i]), right=str(right), difference=str(diff), passed=abs(diff) <= Decimal('.01'))
            row['passed'] = row['current']['passed'] and row['previous']['passed']
            checks[kind.split('_')[1]].append(row)
            if not row['passed']:
                raise _Mismatch(row['label'] + '金额不一致')

        def add(kind, key, left_label, labels, description):
            eq(kind, key, description, value(kind, left_label), *[(1, value(kind, s)) for s in labels])

        def nonnegative(kind, labels):
            if any(v < 0 for label in labels for v in value(kind, label)):
                raise ValueError('不支持的负金额呈列：' + kind)

        def subset(kind, child, parent):
            if any(not Decimal(0) <= a <= b for a, b in zip(value(kind, child), value(kind, parent))):
                raise ValueError('其中项目超出总项：' + child)

        for owner in ('group', 'parent'):
            kind = owner + '_income'; rows = tables[kind]
            exchange = next(label for label in rows if label in ('汇兑收益', '汇兑收益(损失以负号列示)'))
            disposal = '资产处置收益(损失以负号列示)' if owner == 'group' else '资产处置收益'
            add(kind, 'revenue', '营业收入', ['手续费及佣金净收入', '利息净收入', '投资收益', '公允价值变动收益(损失以负号列示)', exchange, disposal, '其他收益', '其他业务收入'], '营业收入等于八项组成合计')
            eq(kind, 'interest', '利息收入减利息支出等于利息净收入', value(kind, '利息净收入'), (1, value(kind, '其中：利息收入')), (-1, value(kind, '利息支出')))
            costs = ['税金及附加', '业务及管理费', '信用减值损失(转回以负号列示)', '其他业务成本']
            if owner == 'group':
                costs.insert(3, '其他资产减值损失')
            add(kind, 'cost', '营业支出', costs, '营业支出等于明确列示的费用合计（转回保留负号）')
            nonnegative(kind, ['其中：利息收入', '利息支出', '营业支出', '税金及附加', '业务及管理费', '其他业务成本', '减：营业外支出', '减：所得税费用'])
            if owner == 'group':
                nonnegative(kind, ['其他资产减值损失'])
            eq(kind, 'operating', '营业收入减营业支出等于营业利润', value(kind, '营业利润'), (1, value(kind, '营业收入')), (-1, value(kind, '营业支出')))
            eq(kind, 'pretax', '营业利润加营业外收入减营业外支出等于利润总额', value(kind, '利润总额'), (1, value(kind, '营业利润')), (1, value(kind, '加：营业外收入')), (-1, value(kind, '减：营业外支出')))
            eq(kind, 'tax', '利润总额减所得税费用等于净利润', value(kind, '净利润'), (1, value(kind, '利润总额')), (-1, value(kind, '减：所得税费用')))
            continuing = ['持续经营净利润'] + (['终止经营净利润'] if year == 2024 else [])
            add(kind, 'continuity', '净利润', continuing, '净利润等于原表经营持续性分类合计')
            if owner == 'group':
                add(kind, 'attribution', '净利润', ['归属于母公司股东的净利润', '少数股东损益'], '归母净利润加少数股东损益等于合并净利润')
                add(kind, 'oci_attribution', '其他综合收益的税后净额', ['归属于母公司股东的其他综合收益的税后净额', '归属于少数股东的其他综合收益的税后净额'], '其他综合收益归属合计')
                add(kind, 'total_attribution', '综合收益总额', ['归属于母公司股东的综合收益总额', '归属于少数股东的综合收益总额'], '综合收益归属合计')
                add(kind, 'parent_total', '归属于母公司股东的综合收益总额', ['归属于母公司股东的净利润', '归属于母公司股东的其他综合收益的税后净额'], '归母净利润加归母其他综合收益等于归母综合收益')
                add(kind, 'minority_total', '归属于少数股东的综合收益总额', ['少数股东损益', '归属于少数股东的其他综合收益的税后净额'], '少数损益加少数其他综合收益等于少数综合收益')
            oci = '归属于母公司股东的其他综合收益的税后净额' if owner == 'group' else '其他综合收益的税后净额'
            add(kind, 'oci_split', oci, ['不能重分类进损益的其他综合收益', '将重分类进损益的其他综合收益'], '可重分类与不可重分类的其他综合收益合计')
            add(kind, 'oci_nonrecycle', '不能重分类进损益的其他综合收益', ['其他权益工具投资公允价值变动', '权益法下不能转损益的其他综合收益'] + (['其他'] if owner == 'group' else []), '不可重分类其他综合收益组成合计')
            add(kind, 'oci_recycle', '将重分类进损益的其他综合收益', ['权益法下可转损益的其他综合收益', '其他债权投资公允价值变动', '其他债权投资信用损失准备'] + (['外币财务报表折算差额'] if owner == 'group' else []), '可重分类其他综合收益组成合计')
            add(kind, 'comprehensive', '综合收益总额', ['净利润', '其他综合收益的税后净额'], '净利润加其他综合收益等于综合收益总额')

            kind = owner + '_balance'; rows = tables[kind]; labels = list(rows)
            assets = labels[:labels.index('资产总计')]
            assets = [s for s in assets if not s.startswith('其中：')]
            liabs = labels[labels.index('资产总计') + 1:labels.index('负债合计')]
            equity = ['股本', '其他权益工具', '资本公积', '其他综合收益', '盈余公积', '一般风险准备', '未分配利润']
            nonnegative(kind, assets + liabs + ['资产总计', '负债合计'])
            if any(v <= 0 for v in value(kind, '资产总计')):
                raise ValueError('资产总计必须为正')
            add(kind, 'assets', '资产总计', assets, '资产各主项等于资产总计')
            add(kind, 'liabs', '负债合计', liabs, '负债各主项等于负债合计')
            add(kind, 'equity_parts', '归属于母公司股东权益合计' if owner == 'group' else '股东权益合计', equity, '股东权益各主项合计')
            if owner == 'group':
                add(kind, 'equity_attribution', '股东权益合计', ['归属于母公司股东权益合计', '少数股东权益'], '归母权益加少数股东权益等于权益合计')
            add(kind, 'balance', '资产总计', ['负债合计', '股东权益合计'], '资产等于负债加股东权益')
            add(kind, 'totals', '负债和股东权益总计', ['资产总计'], '资产与负债权益两侧总额一致')
            for child, parent in [('其中：客户资金存款', '货币资金'), ('其中：客户备付金', '结算备付金'), ('其中：永续债', '其他权益工具')]:
                subset(kind, child, parent)
            if year == 2025:
                subset(kind, '其中：数据资源', '无形资产')

            kind = owner + '_cash'; rows = tables[kind]; labels = list(rows); cursor = 0; flows = []
            for category in ('经营', '投资', '筹资'):
                inflow = category + '活动现金流入小计'; outflow = category + '活动现金流出小计'; flow = category + '活动产生的现金流量净额'
                stop = labels.index(inflow); inparts = [s for s in labels[cursor:stop] if not s.startswith('其中：')]
                outparts = [s for s in labels[stop+1:labels.index(outflow)] if not s.startswith('其中：')]
                add(kind, category + '_in', inflow, inparts, category + '现金流入主项合计')
                add(kind, category + '_out', outflow, outparts, category + '现金流出主项合计')
                eq(kind, category + '_net', category + '现金流入减流出等于净额', value(kind, flow), (1, value(kind, inflow)), (-1, value(kind, outflow)))
                # Disclosed net-movement rows can be negative. In 2024 the
                # parent's comparative operating inflow subtotal is also
                # negative because it includes those net movements. Keep that
                # subtotal signed; ordinary receipts/payments remain positive.
                net_rows = {'为交易目的而持有的金融资产净变动额', '为交易目的而持有的金融资产现金净额', '代理买卖证券收到的现金净额', '回购业务资金净增加额', '融出资金净增加额', '拆入资金净减少额'}
                nonnegative(kind, [s for s in inparts + outparts if s not in net_rows]
                    + ([inflow, outflow] if category != '经营' else []))
                flows.append(flow); cursor = labels.index(flow) + 1
            add(kind, 'delta', '现金及现金等价物的变动净额', flows + ['汇率变动对现金及现金等价物的影响'], '三类现金净额加汇率影响等于现金变动')
            add(kind, 'closing', '年末现金及现金等价物余额', ['加：年初现金及现金等价物余额', '现金及现金等价物的变动净额'], '期初现金加净变动等于期末现金')
            nonnegative(kind, ['加：年初现金及现金等价物余额', '年末现金及现金等价物余额'])
            subset(kind, '其中：发行永续债收到的现金', '吸收投资收到的现金')
            if owner == 'group':
                subset(kind, '其中：子公司支付给少数股东的股利、利润', '分配股利、利润或偿付利息支付的现金')

        comparison = (f'2025年合并利润表2024年比较列明确标注已重述，保留本报告原值，不替换为2024年原报告值；仓单交易会计政策追溯说明见物理第{restatement["page_number"]}页；其他表列头未标注重述。' if year == 2025 else '保留本年度报告本期与比较列原值；本表列头未标注重述。')
        def figures(section, mapping):
            kind = 'group_' + section; window = windows[kind]
            result = dict(unit='人民币元', page_number=window['pages'][0][0], end_page_number=window['pages'][-1][0], metric_sources={})
            for key, label in mapping.items():
                row = tables[kind][label]
                result['current_' + key], result['previous_' + key] = map(float, row['values'])
                result['metric_sources'][key] = dict(page_number=row['page_number'], end_page_number=row['page_number'], labels=[label],
                    statement='独立合并报表（仅取本集团列）', comparison_basis=comparison, excerpt=row['excerpt'],
                    accounting_basis='归母净利润（合并报表）' if key == 'net_profit' else '合并口径')
            return result
        reconciliation = dict(status='passed', passed=True, unit='人民币元', header_years=[year, year-1], pages=dict(start=windows['group_income']['pages'][0][0], end=windows['group_income']['pages'][-1][0]), checks=checks['income'],
            note='中信证券中国准则专项：合并及母公司两期分别检验收入、正数费用、利润归属和其他综合收益；不验证每股收益分母。',
            rounding_note='所有关系使用Decimal；每列允许差额不超过人民币0.01元。', tax_presentation='费用为正数，利润总额减所得税费用；明确减值转回保留负号。', comparison_basis=comparison)
        return dict(template=CITIC_SECURITIES_TEMPLATE,
            income=figures('income', {'revenue':'营业收入', 'net_profit':'归属于母公司股东的净利润'}),
            balance=figures('balance', {'total_assets':'资产总计', 'total_liabilities':'负债合计'}),
            cash=figures('cash', {'operating_cash_flow':'经营活动产生的现金流量净额'}),
            income_reconciliation=reconciliation, statement_reconciliation=checks, audit_evidence=audit,
            restatement_evidence=restatement, comparison_note=comparison)
    except (ValueError, KeyError, IndexError) as error:
        return dict(template=CITIC_SECURITIES_TEMPLATE, income=None, balance=None, cash=None,
            failure_reason=str(error), statement_reconciliation=checks,
            income_reconciliation=dict(status='mismatch' if isinstance(error, _Mismatch) else 'missing_evidence', passed=False,
                unit='人民币元', header_years=[year, year-1], checks=checks['income'], pages=None,
                note='中信证券专项未通过：' + str(error)))


# Each entry pins observed labels and note cells, never report amounts.
_ROW_LAYOUTS = {
    2024: {
        'group_balance': [
            '货币资金@1|其中：客户资金存款|结算备付金@2|其中：客户备付金|融出资金@3|衍生金融资产@4|买入返售金融资产@5|应收款项@6|存出保证金@7|交易性金融资产@8|其他债权投资@9|其他权益工具投资@10|长期股权投资@12|投资性房地产@13|固定资产@14|在建工程@15|无形资产@16|商誉@17|递延所得税资产@18|使用权资产@19|其他资产@20|资产总计',
            '短期借款@22|应付短期融资款@23|拆入资金@24|交易性金融负债@25|衍生金融负债@4|卖出回购金融资产款@26|代理买卖证券款@27|代理承销证券款@28|应付职工薪酬@29|应交税费@30|应付款项@31|预计负债@32|长期借款@33|应付债券@34|递延所得税负债@18|合同负债|租赁负债@35|其他负债@36|负债合计',
            '股本@38|其他权益工具@39|其中：永续债|资本公积@40|其他综合收益@41|盈余公积@42|一般风险准备@43|未分配利润@44|归属于母公司股东权益合计|少数股东权益@45|股东权益合计|负债和股东权益总计',
        ],
        'parent_balance': [
            '货币资金|其中：客户资金存款|结算备付金|其中：客户备付金|融出资金|衍生金融资产|买入返售金融资产|应收款项|存出保证金|交易性金融资产|其他债权投资|其他权益工具投资|长期股权投资@1|投资性房地产|固定资产|在建工程|无形资产|商誉|递延所得税资产|使用权资产|其他资产|资产总计',
            '应付短期融资款|拆入资金|交易性金融负债|衍生金融负债|卖出回购金融资产款|代理买卖证券款|代理承销证券款|应付职工薪酬|应交税费|应付款项|预计负债|应付债券|合同负债|租赁负债|其他负债|负债合计',
            '股本|其他权益工具|其中：永续债|资本公积|其他综合收益|盈余公积|一般风险准备|未分配利润|股东权益合计|负债和股东权益总计',
        ],
        'group_income': [
            '营业收入|手续费及佣金净收入@46|其中：经纪业务手续费净收入|投资银行业务手续费净收入|资产管理业务手续费净收入|利息净收入@47|其中：利息收入|利息支出|投资收益@48|其中：对联营公司和合营公司的投资收益|公允价值变动收益(损失以负号列示)@49|汇兑收益|资产处置收益(损失以负号列示)|其他收益|其他业务收入@50|营业支出|税金及附加@51|业务及管理费@52|信用减值损失(转回以负号列示)@53|其他资产减值损失@54|其他业务成本@55',
            '营业利润|加：营业外收入@56|减：营业外支出@57|利润总额|减：所得税费用@58|净利润|持续经营净利润|终止经营净利润|归属于母公司股东的净利润|少数股东损益',
            '其他综合收益的税后净额|归属于母公司股东的其他综合收益的税后净额@41|不能重分类进损益的其他综合收益|其他权益工具投资公允价值变动|权益法下不能转损益的其他综合收益|其他|将重分类进损益的其他综合收益|权益法下可转损益的其他综合收益|其他债权投资公允价值变动|其他债权投资信用损失准备|外币财务报表折算差额|归属于少数股东的其他综合收益的税后净额',
            '综合收益总额|归属于母公司股东的综合收益总额|归属于少数股东的综合收益总额|基本每股收益(元/股)|稀释每股收益(元/股)',
        ],
        'parent_income': [
            '营业收入|手续费及佣金净收入@2|其中：经纪业务手续费净收入|投资银行业务手续费净收入|资产管理业务手续费净收入|利息净收入@3|其中：利息收入|利息支出|投资收益@4|其中：对联营企业和合营企业的投资收益(损失以负号列示)|公允价值变动收益(损失以负号列示)@5|汇兑收益(损失以负号列示)|资产处置收益|其他收益|其他业务收入|营业支出|税金及附加|业务及管理费@6|信用减值损失(转回以负号列示)|其他业务成本',
            '营业利润|加：营业外收入|减：营业外支出|利润总额|减：所得税费用|净利润|持续经营净利润|终止经营净利润',
            '其他综合收益的税后净额|不能重分类进损益的其他综合收益|其他权益工具投资公允价值变动|权益法下不能转损益的其他综合收益|将重分类进损益的其他综合收益|权益法下可转损益的其他综合收益|其他债权投资公允价值变动|其他债权投资信用损失准备|综合收益总额',
        ],
        'group_cash': [
            '代理买卖证券收到的现金净额|回购业务资金净增加额|收取利息、手续费及佣金的现金|收到其他与经营活动有关的现金@60|经营活动现金流入小计|为交易目的而持有的金融资产现金净额|融出资金净增加额|拆入资金净减少额|支付利息、手续费及佣金的现金|支付给职工以及为职工支付的现金|支付的各项税费|支付其他与经营活动有关的现金@61|经营活动现金流出小计|经营活动产生的现金流量净额@62',
            '收回投资收到的现金|取得投资收益收到的现金|处置固定资产、无形资产和其他长期资产收回的现金净额|收到其他与投资活动有关的现金|投资活动现金流入小计|投资支付的现金|购建固定资产、无形资产和其他长期资产所支付的现金|支付其他与投资活动有关的现金|投资活动现金流出小计|投资活动产生的现金流量净额',
            '吸收投资收到的现金|其中：发行永续债收到的现金|取得借款收到的现金|发行债券收到的现金|筹资活动现金流入小计|偿还债务支付的现金|分配股利、利润或偿付利息支付的现金|其中：子公司支付给少数股东的股利、利润|支付其他与筹资活动有关的现金|筹资活动现金流出小计|筹资活动产生的现金流量净额|汇率变动对现金及现金等价物的影响|现金及现金等价物的变动净额@62|加：年初现金及现金等价物余额|年末现金及现金等价物余额@63',
        ],
        'parent_cash': [
            '为交易目的而持有的金融资产现金净额|代理买卖证券收到的现金净额|收取利息、手续费及佣金的现金|回购业务资金净增加额|收到其他与经营活动有关的现金|经营活动现金流入小计|融出资金净增加额|拆入资金净减少额|支付利息、手续费及佣金的现金|支付给职工以及为职工支付的现金|支付的各项税费|支付其他与经营活动有关的现金|经营活动现金流出小计|经营活动产生的现金流量净额@62',
            '收回投资收到的现金|取得投资收益收到的现金|收到其他与投资活动有关的现金|投资活动现金流入小计|投资支付的现金|购建固定资产、无形资产和其他长期资产所支付的现金|支付其他与投资活动有关的现金|投资活动现金流出小计|投资活动产生的现金流量净额',
            '吸收投资收到的现金|其中：发行永续债收到的现金|发行债券收到的现金|筹资活动现金流入小计|偿还债务支付的现金|分配股利、利润或偿付利息支付的现金|支付其他与筹资活动有关的现金|筹资活动现金流出小计|筹资活动产生的现金流量净额|汇率变动对现金及现金等价物的影响|现金及现金等价物的变动净额@62|加：年初现金及现金等价物余额|年末现金及现金等价物余额',
        ],
    },
    2025: {
        'group_balance': [
            '货币资金@1|其中：客户资金存款|结算备付金@2|其中：客户备付金|融出资金@3|衍生金融资产@4|买入返售金融资产@5|应收款项@6|存出保证金@7|交易性金融资产@8|其他债权投资@9|其他权益工具投资@10|长期股权投资@12|投资性房地产@13|固定资产@14|在建工程@15|无形资产@16|其中：数据资源|商誉@17|递延所得税资产@18|使用权资产@19|其他资产@20|资产总计',
            '短期借款@22|应付短期融资款@23|拆入资金@24|交易性金融负债@25|衍生金融负债@4|卖出回购金融资产款@26|代理买卖证券款@27|代理承销证券款@28|应付职工薪酬@29|应交税费@30|应付款项@31|预计负债@32|长期借款@33|应付债券@34|递延所得税负债@18|租赁负债@35|其他负债@36|负债合计',
            '股本@38|其他权益工具@39|其中：永续债|资本公积@40|其他综合收益@41|盈余公积@42|一般风险准备@43|未分配利润@44|归属于母公司股东权益合计|少数股东权益@45|股东权益合计|负债和股东权益总计',
        ],
        'parent_balance': [
            '货币资金|其中：客户资金存款|结算备付金|其中：客户备付金|融出资金|衍生金融资产|买入返售金融资产|应收款项|存出保证金|交易性金融资产|其他债权投资|其他权益工具投资|长期股权投资@1|投资性房地产|固定资产|在建工程|无形资产|其中：数据资源|商誉|递延所得税资产|使用权资产|其他资产|资产总计',
            '应付短期融资款|拆入资金|交易性金融负债|衍生金融负债|卖出回购金融资产款|代理买卖证券款|代理承销证券款|应付职工薪酬|应交税费|应付款项|预计负债|应付债券|租赁负债|其他负债|负债合计',
            '股本|其他权益工具|其中：永续债|资本公积|其他综合收益|盈余公积|一般风险准备|未分配利润|股东权益合计|负债和股东权益总计',
        ],
        'group_income': [
            '营业收入|手续费及佣金净收入@46|其中：经纪业务手续费净收入|投资银行业务手续费净收入|资产管理业务手续费净收入|利息净收入@47|其中：利息收入|利息支出|投资收益@48|其中：对联营公司和合营公司的投资收益|公允价值变动收益(损失以负号列示)@49|汇兑收益(损失以负号列示)|资产处置收益(损失以负号列示)|其他收益|其他业务收入|营业支出|税金及附加@50|业务及管理费@51|信用减值损失(转回以负号列示)@52|其他资产减值损失|其他业务成本',
            '营业利润|加：营业外收入@53|减：营业外支出@54|利润总额|减：所得税费用@55|净利润|持续经营净利润|归属于母公司股东的净利润|少数股东损益',
            '其他综合收益的税后净额|归属于母公司股东的其他综合收益的税后净额@41|不能重分类进损益的其他综合收益|其他权益工具投资公允价值变动|权益法下不能转损益的其他综合收益|其他|将重分类进损益的其他综合收益|权益法下可转损益的其他综合收益|其他债权投资公允价值变动|其他债权投资信用损失准备|外币财务报表折算差额|归属于少数股东的其他综合收益的税后净额',
            '综合收益总额|归属于母公司股东的综合收益总额|归属于少数股东的综合收益总额|基本每股收益(元/股)|稀释每股收益(元/股)',
        ],
        'parent_income': [
            '营业收入|手续费及佣金净收入@2|其中：经纪业务手续费净收入|投资银行业务手续费净收入|资产管理业务手续费净收入|利息净收入@3|其中：利息收入|利息支出|投资收益@4|其中：对联营企业和合营企业的投资收益(损失以负号列示)|公允价值变动收益(损失以负号列示)@5|汇兑收益|资产处置收益|其他收益|其他业务收入|营业支出|税金及附加|业务及管理费@6|信用减值损失(转回以负号列示)|其他业务成本',
            '营业利润|加：营业外收入|减：营业外支出|利润总额|减：所得税费用|净利润|持续经营净利润',
            '其他综合收益的税后净额|不能重分类进损益的其他综合收益|其他权益工具投资公允价值变动|权益法下不能转损益的其他综合收益|将重分类进损益的其他综合收益|权益法下可转损益的其他综合收益|其他债权投资公允价值变动|其他债权投资信用损失准备|综合收益总额',
        ],
        'group_cash': [
            '为交易目的而持有的金融资产净变动额|代理买卖证券收到的现金净额|回购业务资金净增加额|收取利息、手续费及佣金的现金|收到其他与经营活动有关的现金@57|经营活动现金流入小计|融出资金净增加额|拆入资金净减少额|支付利息、手续费及佣金的现金|支付给职工以及为职工支付的现金|支付的各项税费|支付其他与经营活动有关的现金@58|经营活动现金流出小计|经营活动产生的现金流量净额@59',
            '收回投资收到的现金|取得投资收益收到的现金|处置固定资产、无形资产和其他长期资产收回的现金净额|处置子公司及其他营业单位收到的现金净额|收到其他与投资活动有关的现金|投资活动现金流入小计|投资支付的现金|购建固定资产、无形资产和其他长期资产所支付的现金|支付其他与投资活动有关的现金|投资活动现金流出小计|投资活动产生的现金流量净额',
            '吸收投资收到的现金|其中：发行永续债收到的现金|取得借款收到的现金|发行债券收到的现金|筹资活动现金流入小计|偿还债务支付的现金|分配股利、利润或偿付利息支付的现金|其中：子公司支付给少数股东的股利、利润|支付其他与筹资活动有关的现金|筹资活动现金流出小计|筹资活动产生的现金流量净额',
            '汇率变动对现金及现金等价物的影响|现金及现金等价物的变动净额@59|加：年初现金及现金等价物余额|年末现金及现金等价物余额@60',
        ],
        'parent_cash': [
            '为交易目的而持有的金融资产现金净额|代理买卖证券收到的现金净额|收取利息、手续费及佣金的现金|回购业务资金净增加额|收到其他与经营活动有关的现金|经营活动现金流入小计|融出资金净增加额|拆入资金净减少额|支付利息、手续费及佣金的现金|支付给职工以及为职工支付的现金|支付的各项税费|支付其他与经营活动有关的现金|经营活动现金流出小计|经营活动产生的现金流量净额@59',
            '收回投资收到的现金|取得投资收益收到的现金|处置固定资产、无形资产和其他长期资产收回的现金净额|投资活动现金流入小计|投资支付的现金|购建固定资产、无形资产和其他长期资产所支付的现金|支付其他与投资活动有关的现金|投资活动现金流出小计|投资活动产生的现金流量净额|吸收投资收到的现金|其中：发行永续债收到的现金|发行债券收到的现金|筹资活动现金流入小计|偿还债务支付的现金|分配股利、利润或偿付利息支付的现金|支付其他与筹资活动有关的现金|筹资活动现金流出小计|筹资活动产生的现金流量净额',
            '汇率变动对现金及现金等价物的影响|现金及现金等价物的变动净额@59|加：年初现金及现金等价物余额|年末现金及现金等价物余额',
        ],
    },
}

_SECTION_LAYOUTS = {2024: {'group_balance': ['资产|金融投资：', '负债', '股东权益'], 'parent_balance': ['资产|金融投资：', '负债', '股东权益'], 'group_income': ['', '(一)按经营持续性分类|(二)按所有权归属分类', '', '八、每股收益@59'], 'parent_income': ['', '按经营持续性分类', ''], 'group_cash': ['一、经营活动产生的现金流量', '二、投资活动产生的现金流量', '三、筹资活动产生的现金流量'], 'parent_cash': ['一、经营活动产生的现金流量', '二、投资活动产生的现金流量', '三、筹资活动产生的现金流量']}, 2025: {'group_balance': ['资产|金融投资：', '负债', '股东权益'], 'parent_balance': ['资产|金融投资：', '负债', '股东权益'], 'group_income': ['', '(一)按经营持续性分类|(二)按所有权归属分类', '', '八、每股收益@56'], 'parent_income': ['', '按经营持续性分类', ''], 'group_cash': ['一、经营活动产生的现金流量', '二、投资活动产生的现金流量', '三、筹资活动产生的现金流量', ''], 'parent_cash': ['一、经营活动产生的现金流量', '二、投资活动产生的现金流量|三、筹资活动产生的现金流量', '']}}
