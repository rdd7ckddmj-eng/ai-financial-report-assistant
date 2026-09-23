"""CMOC 2025 traditional-Chinese PRC-GAAP report, original text only.

This is an issuer/year/layout profile, not a script conversion or OCR fallback.
It consumes every observed consolidated primary row and exact note/year header;
parent-company tables and other accounting bases never supply missing cells.
"""
from decimal import Decimal, InvalidOperation
import re

CMOC_TEMPLATE = 'cmoc_2025_cas_traditional_yuan_v1'
_LEGAL = '洛陽欒川鉬業集團股份有限公司'
_NUM = re.compile(r'^(?:–|(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}|\((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}\))$')
_FOOTER = ['本財務報表由下列負責人簽署：', '法定代表人：', '主管會計工作負責人：', '會計機構負責人：']


def _c(text):
    return re.sub(r'\s+', '', text)


def _lines(text):
    return [s.strip() for s in text.splitlines() if s.strip()]


def is_cmoc_annual_report_identity(company, pages, year):
    """A bounded cover identity check; audit/accounting basis is checked below."""
    if str(company.get('code')) != '603993' or company.get('name') != '洛阳钼业' or type(year) is not int or year != 2025:
        return False
    covers = [t for n, t in pages if n == 1]
    if len(covers) != 1:
        return False
    text = _c(covers[0])
    return (text.startswith('僅供識別' + _LEGAL + '2025年度報告')
            and '股份代號:603993.SH03993.HK' in text and 'CMOCGroupLimited' in text
            and '摘要' not in text and 'Summary' not in text)


def _tables(pages, title, first_labels, header_middle):
    found = []
    for number, text in pages:
        lines = _lines(text)
        if title not in lines:
            continue
        if len(text) > 25000 or lines.count(title) != 1 or len(lines) < 5 or lines[2] != title:
            raise ValueError('报表标题位置、数量或页面长度不匹配：' + title)
        if lines[:2] != [(_LEGAL if number % 2 else '二零二五年年報'), str(number - 1)]:
            raise ValueError('报表页眉与印刷页码不匹配')
        idx = len(found)
        if idx >= len(first_labels):
            raise ValueError('重复合并报表页')
        try:
            body = lines.index(first_labels[idx])
        except ValueError:
            raise ValueError('缺失精确首行：' + title)
        if [_c(x) for x in lines[3:body]] != [_c(x) for x in header_middle[idx]]:
            raise ValueError('单位、期间、附注或双列表头不匹配：' + title)
        found.append(dict(page=number, lines=lines[body:]))
    if len(found) != len(first_labels):
        raise ValueError('合并报表页缺失：' + title)
    return found


def _read(table, specs, footer=()):
    lines, cursor, result, section = table['lines'], 0, {}, ''
    for label, note in specs:
        start = cursor; joined = ''; end = None
        for j in range(cursor, min(cursor + 4, len(lines))):
            joined += _c(lines[j])
            if joined == _c(label):
                end = j; break
        if end is None:
            raise ValueError('缺失、重复或未知行：' + label)
        cursor = end + 1
        if note is False:
            section = label; continue
        if note is not None:
            if cursor >= len(lines) or _c(lines[cursor]) != note:
                raise ValueError('附注编号不匹配：' + label)
            cursor += 1
        values = []
        for _ in range(2):
            if cursor >= len(lines) or len(lines[cursor]) > 32 or not _NUM.fullmatch(lines[cursor]):
                raise ValueError('两列金额缺失或格式错误：' + label)
            token = lines[cursor]; cursor += 1
            value = Decimal(0) if token == '–' else Decimal(token.strip('()').replace(',', ''))
            if token.startswith('('):
                value = -value
            if abs(value) > Decimal('1e15'):
                raise ValueError('金额超出限定范围')
            values.append(value)
        key = '非流動存貨' if label == '存貨' and section == '非流動資產：' else label
        if key in result:
            raise ValueError('重复金额科目')
        result[key] = dict(values=values, page=table['page'], label=label, note=note,
                           excerpt='\n'.join(lines[start:cursor]))
    if lines[cursor:] != list(footer):
        raise ValueError('末行后有额外金额、未知行或不完整表尾')
    return result


_ASSETS = [('流動資產：', False),
 ('貨幣資金', '（五）1'),
 ('交易性金融資產', '（五）2'),
 ('衍生金融資產', '（五）3'),
 ('應收賬款', '（五）4'),
 ('應收款項融資', '（五）5'),
 ('預付款項', '（五）6'),
 ('其他應收款', '（五）7'),
 ('其中：應收利息', '（五）7.2'),
 ('應收股利', '（五）7.3'),
 ('存貨', '（五）8'),
 ('一年內到期的非流動資產', '（五）9'),
 ('其他流動資產', '（五）10'),
 ('流動資產合計', None),
 ('非流動資產：', False),
 ('長期股權投資', '（五）11'),
 ('其他權益工具投資', '（五）12'),
 ('其他非流動金融資產', '（五）13'),
 ('固定資產', '（五）14'),
 ('在建工程', '（五）15'),
 ('存貨', '（五）8'),
 ('使用權資產', '（五）16'),
 ('無形資產', '（五）17'),
 ('商譽', '（五）18'),
 ('長期待攤費用', '（五）19'),
 ('遞延所得稅資產', '（五）20'),
 ('其他非流動資產', '（五）21'),
 ('非流動資產合計', None),
 ('資產總計', None)]

_LIABILITIES = [('流動負債：', False),
 ('短期借款', '（五）23'),
 ('交易性金融負債', '（五）24'),
 ('衍生金融負債', '（五）25'),
 ('應付票據', '（五）26'),
 ('應付賬款', '（五）27'),
 ('合同負債', '（五）28'),
 ('應付職工薪酬', '（五）29'),
 ('應交稅費', '（五）30'),
 ('其他應付款', '（五）31'),
 ('其中：應付股利', '（五）31.2'),
 ('一年內到期的非流動負債', '（五）32'),
 ('其他流動負債', '（五）33'),
 ('流動負債合計', None),
 ('非流動負債：', False),
 ('長期借款', '（五）34'),
 ('租賃負債', '（五）35'),
 ('長期應付職工薪酬', '（五）36'),
 ('預計負債', '（五）37'),
 ('遞延收益', '（五）38'),
 ('遞延所得稅負債', '（五）20'),
 ('其他非流動負債', '（五）39'),
 ('非流動負債合計', None),
 ('負債合計', None)]

_EQUITY = [('股東權益：', False),
 ('股本', '（五）40'),
 ('其他權益工具', '（五）41'),
 ('其中：永續債', None),
 ('資本公積', '（五）42'),
 ('減：庫存股', '（五）43'),
 ('其他綜合收益', '（五）44'),
 ('專項儲備', '（五）45'),
 ('盈餘公積', '（五）46'),
 ('未分配利潤', '（五）47'),
 ('歸屬於母公司股東權益合計', None),
 ('少數股東權益', None),
 ('股東權益合計', None),
 ('負債和股東權益總計', None)]

_INCOME = [('一、營業總收入', None),
 ('其中：營業收入', '（五）48'),
 ('二、營業總成本', None),
 ('其中：營業成本', '（五）48'),
 ('稅金及附加', '（五）49'),
 ('銷售費用', '（五）50'),
 ('管理費用', '（五）51'),
 ('研發費用', None),
 ('財務費用', '（五）52'),
 ('其中：利息費用', None),
 ('利息收入', None),
 ('加：其他收益', '（五）53'),
 ('投資收益（損失以「-」號填列）', '（五）54'),
 ('其中：對聯營企業和合營企業的投資收益', None),
 ('公允價值變動收益（損失以「-」號填列）', '（五）55'),
 ('信用減值利得（損失以「-」號填列）', '（五）56'),
 ('資產減值利得（損失以「-」號填列）', '（五）57'),
 ('資產處置收益（損失以「-」號填列）', None),
 ('三、營業利潤（虧損以「-」號填列）', None),
 ('加：營業外收入', '（五）58'),
 ('減：營業外支出', '（五）59'),
 ('四、利潤總額（虧損總額以「-」號填列）', None),
 ('減：所得稅費用', '（五）60'),
 ('五、淨利潤（淨虧損以「-」號填列）', None),
 ('（一）按經營持續性分類：', False),
 ('1.持續經營淨利潤（淨虧損以「-」號填列）', None),
 ('2.終止經營淨利潤（淨虧損以「-」號填列）', '（十五）1'),
 ('（二）按所有權歸屬分類：', False),
 ('1.歸屬於母公司股東的淨利潤（淨虧損以「-」號填列）', None),
 ('2.少數股東損益（淨虧損以「-」號填列）', None)]

_CASH_A = [('一、經營活動產生的現金流量：', False),
 ('銷售商品、提供勞務收到的現金', None),
 ('收到的稅費返還', None),
 ('收到的其他與經營活動有關的現金', '（五）61(1)'),
 ('經營活動現金流入小計', None),
 ('購買商品、接受勞務支付的現金', None),
 ('支付給職工以及為職工支付的現金', None),
 ('支付的各項稅費', None),
 ('支付的其他與經營活動有關的現金', '（五）61(1)'),
 ('經營活動現金流出小計', None),
 ('經營活動產生的現金流量淨額', '（五）62(1)'),
 ('二、投資活動產生的現金流量：', False),
 ('收回投資所收到的現金', '（五）61(2)'),
 ('取得投資收益所收到的現金', None),
 ('處置固定資產、無形資產和其他長期資產收回的現金淨額', None),
 ('處置子公司及其他營業單位收到的現金淨額', None),
 ('收到其他與投資活動有關的現金', '（五）61(2)'),
 ('投資活動現金流入小計', None),
 ('購建固定資產、無形資產和其他長期資產支付的現金', None),
 ('投資支付的現金', '（五）61(2)'),
 ('取得子公司及其他營業單位支付的現金淨額', None),
 ('支付其他與投資活動有關的現金', '（五）61(2)'),
 ('投資活動現金流出小計', None),
 ('投資活動產生的現金流量淨額', None)]

_CASH_B = [('三、籌資活動產生的現金流量：', False),
 ('取得借款收到的現金', None),
 ('收到的其他與籌資活動有關的現金', '（五）61(3)'),
 ('籌資活動現金流入小計', None),
 ('償還債務所支付的現金', None),
 ('分配股利、利潤和償付利息所支付的現金', None),
 ('其中：子公司支付給少數股東的股利', None),
 ('支付其他與籌資活動有關的現金', '（五）61(3)'),
 ('籌資活動現金流出小計', None),
 ('籌資活動產生的現金流量淨額', None),
 ('四、匯率變動對現金及現金等價物的影響額', None),
 ('五、現金及現金等價物淨增加額', None),
 ('加：年初現金及現金等價物餘額', '（五）62(2)'),
 ('六、年末現金及現金等價物餘額', '（五）62(2)')]


def extract_cmoc_statements(pages, year):
    """Return None for a nonmatch; recognized failures carry no figures."""
    pages = list(pages)
    if not is_cmoc_annual_report_identity(dict(code='603993', name='洛阳钼业'), pages, year):
        return None
    detail = dict(status='missing_evidence', passed=False, checks=[], unit='元', pages=None,
                  header_years=[2025, 2024], tolerance='0.01', evidence={},
                  note='洛阳钼业2025繁体中国企业会计准则报表待核对。')
    failed = dict(template=CMOC_TEMPLATE, income=None, balance=None, cash=None,
                  income_reconciliation=detail, failure_reason='')
    try:
        numbers = [n for n, _ in pages]
        if any(type(n) is not int or not 1 <= n <= 1000 for n in numbers) or numbers != sorted(set(numbers)):
            raise ValueError('物理页重复、缺少顺序或页码无效')
        by_page = dict(pages)
        dates = ['2025年12月31日', '2024年12月31日']
        bal = _tables(pages, '合併資產負債表', ['流動資產：', '流動負債：', '股東權益：'], [
            ['2025年12月31日','人民幣元','資產','附註'] + dates,
            ['2025年12月31日','負債和股東權益','附註'] + dates,
            ['2025年12月31日','負債和股東權益','附註'] + dates])
        period = ['2025年12月31日止年度']
        inc = _tables(pages, '合併利潤表', ['一、營業總收入','六、其他綜合收益的稅後淨額'], [
            period + ['人民幣元','項目','附註','2025年度','2024年度'],
            period + ['項目','附註','2025年度','2024年度']])
        cf = _tables(pages, '合併現金流量表', ['一、經營活動產生的現金流量：','三、籌資活動產生的現金流量：'], [
            period + ['人民幣元','項目','附註','本年金額','上年金額'],
            period + ['項目','附註','本年金額','上年金額']])
        start = bal[0]['page']
        if [t['page'] for t in bal + inc + cf] != [start+i for i in (0,1,2,5,6,8,9)]:
            raise ValueError('连续合并报表页和公司报表分界不匹配')
        for offset,title in ((3,'公司資產負債表'),(4,'公司資產負債表'),(7,'公司利潤表'),(10,'母公司現金流量表')):
            if title not in _lines(by_page.get(start+offset,'')):
                raise ValueError('独立公司报表边界缺失，不能借数')
        audit = by_page.get(start-4, '')
        audit_compact = _c(audit)
        required = ['審計報告','德師報(審)字(26)第P04032號',_LEGAL+'全體股東：',
                    '2025年12月31日的合併及母公司資產負債表',
                    '2025年度的合併及母公司利潤表',
                    '我們認為，後附的財務報表在所有重大方面按照企業會計準則的規定編製，公允反映了']
        if not all(s in audit_compact for s in required):
            raise ValueError('缺少本公司2025中国企业会计准则审计意见')
        audit_end = _c(by_page.get(start-1,''))
        if not all(s in audit_end for s in ['德勤華永會計師事務所（特殊普通合夥）','中國註冊會計師：','2026年3月27日']):
            raise ValueError('审计机构、审计日期或审计末页不匹配')
        basis = by_page.get(start+16, '')
        if ('（二）、財務報表的編製基礎編製基礎本集團執行財政部頒佈的企業會計準則及相關規定。' not in _c(basis)
                or '國際財務報告會計準則' in basis or '國際財務報告準則' in basis):
            raise ValueError('缺少明确的财政部准则编制依据')
        rows_i = _read(inc[0], _INCOME)
        rows_b = {**_read(bal[0], _ASSETS), **_read(bal[1], _LIABILITIES),
                  **_read(bal[2], _EQUITY, ['附註為財務報表的組成部分'] + _FOOTER)}
        rows_c = {**_read(cf[0], _CASH_A), **_read(cf[1], _CASH_B, _FOOTER)}
        all_checks = dict(income=[],balance=[],cash=[])
        def eq(section, rows, total, positive, negative=()):
            check = dict(key=f'{section}_{len(all_checks[section])+1}',label=' + '.join(positive)+(' - '+' - '.join(negative) if negative else '')+' = '+total)
            for key,j in (('current',0),('previous',1)):
                computed = sum((rows[x]['values'][j] for x in positive),Decimal(0)) - sum((rows[x]['values'][j] for x in negative),Decimal(0))
                value = rows[total]['values'][j];delta=computed-value
                check[key] = dict(left=str(computed),right=str(value),difference=str(delta),passed=abs(delta)<=Decimal('0.01'))
            check['passed'] = check['current']['passed'] and check['previous']['passed']
            all_checks[section].append(check)
        def positive(rows,labels):
            if any(v<0 for label in labels for v in rows[label]['values']):
                raise ValueError('限定正数呈列项目出现负值')
        costs = ['其中：營業成本','稅金及附加','銷售費用','管理費用','研發費用','財務費用']
        gains = ['加：其他收益','投資收益（損失以「-」號填列）','公允價值變動收益（損失以「-」號填列）',
                 '信用減值利得（損失以「-」號填列）','資產減值利得（損失以「-」號填列）','資產處置收益（損失以「-」號填列）']
        op='三、營業利潤（虧損以「-」號填列）';pbt='四、利潤總額（虧損總額以「-」號填列）';net='五、淨利潤（淨虧損以「-」號填列）'
        owner='1.歸屬於母公司股東的淨利潤（淨虧損以「-」號填列）';minority='2.少數股東損益（淨虧損以「-」號填列）'
        positive(rows_i,['一、營業總收入','其中：營業收入','其中：利息費用','利息收入','減：營業外支出'] + costs)
        eq('income',rows_i,'一、營業總收入',['其中：營業收入'])
        eq('income',rows_i,'二、營業總成本',costs)
        eq('income',rows_i,op,['一、營業總收入']+gains,['二、營業總成本'])
        eq('income',rows_i,pbt,[op,'加：營業外收入'],['減：營業外支出'])
        eq('income',rows_i,net,[pbt],['減：所得稅費用'])
        eq('income',rows_i,net,['1.持續經營淨利潤（淨虧損以「-」號填列）','2.終止經營淨利潤（淨虧損以「-」號填列）'])
        eq('income',rows_i,net,[owner,minority])
        # Inventory occurs twice in different asset classifications; retain both.
        groups=[('流動資產合計',_ASSETS,'流動資產：','流動資產合計'),('非流動資產合計',_ASSETS,'非流動資產：','非流動資產合計'),
                ('流動負債合計',_LIABILITIES,'流動負債：','流動負債合計'),('非流動負債合計',_LIABILITIES,'非流動負債：','非流動負債合計')]
        for total,specs,first,last in groups:
            labels=[x[0] for x in specs];parts=labels[labels.index(first)+1:labels.index(last)]
            parts=[x for x in parts if not x.startswith('其中：') and x!='應收股利']
            if first=='非流動資產：':parts=['非流動存貨' if x=='存貨' else x for x in parts]
            positive(rows_b,parts+[total]);eq('balance',rows_b,total,parts)
        eq('balance',rows_b,'資產總計',['流動資產合計','非流動資產合計'])
        eq('balance',rows_b,'負債合計',['流動負債合計','非流動負債合計'])
        eq('balance',rows_b,'歸屬於母公司股東權益合計',['股本','其他權益工具','資本公積','其他綜合收益','專項儲備','盈餘公積','未分配利潤'],['減：庫存股'])
        eq('balance',rows_b,'股東權益合計',['歸屬於母公司股東權益合計','少數股東權益'])
        eq('balance',rows_b,'資產總計',['負債合計','股東權益合計'])
        eq('balance',rows_b,'負債和股東權益總計',['資產總計'])
        for sub,total in [('其中：應收利息','其他應收款'),('應收股利','其他應收款'),('其中：應付股利','其他應付款'),('其中：永續債','其他權益工具')]:
            positive(rows_b,[sub])
            if any(rows_b[sub]['values'][i]>rows_b[total]['values'][i] for i in range(2)):
                raise ValueError('子项目超过所属总项')
        if any(rows_b['其中：應收利息']['values'][i] + rows_b['應收股利']['values'][i]
               > rows_b['其他應收款']['values'][i] for i in range(2)):
            raise ValueError('应收利息与应收股利合计超过其他应收款')
        for kind,first,last in [('經營','一、經營活動產生的現金流量：','經營活動產生的現金流量淨額'),('投資','二、投資活動產生的現金流量：','投資活動產生的現金流量淨額'),('籌資','三、籌資活動產生的現金流量：','籌資活動產生的現金流量淨額')]:
            labels=[x[0] for x in _CASH_A+_CASH_B];tin=kind+'活動現金流入小計';tout=kind+'活動現金流出小計'
            incoming=labels[labels.index(first)+1:labels.index(tin)]
            outgoing=[x for x in labels[labels.index(tin)+1:labels.index(tout)] if not x.startswith('其中：')]
            positive(rows_c,incoming+outgoing+[tin,tout])
            eq('cash',rows_c,tin,incoming);eq('cash',rows_c,tout,outgoing);eq('cash',rows_c,last,[tin],[tout])
        delta='五、現金及現金等價物淨增加額';opening='加：年初現金及現金等價物餘額';ending='六、年末現金及現金等價物餘額'
        eq('cash',rows_c,delta,['經營活動產生的現金流量淨額','投資活動產生的現金流量淨額','籌資活動產生的現金流量淨額','四、匯率變動對現金及現金等價物的影響額'])
        eq('cash',rows_c,ending,[delta,opening]);positive(rows_c,[opening,ending,'其中：子公司支付給少數股東的股利'])
        if any(rows_c['其中：子公司支付給少數股東的股利']['values'][i]>rows_c['分配股利、利潤和償付利息所支付的現金']['values'][i] for i in range(2)):
            raise ValueError('少数股东股利子项超过对应现金流出')
        if any(v<=0 for v in rows_b['資產總計']['values']):raise ValueError('总资产必须大于零')
        detail['pages']=dict(start=inc[0]['page'],end=inc[0]['page'])
        detail['evidence']={label:dict(values=[str(v) for v in row['values']],pages=dict(start=row['page'],end=row['page']),excerpt=row['excerpt'],note=row['note']) for label,row in rows_i.items()}
        detail['checks']=all_checks['income'];failed['statement_reconciliation']=all_checks
        if not all(c['passed'] for section in all_checks.values() for c in section):
            detail.update(status='mismatch',note='两期完整报表组成关系存在超过0.01元的差额，未放行金额。');failed['failure_reason']=detail['note'];return failed
        def figures(rows,fields,source_pages):
            result=dict(unit='元',original_unit='人民幣元',page_number=min(source_pages),end_page_number=max(source_pages),metric_sources={})
            for key,label in fields.items():
                row=rows[label];result['current_'+key],result['previous_'+key]=map(float,row['values'])
                result['metric_sources'][key]=dict(page_number=row['page'],end_page_number=row['page'],labels=[row['label']],statement='合併報表（繁體原文；中國企業會計準則）',accounting_basis=('归母净利润（合并报表；繁体原文；中国企业会计准则）' if key=='net_profit' else '合并口径（繁体原文；中国企业会计准则）'),comparison_basis='同一份2025完整年報的2024比較欄；未以其他來源替換。',excerpt=row['excerpt'])
            return result
        detail.update(status='passed',passed=True,note='限定洛阳钼业2025繁体中国企业会计准则报表：两期利润、资产负债及现金流组成通过金额关系检查；仍待人工核验。')
        return dict(template=CMOC_TEMPLATE,
            income=figures(rows_i,dict(revenue='其中：營業收入',net_profit=owner),[inc[0]['page']]),
            balance=figures(rows_b,dict(total_assets='資產總計',total_liabilities='負債合計'),[t['page'] for t in bal]),
            cash=figures(rows_c,dict(operating_cash_flow='經營活動產生的現金流量淨額'),[t['page'] for t in cf]),
            income_reconciliation=detail,statement_reconciliation=all_checks,
            audit_evidence=dict(page=start-4,excerpt=audit,audit_end_page=start-1,audit_end_excerpt=by_page[start-1],basis_page=start+16,basis_excerpt=basis))
    except (ValueError,IndexError,KeyError,InvalidOperation,TypeError) as error:
        detail.update(status='missing_evidence',passed=False,note='洛阳钼业限定繁体模板证据不足：'+str(error)+'。')
        failed['failure_reason']=detail['note'];return failed
