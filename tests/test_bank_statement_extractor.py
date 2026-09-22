"""Synthetic balanced bank tables; no real company figures in fixtures."""
import pytest
from src.bank_statement_extractor import BANK_TEMPLATE, extract_bank_statements
from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.financial_snapshot_review import (build_financial_snapshot_review,
    confirm_snapshot_metric, build_exportable_review_workpaper, CORE_METRIC_KEYS)
from src.research_case_financial_review_bridge import _validate_workpaper
from src.research_case_financial_review_bridge import build_financial_review_research_case_patch
from src.research_case import new_research_case, apply_case_patch


def pages():
    def table(title, rows):
        body = title + '\n（除特别注明外，货币单位均以人民币百万元列示）\n项目\n附注\n2025年\n2024年\n'
        for label, value in rows:
            formatted = f'({abs(value)})' if value < 0 else str(value)
            body += f'{label}\n{formatted}\n{formatted}\n'
        return body
    income = [('利息收入',1000), ('利息支出',-200), ('净利息收入',800),
        ('手续费及佣金收入',100), ('手续费及佣金支出',-10), ('净手续费及佣金收入',90),
        ('其他净收入小计',110), ('营业收入合计',1000), ('营业支出合计',-400),
        ('营业利润',600), ('加：营业外收入',10), ('减：营业外支出',-5), ('利润总额',605),
        ('减：所得税费用',-105), ('净利润',500), ('本行股东的净利润',490), ('少数股东的净利润',10)]
    balance = [('资产合计',2000), ('负债合计',1500), ('股东权益合计',500), ('负债及股东权益总计',2000)]
    cash = []
    for kind, incoming, outgoing in [('经营',1000,-500), ('投资',100,-300), ('筹资',100,-150)]:
        cash += [(kind+'活动现金流入小计', incoming), (kind+'活动现金流出小计',outgoing),
                 (kind+'活动产生的现金流量净额',incoming+outgoing)]
    cash += [('汇率变动对现金及现金等价物的影响额',-10), ('现金及现金等价物净（减少）/增加额',240),
             ('加：年初现金及现金等价物余额',100), ('年末现金及现金等价物余额',340)]
    return [(1,table('合并资产负债表',balance)), (2,table('合并利润表',income)),
            (3,table('合并现金流量表',cash))]


def test_balanced_bank_tables_use_revenue_total_and_parent_profit():
    result = extract_bank_statements(pages(),2025)
    assert result['income']['current_revenue'] == 1000
    assert result['income']['current_net_profit'] == 490
    assert result['balance']['current_total_assets'] == 2000
    assert result['cash']['current_operating_cash_flow'] == 500
    assert result['income']['unit'] == '人民币百万元'


@pytest.mark.parametrize('index,old,new', [
    (0,'资产合计\n2000','资产合计\n2100'),
    (0,'股东权益合计\n500','股东权益合计\n510'),
    (1,'营业收入合计\n1000','营业收入合计\n1100'),
    (1,'本行股东的净利润\n490','本行股东的净利润\n480'),
    (2,'经营活动现金流出小计\n(500)','经营活动现金流出小计\n500'),
    (2,'年末现金及现金等价物余额\n340','年末现金及现金等价物余额\n350'),
    (2,'340\n340','340\n350'),  # prior-year checks are required too
    (0,'人民币百万元','人民币万元'),
    (2,'2024年','2023年'),
])
def test_invalid_bank_layout_never_falls_back_to_generic_figures(index,old,new):
    data = pages()
    n, text = data[index]
    assert old in text
    data[index] = n, text.replace(old,new)
    result = extract_bank_statements(data,2025)
    assert result['template'] == BANK_TEMPLATE
    assert all(result[k] is None for k in ('income','balance','cash'))


def test_nonbank_layout_is_not_classified_from_company_name():
    assert extract_bank_statements([(1,'某银行\n营业收入\n100\n90')],2025) is None


def test_contents_page_titles_do_not_hide_actual_statement_windows():
    contents = '目录\n合并资产负债表\n7-8\n合并利润表\n11-12\n合并现金流量表\n19-21'
    result = extract_bank_statements([(1,contents)] + [(n+1,t) for n,t in pages()],2025)
    assert result['income']['current_net_profit'] == 490
    assert result['income']['page_number'] == 3


def test_bank_net_profit_without_parent_row_stays_unavailable_with_reason():
    data = [(n,t.replace('本行股东的净利润\n490\n490\n','')
                .replace('净利息收入','利息净收入')) for n,t in pages()]
    result = extract_bank_statements(data,2025)
    assert result['template'] == BANK_TEMPLATE
    assert all(result[k] is None for k in ('income','balance','cash'))
    assert '不能用“净利润”自动替代' in result['failure_reason']
    company = build_company_identity('000001','测试银行')
    candidate = build_candidate_report_result(company,
        dict(report_year=2025,published_date='2026-03-21',title='测试银行2025年年度报告',
             url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',
        [dict(page_number=n,text=t) for n,t in data])
    snapshot = build_on_demand_financial_snapshot(company,candidate)
    assert snapshot['status'] == 'needs_review'
    assert result['failure_reason'] in snapshot['limitations']
    assert all(v is None for v in snapshot['ratios'].values())


@pytest.mark.parametrize('heading', ['银行资产负债表', '银 行资 产负债表',
                                    '银\n行资产负债表', '母 公 司资产负债表'])
def test_missing_consolidated_equity_cannot_be_borrowed_from_next_statement(heading):
    data = pages()
    number, text = data[0]
    text = text.replace('股东权益合计\n500\n500\n', '')
    data[0] = number, text + '\n' + heading + '\n股东权益合计\n500\n500\n'
    result = extract_bank_statements(data,2025)
    assert all(result[k] is None for k in ('income', 'balance', 'cash'))


def test_valid_consolidated_table_ignores_conflicting_parent_totals():
    data = pages()
    number, text = data[0]
    data[0] = number, text + '\n银 行资产负债表\n资产合计\n999\n888\n'
    result = extract_bank_statements(data,2025)
    assert result['balance']['current_total_assets'] == 2000


def test_explicit_million_unit_header_variant_is_supported():
    data = [(n,t.replace('（除特别注明外，货币单位均以人民币百万元列示）',
                         '单位：人民币百万元')) for n,t in pages()]
    assert extract_bank_statements(data,2025)['income']['current_revenue'] == 1000


def test_body_unit_mention_cannot_override_wrong_header_currency():
    data = [(n,t.replace('（除特别注明外，货币单位均以人民币百万元列示）',
                         '单位：美元百万元') + '\n（除特别注明外，货币单位均以人民币百万元列示）')
            for n,t in pages()]
    assert extract_bank_statements(data,2025)['income'] is None


def test_explicit_cash_balance_label_variants_keep_same_reconciliations():
    data = [(n,t.replace('净（减少）/增加额','净增加额').replace('现金等价物余额','现金等价物'))
            for n,t in pages()]
    assert extract_bank_statements(data,2025)['cash']['current_operating_cash_flow'] == 500


@pytest.mark.parametrize('header', [
    '2024年\n2025年',
    '2025年\n2024年\n2023年',
    '2025年\n2025年\n2024年',
])
def test_year_columns_must_be_current_then_previous_even_when_report_date_matches(header):
    data = pages()
    number, text = data[0]
    text = text.replace('合并资产负债表\n','合并资产负债表\n2025年12月31日\n')
    text = text.replace('附注\n2025年\n2024年','附注\n' + header)
    data[0] = number, text
    result = extract_bank_statements(data,2025)
    assert all(result[k] is None for k in ('income','balance','cash'))


def test_bank_snapshot_review_and_receiver_keep_generic_ratios_disabled():
    company = build_company_identity('600036','测试银行')
    report = dict(report_year=2025,published_date='2026-03-28',
        title='测试银行2025年年度报告',url='https://static.cninfo.com.cn/test.pdf')
    candidate = build_candidate_report_result(company,report,b'%PDF-synthetic',
        [dict(page_number=n,text=t) for n,t in pages()])
    snapshot = build_on_demand_financial_snapshot(company,candidate)
    assert snapshot['status'] == 'ready_for_human_review'
    assert snapshot['report']['statement_template'] == BANK_TEMPLATE
    assert all(v is None for v in snapshot['ratios'].values())
    assert snapshot['metrics'][0]['current_yuan'] == 1_000_000_000
    assert snapshot['metrics'][1]['source']['excerpt'].startswith('本行股东的净利润')
    review = build_financial_snapshot_review(snapshot)
    for key in CORE_METRIC_KEYS:
        review = confirm_snapshot_metric(review,key)
    workpaper = build_exportable_review_workpaper(review)
    assert all(v is None for v in workpaper['ratios'].values())
    case = new_research_case('bank-test',company,mode='current',as_of_date=None,
        effective_market_date='2026-09-21',created_at='2026-09-21T00:00:00+00:00')
    clean = _validate_workpaper(case,workpaper)
    assert clean['report']['statement_template'] == BANK_TEMPLATE
    assert all(v is None for v in clean['ratios'].values())
    patch = build_financial_review_research_case_patch(case,workpaper,
        patch_id='bank-write-test',emitted_at=workpaper['exported_at'])
    updated = apply_case_patch(case,patch)
    assert len(updated['evidence']) == 5
    import json
    assert '金融机构模板不计算普通公司比例' in json.dumps(updated,ensure_ascii=False)


@pytest.mark.parametrize('date_header', ['2025 年度', '2025\n年度'])
def test_unsupported_bank_layout_keeps_bank_policy_with_spaced_date(date_header):
    text = ('合并利润表\n' + date_header + '\n人民币百万元\n附注五\n2025年度\n2024年度\n'
        '一、营业收入\n1000\n900\n利息净收入\n800\n700\n'
        '手续费及佣金净收入\n100\n100\n五、净利润\n500\n450\n'
        '其中：归属于母公司股东\n的净利润\n490\n440\n少数股东损益\n10\n10')
    result = extract_bank_statements([(1,text)],2025)
    assert result['template']==BANK_TEMPLATE
    assert all(result[key] is None for key in ('income','balance','cash'))
    assert '当前版式尚未通过完整三表校验' in result['failure_reason']
    company=build_company_identity('002142','测试银行')
    candidate=build_candidate_report_result(company,
        dict(report_year=2025,published_date='2026-04-25',title='测试银行2025年年度报告',
             url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',
        [dict(page_number=1,text=text)])
    snapshot=build_on_demand_financial_snapshot(company,candidate)
    assert snapshot['status']=='needs_review'
    assert snapshot['report']['statement_template']==BANK_TEMPLATE
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])
    assert all(v is None for v in snapshot['ratios'].values())
    review=build_financial_snapshot_review(snapshot)
    assert review['report']['statement_template']==BANK_TEMPLATE


def test_bank_terms_in_prose_do_not_trigger_bank_template():
    text=('合并利润表\n2025 年度\n单位：人民币百万元\n营业收入\n100\n90\n'
          '本公司比较银行的利息净收入和手续费及佣金净收入，但不是银行报表。')
    assert extract_bank_statements([(1,text)],2025) is None
