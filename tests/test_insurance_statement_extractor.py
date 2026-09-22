"""Official statement excerpts; mutations are synthetic rejection cases."""
import json
from pathlib import Path
import pytest
from src.insurance_statement_extractor import extract_insurance_statements, INSURANCE_TEMPLATE


def pages():
    return json.loads((Path(__file__).parent/'fixtures/pingan_insurance_2024_statements.json').read_text())['pages']


def test_official_two_year_values_and_exact_pdf_pages():
    result = extract_insurance_statements(pages(), 2024)
    expected = {'income': {'revenue': (1028925, 913789, 158), 'net_profit': (126607, 85665, 159)},
                'balance': {'total_assets': (12957827, 11583417, 155), 'total_liabilities': (11653115, 10354453, 156)},
                'cash': {'operating_cash_flow': (382474, 360403, 162)}}
    for section, metrics in expected.items():
        assert result[section]['unit'] == '人民币百万元'
        for key, (current, previous, page) in metrics.items():
            assert result[section]['current_'+key] == current
            assert result[section]['previous_'+key] == previous
            assert result[section]['metric_sources'][key]['page_number'] == page


@pytest.mark.parametrize('change', ['year', 'unit', 'gap', 'missing', 'parent', 'sign', 'equation', 'duplicate_row', 'duplicate_table', 'extra_column', 'missing_end', 'prior_year_amount', 'unclosed_sign', 'ambiguous_note'])
def test_malformed_or_inconsistent_tables_fail_closed(change):
    p = pages()
    def replace(old, new):
        nonlocal p
        assert any(old in t for _, t in p)
        p = [(n, t.replace(old, new)) for n, t in p]
    if change == 'unclosed_sign': replace('(1,263,852)', '(1,263,852')
    if change == 'ambiguous_note': replace('1,028,925\n913,789', '42\n1,028,925\n913,789')
    if change == 'year': replace('2023年度', '2022年度')
    if change == 'unit': replace('人民币百万元', '人民币万元')
    if change == 'gap': p = [(n+1 if n == 157 else n, t) for n, t in p]
    if change == 'missing': p = [(n, t) for n, t in p if n != 159]
    if change == 'parent': replace('合并利润表', '公司利润表')
    if change == 'sign': replace('(1,263,852)', '1,263,852')
    if change == 'equation': replace('1,028,925', '1,028,935')
    if change == 'duplicate_row': replace('营业收入合计\n1,028,925\n913,789', '营业收入合计\n1,028,925\n913,789\n营业收入合计\n1,028,925\n913,789')
    if change == 'duplicate_table': p += [(n+100, t) for n, t in p if n in (158,159)]
    if change == 'extra_column': replace('1,028,925\n913,789', '1,028,925\n913,789\n888,888')
    if change == 'missing_end': replace('后附财务报表附注为财务报表的组成部分。', '')
    if change == 'prior_year_amount': replace('913,789', '913,799')
    assert extract_insurance_statements(p, 2024) is None


def candidate(name='中国平安', code='601318'):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    company = build_company_identity(code, name)
    return company, build_candidate_report_result(company,
        dict(report_year=2024, title='2024年年度报告', published_date='2025-03-20', url='https://static.cninfo.com.cn/finalpage/2025-03-20/1222847447.PDF'),
        b'%PDF-fixture', [dict(page_number=1,text=name+'保险（集团）股份有限公司')]+[dict(page_number=n,text=t) for n,t in pages()])


def test_integration_keeps_candidate_status_and_special_financial_policy():
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    from src.financial_snapshot_review import build_financial_snapshot_review
    company, result = candidate()
    assert result['statement_template'] == INSURANCE_TEMPLATE
    assert result['status'] == 'ready_for_human_review'
    snapshot = build_on_demand_financial_snapshot(company, result)
    assert all(v is None for v in snapshot['ratios'].values())
    assert snapshot['metrics'][0]['current_yuan'] == 1028925 * 1000000
    assert '非保费收入' in snapshot['metrics'][0]['source']['accounting_basis']
    assert all(m['decision'] == 'pending' for m in build_financial_snapshot_review(snapshot)['metrics'])


def test_other_insurer_is_not_claimed_supported():
    _, result = candidate('测试保险', '601319')
    assert result['statement_template'] == 'insurance_unsupported_v1'
    assert result['status'] == 'needs_review'
    assert all(v is None for v in result['values'].values())


def test_table_of_contents_is_not_a_statement():
    p = [(2, '目录\n合并资产负债表\n合并利润表\n合并现金流量表')] + pages()
    assert extract_insurance_statements(p, 2024) is not None


def pages_2023():
    return json.loads((Path(__file__).parent/'fixtures/pingan_insurance_2023_statements.json').read_text())['pages']


def test_restated_three_column_balance_and_crossyear_agreement():
    old = extract_insurance_statements(pages_2023(), 2023)
    newer = extract_insurance_statements(pages(), 2024)
    expected = {'income': {'revenue': 880355, 'net_profit': 111008},
                'balance': {'total_assets': 11009940, 'total_liabilities': 9823944},
                'cash': {'operating_cash_flow': 476776}}
    for section, metrics in expected.items():
        for key, previous in metrics.items():
            assert old[section]['previous_'+key] == previous
            assert old[section]['current_'+key] == newer[section]['previous_'+key]
            assert '已重述' in old[section]['metric_sources'][key]['comparison_basis']


@pytest.mark.parametrize('change', ['opening_wrong','opening_missing','opening_date','restated_missing','continuation_layout','duplicate_label'])
def test_three_column_boundaries(change):
    p = pages_2023()
    def replace(old, new):
        nonlocal p
        assert any(old in t for _, t in p)
        p = [(n, t.replace(old, new)) for n, t in p]
    if change == 'opening_wrong': replace('9,994,079', '9,994,089')
    if change == 'opening_missing': replace('11,583,417\n11,009,940\n9,994,079', '11,583,417\n11,009,940')
    if change == 'opening_date': replace('2022年1月1日', '2021年1月1日')
    if change == 'restated_missing': replace('（已重述）', '')
    if change == 'continuation_layout': p = [(n, t.replace('2022年1月1日\n', '') if n == 147 else t) for n,t in p]
    if change == 'duplicate_label': replace('筹资活动使用的现金流量净额', '筹资活动产生╱（使用）的现金流量净额\n1\n2\n筹资活动使用的现金流量净额')
    assert extract_insurance_statements(p, 2023) is None


def test_cpic_abbreviation_stays_special_and_does_not_enable_pingan_parser():
    from src.financial_sector_policy import unsupported_issuer_template
    company = dict(code='601601', name='中国太保')
    front = [(1, '中国太平洋保险（集团）股份有限公司')]
    assert unsupported_issuer_template(company, front) == 'insurance_unsupported_v1'
    assert unsupported_issuer_template(dict(code='600519',name='贵州茅台'), front) is None
    assert unsupported_issuer_template(company, [(1, '中国太保产品介绍')]) is None


def test_restated_provenance_reaches_candidate():
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    company = build_company_identity('601318','中国平安')
    result = build_candidate_report_result(company,
        dict(report_year=2023,title='2023年年度报告',published_date='2024-03-22',url='https://static.cninfo.com.cn/test.pdf'),
        b'%PDF-fixture', [dict(page_number=1,text='中国平安保险（集团）股份有限公司')]+[dict(page_number=n,text=t) for n,t in pages_2023()])
    assert result['status'] == 'ready_for_human_review'
    assert all('已重述' in x['comparison_basis'] for x in result['metric_evidence'].values())
