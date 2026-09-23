"""Original CAS evidence plus parent/IFRS, missing-cell and conflict regressions."""
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.sinopec_statement_extractor import (
    SINOPEC_TEMPLATE, extract_sinopec_statements, is_sinopec_annual_report_identity,
)

SAMPLE = json.loads((Path(__file__).parent / 'fixtures/sinopec_2025_cas_million.json').read_text())
COMPANY = dict(code='600028',name='中国石化')


def pages():
    return [(p['page_number'],p['text']) for p in SAMPLE['pages']]


def replace(source,number,old,new):
    result=list(source)
    i=next(i for i,(n,_) in enumerate(result) if n==number)
    assert old in result[i][1], (number,old)
    result[i]=(number,result[i][1].replace(old,new,1))
    return result


def rejected(source,year=2025):
    result=extract_sinopec_statements(source,year)
    assert result is None or (all(result[k] is None for k in ('income','balance','cash'))
                             and not result['income_reconciliation']['passed'])
    return result


def test_official_cas_original_preserves_two_periods_pages_units_and_raw_evidence():
    source=pages()
    assert is_sinopec_annual_report_identity(COMPANY,source,2025)
    result=extract_sinopec_statements(source,2025)
    assert result['template']==SINOPEC_TEMPLATE
    assert result['income_reconciliation']['status']=='passed'
    assert result['income_reconciliation']['tolerance']=='0'
    assert {k:len(v) for k,v in result['statement_reconciliation'].items()}=={'income':6,'balance':10,'cash':11}
    for kind,metrics,page_range in [('income',['revenue','net_profit'],[99,99]),
                                    ('balance',['total_assets','total_liabilities'],[95,96]),
                                    ('cash',['operating_cash_flow'],[102,102])]:
        figures=result[kind]
        assert figures['unit']=='人民币百万元'
        assert [figures['page_number'],figures['end_page_number']]==page_range
        for metric in metrics:
            assert [figures['current_'+metric],figures['previous_'+metric]]==SAMPLE['expected'][metric]
            provenance=figures['metric_sources'][metric]
            assert provenance['raw_excerpt'] in dict(source)[provenance['page_number']]
            assert provenance['unit']=='人民币百万元'
            assert '中国企业会计准则合并报表' in provenance['statement']
        for row in result['statement_evidence'][kind].values():
            assert row['raw_excerpt']==row['excerpt']
            assert row['raw_excerpt'] in dict(source)[row['pages']['start']]
        for check in result['statement_reconciliation'][kind]:
            assert check['passed']
            for period in ('current','previous'):
                p=check[period]
                assert Decimal(p['left'])==Decimal(p['right'])
                assert Decimal(p['difference'])==0
    assert result['audit_evidence']['page']==89
    assert '中华人民共和国财政部颁布的企业会计准' in result['audit_evidence']['excerpt']
    assert result['income']['current_net_profit'] not in (35633,32476)


@pytest.mark.parametrize('company',[dict(code='600688',name='中国石化'),dict(code='600028',name='上海石化')])
def test_wrong_company_object_cannot_enter(company):
    assert not is_sinopec_annual_report_identity(company,pages(),2025)


@pytest.mark.parametrize('year',[2024,2026,True,'2025'])
def test_unknown_years_do_not_enter(year):
    assert extract_sinopec_statements(pages(),year) is None


@pytest.mark.parametrize('number,old,new',[
    (1,'2025 年度报告','2024 年度报告'),(1,'2025 年度报告','2025 年度报告摘要'),
    (1,'2025 年度报告','2025 年度报告英文'),
    (4,'“中国石化”是指中国石油化工股份有限公司','“中国石化”是指中国石化上海石油化工股份有限公司'),
    (236,'中国石油化工股份有限公司','中国石化上海石油化工股份有限公司'),
    (237,'股票代号：600028','股票代号：600688'),
    (237,'A 股： \n上海证券交易所','H 股： \n上海证券交易所'),
    (237,'股票简称：中国石化','股票简称：中国石油'),
])
def test_cover_legal_name_share_class_and_listing_identity_are_bound(number,old,new):
    source=replace(pages(),number,old,new)
    assert not is_sinopec_annual_report_identity(COMPANY,source,2025)
    assert extract_sinopec_statements(source,2025) is None


@pytest.mark.parametrize('change',['missing','duplicate','wrong_issuer','wrong_year','ifrs','wrong_auditor'])
def test_cas_audit_is_required_and_unique(change):
    source=pages()
    if change=='missing':source=[(n,t) for n,t in source if n!=89]
    if change=='duplicate':source=sorted(source+[(90,dict(source)[89])])
    if change=='wrong_issuer':source=replace(source,89,'中国石油化工股份有限公司全体股东','上海石化全体股东')
    if change=='wrong_year':source=replace(source,89,'2025 年度的合并及母公司利润表','2024 年度的合并及母公司利润表')
    if change=='ifrs':source=replace(source,89,'中华人民共和国财政部颁布的企业会计准\n则','国际财务报告会计准则')
    if change=='wrong_auditor':source=replace(source,89,'毕马威华振审字第2603847 号','毕马威审字第2603847 号')
    assert rejected(source)['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('number,old,new',[
    (95,'2024 年','2023 年'),(96,'2025 年','2024 年'),(99,'2024 年','2025 年'),(102,'2025 年','2024 年'),
    (95,'百万元','万元'),(96,'人民币','港币'),(99,'人民币','美元'),(102,'百万元','千元'),
    (95,'中国石油化工股份有限公司','中国石化上海石油化工股份有限公司'),
    (99,'合并利润表','利润表'),(102,'合并现金流量表','现金流量表'),
    (99,'98 \n','97 \n'),(95,'于2025年12月31日','于2024年12月31日'),
])
def test_each_header_is_bound_to_company_scope_currency_date_and_physical_page(number,old,new):
    assert rejected(replace(pages(),number,old,new))['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('number',[95,96,99,102])
def test_missing_cas_table_does_not_borrow_from_parent_or_ifrs(number):
    source=[(n,t) for n,t in pages() if n!=number]
    assert rejected(source)['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('number,other',[(95,97),(96,98),(99,101),(99,175),(102,103),(102,180)])
def test_parent_or_ifrs_table_cannot_be_substituted_at_cas_page(number,other):
    source=pages()
    source=[(n,dict(source)[other] if n==number else t) for n,t in source]
    assert rejected(source)['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('change',['duplicate_page','reversed','shift','duplicate_table','duplicate_title','damaged_ifrs_header'])
def test_duplicate_or_unknown_statement_context_fails_closed(change):
    source=pages()
    if change=='duplicate_page':source=sorted(source+[(99,dict(source)[99])])
    if change=='reversed':source=source[::-1]
    if change=='shift':source=[(n+1 if n==99 else n,t) for n,t in source]
    if change=='duplicate_table':source=sorted(source+[(238,dict(source)[99])])
    if change=='duplicate_title':source=replace(source,99,'合并利润表','合并利润表\n合并利润表')
    if change=='damaged_ifrs_header':source=replace(source,175,'(除每股数字外，以百万元列示)','人民币百万元')
    assert rejected(source)['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('number,old,new',[
    (99,'2,783,583','2,783,584'),(99,'3,074,562','3,074,563'),
    (99,'31,809','35,633'),(99,'50,313','45,295'),  # parent profit
    (99,'31,809','32,476'),(99,'50,313','48,939'),  # IFRS profit
    (99,'252,435','252,436'),(99,'11,353','11,354'),(99,'9,375','9,376'),
    (99,'7,934','7,935'),(99,'12,966','12,967'),(99,'(12,953)','(12,954)'),
    (99,'3,441','3,442'),(99,'7,234','7,235'),(99,'0.262','0.263'),
    (95,'152,318','152,319'),(95,'146,799','146,800'),
    (95,'2,155,617','2,155,618'),(95,'2,084,771','2,084,772'),
    (96,'29,455','29,456'),(96,'48,231','48,232'),
    (96,'1,165,845','1,165,846'),(96,'1,108,478','1,108,479'),
    (96,'120,926','120,927'),(96,'(987)','(988)'),
    (102,'162,496','162,497'),(102,'149,360','149,361'),
    (102,'(108,609)','(108,610)'),(102,'(109,030)','(109,031)'),
    (102,'(10,242)','(10,243)'),(102,'(30,464)','(30,465)'),
    (102,'81,053','81,054'),(102,'91,295','91,296'),
    (102,'7,702','7,703'),(102,'15,458','15,459'),
])
def test_conflicting_current_previous_components_and_borrowed_profits_are_rejected(number,old,new):
    result=rejected(replace(pages(),number,old,new))
    assert result['income_reconciliation']['status']=='mismatch'
    assert any(not c['passed'] for cs in result['statement_reconciliation'].values() for c in cs)


@pytest.mark.parametrize('replacement',['','7,934.0','7,,934','N/A','(7,934','7,934)','7,934junk','777777777777777777777777777','7,934\n777'])
def test_missing_extra_or_malformed_amount_does_not_shift_into_note_or_next_row(replacement):
    assert rejected(replace(pages(),99,'7,934',replacement))['income_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('number,old,new',[
    (99,'2,341,383','(2,341,383)'),(99,'7,934','(7,934)'),(99,'(12,953)','12,953'),
    (102,'(2,691,243)','2,691,243'),(102,'3,322,049','(3,322,049)'),
])
def test_explicit_income_and_cash_sign_conventions_cannot_be_switched(number,old,new):
    assert '正负呈列' in rejected(replace(pages(),number,old,new))['failure_reason']


def test_unknown_duplicate_row_and_extra_footer_cell_are_not_skipped():
    for old,new in [('营业利润','未知费用\n1\n1\n营业利润'),
                    ('减： 所得税费用','利润总额\n43,184\n70,513\n减： 所得税费用'),
                    ('此财务报表已于','777\n此财务报表已于')]:
        assert rejected(replace(pages(),99,old,new))['income_reconciliation']['status']=='missing_evidence'


def test_missing_cas_profit_is_not_filled_from_matching_parent_ifrs_or_summary():
    source=replace(pages(),99,'母公司股东的净利润 \n \n31,809 \n50,313','母公司股东的净利润 \n \n')
    assert rejected(source)['income_reconciliation']['status']=='missing_evidence'


def test_cash_minority_subrow_cannot_exceed_total():
    source=replace(pages(),102,'其中：子公司吸收少数股东投资收到的现金 \n \n7,702',
                                  '其中：子公司吸收少数股东投资收到的现金 \n \n7,703')
    assert '子项目超过' in rejected(source)['failure_reason']


def test_parent_and_ifrs_values_are_never_used_to_repair_or_override_cas():
    source=replace(pages(),101,'35,633','999,999')
    source=replace(source,175,'32,476','888,888')
    source=replace(source,180,'162,496','777,777')
    result=extract_sinopec_statements(source,2025)
    assert result['income_reconciliation']['passed']
    assert result['income']['current_net_profit']==31809
    assert result['cash']['current_operating_cash_flow']==162496
