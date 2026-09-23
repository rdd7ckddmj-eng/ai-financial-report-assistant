"""Original CITIC reports: independent group/parent checks and damaged inputs."""
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from src.citic_securities_statement_extractor import (
    CITIC_SECURITIES_TEMPLATE, extract_citic_securities_statements,
    is_citic_annual_report_identity,
)

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/citic_securities_2024_2025.json').read_text())
COMPANY = dict(code='600030', name='中信证券')
STARTS = {2024: [163,166,169,173,180,183], 2025: [176,179,182,186,193,197]}
MONEY = re.compile(r'(?<![\d,.])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])')


def pages(year=2025):
    return [(p['page_number'], p['text']) for p in next(s for s in SAMPLES if s['year'] == year)['pages']]


def edit(source, number, transform):
    assert any(n == number for n, _ in source)
    result = [(n, transform(t) if n == number else t) for n, t in source]
    assert result != source
    return result


def replace(source, number, old, new):
    def transform(text):
        assert old in text, (number, old)
        return text.replace(old, new, 1)
    return edit(source, number, transform)


def reject(source, year=2025):
    result = extract_citic_securities_statements(source, year)
    assert result is None or (all(result[k] is None for k in ('income','balance','cash'))
        and result['income_reconciliation']['status'] in ('mismatch', 'missing_evidence'))
    return result


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda s: str(s['year']))
def test_original_complete_statement_pages_reconcile_both_owners_and_both_periods(sample):
    result = extract_citic_securities_statements(pages(sample['year']), sample['year'])
    assert result['template'] == CITIC_SECURITIES_TEMPLATE
    assert result['income_reconciliation']['header_years'] == [sample['year'], sample['year']-1]
    assert {k:len(v) for k,v in result['statement_reconciliation'].items()} == {'income':27,'balance':11,'cash':22}
    for kind in ('income','balance','cash'):
        for key, expected in sample['expected'][kind].items():
            assert result[kind][key] == expected
        for source in result[kind]['metric_sources'].values():
            assert source['page_number'] == source['end_page_number']
            assert result[kind]['page_number'] <= source['page_number'] <= result[kind]['end_page_number']
            assert source['excerpt'] and source['labels']
        for check in result['statement_reconciliation'][kind]:
            assert check['passed']
            for period in ('current','previous'):
                item = check[period]
                assert item['passed'] and Decimal(item['difference']) == 0
                assert Decimal(item['left']) == Decimal(item['right'])
    assert result['income']['metric_sources']['net_profit']['accounting_basis'] == '归母净利润（合并报表）'
    assert '中华人民共和国财政部颁布的企业会计准则' in re.sub(r'\s+', '', result['audit_evidence']['excerpt'])


def test_2025_restatement_and_two_different_2024_revenue_vintages_are_retained():
    old = extract_citic_securities_statements(pages(2024), 2024)
    new = extract_citic_securities_statements(pages(), 2025)
    assert old['income']['current_revenue'] == 63789215688.23
    assert new['income']['previous_revenue'] == 58119003450.22
    assert new['restatement_evidence']['page_number'] == 230
    assert '原按总额确认收入' in new['restatement_evidence']['excerpt']
    assert '已重述' in new['comparison_note']
    assert new['income']['metric_sources']['revenue']['comparison_basis'] == new['comparison_note']
    assert new['income']['metric_sources']['revenue']['labels'] == ['营业收入']
    assert old['restatement_evidence'] is None


def test_original_signed_parent_operating_inflow_is_not_forced_positive():
    result = extract_citic_securities_statements(pages(2024), 2024)
    checks = {c['key']:c for c in result['statement_reconciliation']['cash']}
    assert checks['parent_cash_经营_in']['previous']['left'] == '-372276122.03'
    assert checks['parent_cash_经营_in']['previous']['passed']
    assert result['cash']['previous_operating_cash_flow'] == -40836959699.43


@pytest.mark.parametrize('company', [dict(code='600999',name='中信证券'),dict(code='600030',name='中信建投')])
def test_wrong_explicit_identity_is_not_matched(company):
    assert not is_citic_annual_report_identity(company,pages(),2025)


@pytest.mark.parametrize('year', [2023,2026,'2025',True,None])
def test_unsupported_year_is_not_matched(year):
    assert extract_citic_securities_statements(pages(),year) is None


@pytest.mark.parametrize('year,number,old,new', [
    (2024,1,'2024','2025'), (2024,1,'600030','600999'),
    (2024,1,'年度报告','年度报告摘要'), (2025,1,'','年度报告摘要\n'),
    (2025,11,'公司的中文名称','其他公司的名称'),
    (2025,11,'中信证券股份有限公司','中信建投证券股份有限公司'),
    (2025,13,'600030.SH','600999.SH'), (2025,13,'A 股','B 股'),
])
def test_cover_legal_fields_and_a_share_registration_are_bound(year,number,old,new):
    reject(replace(pages(year),number,old,new),year)


@pytest.mark.parametrize('year', [2024,2025])
@pytest.mark.parametrize('table', range(6))
@pytest.mark.parametrize('column', [0,1])
def test_mutated_current_or_comparative_amount_in_every_group_and_parent_table_is_rejected(year,table,column):
    def mutate(text):
        matches = list(MONEY.finditer(text)); match = matches[column]
        changed = Decimal(match.group().replace(',','')) + 123
        return text[:match.start()] + f'{changed:,.2f}' + text[match.end():]
    result = reject(edit(pages(year),STARTS[year][table],mutate),year)
    assert result['income_reconciliation']['status'] == 'mismatch'


@pytest.mark.parametrize('number,old,new', [
    (176,'人民币元','美元'), (179,'本公司','本集团'),
    (182,'2025 年度 \n2024 年度','2024 年度 \n2025 年度'),
    (182,'2024 年度','2024 年度\n2023 年度'),
    (183,'(已重述)',''), (182,'附注五','附注六'),
    (176,'其中：客户资金存款','其中：客户证券存款'),
    (183,'少数股东损益','其他股东损益'),
    (193,'一、经营活动产生的现金流量','二、投资活动产生的现金流量'),
])
def test_currency_owner_year_columns_restatement_note_and_row_labels_must_be_exact(number,old,new):
    reject(replace(pages(),number,old,new))


@pytest.mark.parametrize('token', ['777,,777','777.77.7','777xyz','不适用','N/A','777.00','777.000','−777.00'])
def test_extra_malformed_or_third_amount_is_not_silently_discarded(token):
    reject(replace(pages(),182,'74,854,368,352.85','74,854,368,352.85\n'+token))


@pytest.mark.parametrize('token', ['单位：美元','777,,777','777.00','其他未经验证说明'])
@pytest.mark.parametrize('year,number', [(2024,165),(2025,178)])
def test_signature_area_cannot_hide_units_or_amounts(year,number,token):
    reject(replace(pages(year),number,'后附财务报表附注',token+'\n后附财务报表附注'),year)


@pytest.mark.parametrize('year,number', [(2024,165),(2025,178)])
@pytest.mark.parametrize('change', ['date','signature','missing','footer','prefix'])
def test_approval_and_page_surroundings_are_pinned(year,number,change):
    if change == 'date':
        source = replace(pages(year),number,f'{year+1}年3月26日','1900年1月1日')
    elif change == 'signature':
        source = replace(pages(year),number,'张皓','未知签字人')
    elif change == 'missing':
        source = edit(pages(year),number,lambda t:re.sub(r'此财务报表已于.*?后附财务报表附注','后附财务报表附注',t,flags=re.S))
    elif change == 'footer':
        source = edit(pages(year),number,lambda t:t+'单位：美元\n')
    else:
        source = edit(pages(year),number,lambda t:'单位：美元\n'+t)
    reject(source,year)


@pytest.mark.parametrize('change', ['missing','duplicate','wrong_standard','wrong_year'])
def test_prc_audit_evidence_is_required_and_unique(change):
    source = pages()
    if change == 'missing':
        source = [(n,t) for n,t in source if n != 167]
    elif change == 'duplicate':
        source = sorted(source+[(168,next(t for n,t in source if n==167))])
    elif change == 'wrong_standard':
        source = replace(source,167,'中华人民共和国财政部颁布的','国际会计准则理事会颁布的')
    else:
        source = edit(source,167,lambda t:t.replace('2025','2024'))
    reject(source)


@pytest.mark.parametrize('change', ['missing','duplicate','wrong_cause'])
def test_2025_comparative_restatement_requires_actual_note(change):
    source = pages()
    if change == 'missing':
        source = [(n,t) for n,t in source if n != 230]
    elif change == 'duplicate':
        source = sorted(source+[(231,next(t for n,t in source if n==230))])
    else:
        source = replace(source,230,'原按总额确认收入','原按其他方法确认收入')
    reject(source)


@pytest.mark.parametrize('change', ['missing_group','missing_parent','duplicate','out_of_order','gap','extra_continuation'])
def test_missing_or_ambiguous_physical_pages_never_borrow_other_statement(change):
    source = pages()
    if change.startswith('missing_'):
        source = [(n,t)for n,t in source if n != (182 if change=='missing_group' else 186)]
    elif change == 'duplicate':
        source += [next(p for p in source if p[0]==182)]
    elif change == 'out_of_order':
        source = source[::-1]
    elif change == 'gap':
        source = [(n,t)for n,t in source if n !=183]
    else:
        source = replace(source,186,'母公司利润表','合并利润表 (续)')
    reject(source)


@pytest.mark.parametrize('year', [2024,2025])
@pytest.mark.parametrize('scale', [100000000000000,10**320])
def test_huge_balanced_amounts_are_rejected_before_float_conversion(year,scale):
    source = [(n,MONEY.sub(lambda m:format(Decimal(m.group().replace(',',''))*scale,'.2f'),t)) for n,t in pages(year)]
    result = reject(source,year)
    assert '金额' in result['failure_reason']


def test_symmetric_negative_ordinary_cash_receipts_cannot_pass_by_balancing():
    # Reverse every cash amount: every linear equality is preserved, but the
    # observed ordinary receipt/payment sign convention must reject it.
    source = pages()
    for number in range(193,200):
        def flip(text):
            return re.sub(r'\(?'+MONEY.pattern+r'\)?',lambda m:m.group()[1:-1] if m.group().startswith('(') else '('+m.group()+')',text)
        source = edit(source,number,flip)
    reject(source)
