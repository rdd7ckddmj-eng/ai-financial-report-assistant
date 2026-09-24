"""Exact source rows, explicit third attribution term and parent-only NA cells."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from src.general_income_reconciliation import check_general_income_reconciliation


SAMPLES = json.loads((Path(__file__).parent / 'fixtures/coverage13_income_attribution_columns.json').read_text())


def sample(code):
    return deepcopy(next(s for s in SAMPLES if s['code'] == code))


def check(s):
    return check_general_income_reconciliation(s['pages'], s['income'], report_year=s['year'])


def replace(s, old, new, count=1):
    changed=0
    for i, (page, text) in enumerate(s['pages']):
        if old in text and changed < count:
            limit=count-changed
            changed += min(text.count(old), limit)
            s['pages'][i]=[page,text.replace(old,new,limit)]
    assert changed == count
    return s


def minority_cells(s, replacement):
    n,text=s['pages'][0]
    text,count=re.subn(r'129,315,430\s+146,792,828\s+/\s+/',replacement,text,count=1)
    assert count==1
    s['pages'][0]=[n,text]
    return s


@pytest.mark.parametrize('source', SAMPLES, ids=lambda s:s['code'])
def test_official_source_windows_pass_without_changing_selected_profit(source):
    original=deepcopy(source)
    result=check(source)
    assert result['passed'] and result['status']=='passed'
    assert source==original
    assert len(source['pdf_sha256'])==64 and source['source_url'].startswith('https://static.cninfo.com.cn/')
    selected=next(c for c in result['checks'] if c['key']=='selected_attributable_profit')
    assert selected['current']['left']==source['income']['current_net_profit']
    assert selected['previous']['left']==source['income']['previous_net_profit']
    for item in result['checks']:
        assert item['passed']
        for period in ('current','previous'):
            assert Decimal(item[period]['left'])-Decimal(item[period]['right'])==Decimal(item[period]['difference'])


def test_yankuang_independent_third_term_reconciles_both_periods_with_source_pages():
    r=check(sample('600188'))
    equity=r['evidence']['other_equity_holder_profit']
    assert equity['values']==['627530','631864']
    assert equity['pages']=={'start':155,'end':155}
    assert '归属于母公司其他权益工具' in equity['excerpt']
    assert r['evidence']['attributable_profit']['values']==['8380948','14862943']
    attribution=next(c for c in r['checks'] if c['key']=='profit_attribution')
    assert attribution['current']['left']=='14225701'
    assert attribution['previous']['left']=='22065854'
    assert '独立其他权益工具持有者' in attribution['label']
    assert r['operating_reconciliation']['status']=='missing_evidence'


@pytest.mark.parametrize('old,new', [
    ('627,530\n631,864',''),
    ('627,530\n631,864','627,530'),
    ('627,530\n631,864','627,530\n631,864\n17'),
    ('627,530\n631,864','627,530\n631,864\n631,864'),
    ('627,530','627,,530'),
    ('627,530','不适用'),
    ('627,530','/'),
    ('627,530','nan'),
    ('（二）按所有权归属分类',''),
    ('2.归属于母公司其他权益工具','其中：归属于母公司其他权益工具'),
    ('2.归属于母公司其他权益工具','2.其他权益工具'),
    ('归属于母公司股东的净利润','归属于母公司所有者的净利润'),
    ('2.归属于母公司其他权益工具','4.归属于母公司其他权益工具'),
])
def test_optional_term_becomes_required_when_present_and_must_have_independent_scope(old,new):
    r=check(replace(sample('600188'),old,new))
    assert not r['passed'] and r['status']=='missing_evidence'
    assert r['evidence']['other_equity_holder_profit']['status']=='missing_or_ambiguous'


def test_duplicate_other_equity_row_is_not_deduplicated_or_summed():
    row='2.归属于母公司其他权益工具\n持有者的净利润\n627,530\n631,864\n'
    r=check(replace(sample('600188'),row,row+row))
    assert r['status']=='missing_evidence'


@pytest.mark.parametrize('scope', ['其中：', '其中：归母股东利润包含下列项目', '附注：以下为归母股东利润子项', '口径暂未说明'])
@pytest.mark.parametrize('before', ['2.归属于母公司其他权益工具', '3.少数股东损益'])
def test_separate_scope_text_between_numbered_rows_prevents_third_term(scope,before):
    r=check(replace(sample('600188'),before,scope+'\n'+before))
    assert r['status']=='missing_evidence'
    assert r['evidence']['other_equity_holder_profit']['status']=='missing_or_ambiguous'


def test_unknown_other_equity_label_cannot_be_ignored_even_when_remaining_sum_matches():
    s=replace(sample('600188'),'2.归属于母公司其他权益工具','2.其他权益工具')
    replace(s,'5,217,223','5,844,753')
    replace(s,'6,571,047','7,202,911')
    assert check(s)['status']=='missing_evidence'


@pytest.mark.parametrize('old,new', [('627,530','627,532'),('631,864','631,866'),('627,530','(627,530)')])
def test_complete_third_term_contradiction_is_mismatch_with_original_sign(old,new):
    r=check(replace(sample('600188'),old,new))
    assert r['status']=='mismatch' and not r['passed']
    if new.startswith('('):assert r['evidence']['other_equity_holder_profit']['values'][0]=='-627530'


def test_removing_third_row_does_not_infer_the_residual_amount():
    row='2.归属于母公司其他权益工具\n持有者的净利润\n627,530\n631,864\n'
    r=check(replace(sample('600188'),row,''))
    assert r['status']=='mismatch'
    assert 'other_equity_holder_profit' not in r['evidence']
    c=next(c for c in r['checks'] if c['key']=='profit_attribution')
    assert c['current']['difference']=='-627530' and c['previous']['difference']=='-631864'


def test_other_equity_row_in_a_parent_table_cannot_complete_consolidated_attribution():
    s=sample('600188')
    row='2.归属于母公司其他权益工具\n持有者的净利润\n627,530\n631,864\n'
    replace(s,row,'')
    s['pages'][-1][1]+='\n母公司利润表\n'+row
    r=check(s)
    assert r['status']=='mismatch' and 'other_equity_holder_profit' not in r['evidence']


def test_tongrentang_tax_note_is_a_reference_not_a_third_amount():
    r=check(sample('600085'))
    assert r['evidence']['income_tax']['notes']==['八、七、76']
    assert r['evidence']['income_tax']['values']==['393508814.56','525045590.00']


@pytest.mark.parametrize('note', ['八、七、76、77','八、七、76.5','八、七、76 77','八、七、七、76','八、七、76foo'])
def test_extra_or_malformed_double_chapter_note_cannot_hide_numbers(note):
    r=check(replace(sample('600085'),'八、七、76',note))
    assert r['status']=='missing_evidence'
    assert r['evidence']['income_tax']['status']=='missing_or_ambiguous'


def test_double_chapter_note_requires_an_explicit_note_column():
    r=check(replace(sample('600085'),'项目\n附注\n','项目\n'))
    assert r['status']=='missing_evidence'


def test_tsingtao_parent_na_cells_are_null_with_raw_slashes_and_no_zero_calculation():
    r=check(sample('600600'))
    row=r['evidence']['minority_profit']
    assert row['values']==['129315430','146792828',None,None]
    assert row['raw_values']==['129,315,430','146,792,828','/','/']
    assert row['not_applicable_columns']==['company_current','company_previous']
    assert json.loads(json.dumps(row))['values'][2:]==[None,None]
    parent=next(c for c in r['checks'] if c['key']=='profit_attribution_company')
    assert '未作零值计算' in parent['label']
    assert parent['current']['left']=='3961210754' and parent['previous']['left']=='2953074635'
    assert r['evidence']['income_tax']['notes']==['(五)53']
    assert r['operating_reconciliation']['status']=='unsupported_layout'


@pytest.mark.parametrize('cells', [
    '129,315,430\n146,792,828\n/',
    '129,315,430\n146,792,828\n/\n/\n17',
    '129,315,430\n146,792,828\n/\n/\n/',
    '/\n146,792,828\n/\n/',
    '129,315,430\n/\n/\n/',
    '129,315,430\n146,792,828\n/\n0',
    '129,315,430\n146,792,828\n0\n/',
    '129,315,430\n146,792,828\nN/A\nN/A',
])
def test_parent_na_is_exactly_two_cells_and_never_a_group_value(cells):
    r=check(minority_cells(sample('600600'),cells))
    assert r['status']=='missing_evidence' and not r['passed']
    assert r['evidence']['minority_profit']['status']=='missing_or_ambiguous'


@pytest.mark.parametrize('scope', ['公司','合并','未注明',''])
def test_one_changed_role_cannot_become_an_assumed_four_column_header(scope):
    s=sample('600600')
    replace(s,'母公司',scope)
    assert check(s)['status']=='missing_evidence'


def test_parent_tax_and_attribution_relations_remain_independently_checked():
    r=check(replace(sample('600600'),'532,144,270','532,144,272'))
    assert r['status']=='mismatch'
    assert next(c for c in r['checks'] if c['key']=='profit_after_tax_company')['current']['difference']=='-2'
    r=check(replace(sample('600600'),'3,961,210,754','3,961,210,756'))
    assert r['status']=='mismatch'


def test_parent_na_does_not_expand_to_two_column_statements():
    r=check(replace(sample('600188'),'5,217,223\n6,571,047','/\n/'))
    assert not r['passed'] and r['status']=='missing_evidence'


@pytest.mark.parametrize('page',[141,142])
@pytest.mark.parametrize('header',[
    '2026 年度\n2024 年度', '2025 年度\n2023 年度',
    '2024 年度\n2025 年度', '2025 年度\n2024 年度\n2023 年度',
    '2025 年度', '2025 年度（未经确认）\n2024 年度',
])
def test_every_explicit_repeated_header_must_match_including_middle_page(page,header):
    s=sample('600089')
    for i,(number,text) in enumerate(s['pages']):
        if number==page:
            assert text.count('2025 年度\n2024 年度')==1
            s['pages'][i]=[number,text.replace('2025 年度\n2024 年度',header)]
    r=check(s)
    assert r['status']=='missing_evidence' and not r['passed']
    assert '续页' in r['note']


def test_repeated_consistent_headers_keep_three_page_evidence_and_all_real_values():
    s=sample('600089');r=check(s)
    assert r['passed'] and r['header_years']==[2025,2024]
    assert r['pages']=={'start':140,'end':142}
    assert r['evidence']['attributable_profit']['values']==['5954294958.25','4143924869.81']
    assert r['evidence']['minority_profit']['values']==['46688454.00','-541034248.49']
