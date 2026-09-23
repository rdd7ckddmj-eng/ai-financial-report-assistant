"""Cross-page sign annotation keeps the preceding row's two original cells."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.income_row_layout_recovery import (
    CROSS_PAGE_ATTRIBUTABLE_LAYOUT, recover_cross_page_attributable_profit,
)

SAMPLE=json.loads((Path(__file__).parent/'fixtures/baosteel_attributable_crosspage_2025.json').read_text())


def pages():
    return [(x['page_number'],x['text']) for x in SAMPLE['pages']]


def replace(source,number,old,new):
    result=list(source)
    i=next(i for i,(n,_) in enumerate(source) if n==number)
    assert old in result[i][1]
    result[i]=(number,result[i][1].replace(old,new,1))
    return result


def rejected(source,**kwargs):
    result=recover_cross_page_attributable_profit(source,**kwargs)
    assert result is None or (result['values'] is None and result['error'])
    return result


def test_official_two_page_original_returns_money_and_exact_unmodified_source_slices():
    source=pages(); original=deepcopy(source)
    row=recover_cross_page_attributable_profit(source,report_year=2025)
    assert row['values']==tuple(Decimal(v) for v in SAMPLE['expected'])
    assert row['pages']==dict(start=97,end=98)
    assert row['amount_pages']==dict(start=97,end=97)
    assert row['unit']=='元' and row['currency']=='人民币'
    assert row['header_years']==[2025,2024]
    assert row['layout_recovery']==CROSS_PAGE_ATTRIBUTABLE_LAYOUT
    assert row['error'] is None and row['notes']==[]
    assert source==original
    for segment in row['source_segments']:
        assert dict(source)[segment['page_number']][segment['start_offset']:segment['end_offset']]==segment['text']
    assert row['excerpt']=='\n'.join(s['text'] for s in row['source_segments'])
    assert '7,361,925,588.60\n宝山钢铁股份有限公司2025年年度报告\n98 / 245\n损以“-”号填列）' in row['excerpt']
    assert '归属于母公司股东的净利润（净亏损以“-”号填列）' not in row['excerpt']


def test_helper_never_uses_arithmetic_to_choose_a_cell():
    # Wrong but syntactically complete values are retained here; the separate
    # income reconciliation must reject them. This helper never balances them.
    source=replace(pages(),97,'10,345,621,735.27','1.00')
    row=recover_cross_page_attributable_profit(source,report_year=2025)
    assert row['values']==(Decimal('1.00'),Decimal('7361925588.60'))


@pytest.mark.parametrize('year',[2024,2026,True,'2025'])
def test_report_year_must_match_both_headers(year):
    assert rejected(pages(),report_year=year)['error']=='跨页行报告年度不匹配'


@pytest.mark.parametrize('number,old,new',[
    (97,'宝山钢铁股份有限公司2025年年度报告','另一家公司2025年年度报告'),
    (98,'宝山钢铁股份有限公司2025年年度报告','另一股份有限公司2025年年度报告'),
    (97,'97 / 245','96 / 245'),(98,'98 / 245','99 / 245'),
    (98,'98 / 245','98 / 246'),(98,'98 / 245','98'),
    (98,'98 / 245','98 / 97'),(98,'98 / 245','98 / 1001'),
    (98,'98 / 245',''),(98,'宝山钢铁股份有限公司2025年年度报告',''),
    (98,'98 / 245','98 / 245\n998'),
    (98,'损以“-”号填列）','未知页眉\n损以“-”号填列）'),
])
def test_only_the_true_matching_report_header_and_page_counter_can_be_skipped(number,old,new):
    rejected(replace(pages(),number,old,new))


@pytest.mark.parametrize('change',['gap','missing_next','duplicate_page','reverse','duplicate_candidate'])
def test_physical_page_contiguity_uniqueness_and_original_order(change):
    source=pages()
    if change=='gap':source=[(n+1 if n==98 else n,t) for n,t in source]
    if change=='missing_next':source=source[:1]
    if change=='duplicate_page':source=source+[source[-1]]
    if change=='reverse':source=source[::-1]
    if change=='duplicate_candidate':source=source+[(99,dict(source)[97])]
    rejected(source)


@pytest.mark.parametrize('number,old,new',[
    (97,'合并利润表','母公司利润表'),(97,'合并利润表','合并利润表\n合并利润表'),
    (97,'单位：元','单位：万元'),(97,'币种：人民币','币种：港元'),
    (97,'2025年度','2024年度'),(97,'2024年度','2025年度'),
    (97,'附注五','附注十七'),(97,'2025年1—12月','2025年1—6月'),
    (97,'（二）按所有权归属分类','母公司利润表\n（二）按所有权归属分类'),
    (97,'（二）按所有权归属分类','其他利润分类'),
    (98,'损以“-”号填列）','母公司利润表\n损以“-”号填列）'),
])
def test_group_income_header_scope_currency_and_classification_are_required(number,old,new):
    rejected(replace(pages(),number,old,new))


@pytest.mark.parametrize('prefix',['1.归属于母公司股东的净利润（净损','1.归属于母公司股东的净利润（亏',
                                  '1.归属于母公司股东的净利润（净亏损','1.归属于母公司股东的净利润（净亏\n损'])
def test_unobserved_or_discontinuous_prefix_is_not_guessed(prefix):
    rejected(replace(pages(),97,'1.归属于母公司股东的净利润（净亏',prefix))


@pytest.mark.parametrize('suffix',['','损以“+”号填列）','损以“-”号填列','损以“-”号填写）',
                                  '损以“-”号填列） 123','损\n以“-”号填列）','（净亏损以“-”号填列）'])
def test_exact_next_page_annotation_suffix_is_required(suffix):
    rejected(replace(pages(),98,'损以“-”号填列）',suffix))


@pytest.mark.parametrize('token',['','-','N/A','1','1.0','1.000','1,00.00','1.00x','(1.00)','NaN',
                                 '1.00 2.00','1.00\n2.00'])
@pytest.mark.parametrize('old',['10,345,621,735.27','7,361,925,588.60'])
def test_exact_two_unambiguous_cells_cannot_be_missing_extra_or_damaged(token,old):
    rejected(replace(pages(),97,old,token))


@pytest.mark.parametrize('number,old,new',[
    (97,'7,361,925,588.60','7,361,925,588.60\n777.00'),
    (97,'7,361,925,588.60','7,361,925,588.60\n母公司利润表'),
    (98,'2.少数股东损益（净亏损以“-”号','3.少数股东损益（净亏损以“-”号'),
    (98,'2.少数股东损益（净亏损以“-”号','2.净利润（净亏损以“-”号'),
    (98,'1,066,484,238.78',''),(98,'1,205,724,086.59',''),
    (98,'1,205,724,086.59','1,205,724,086.59\n777.00'),
    (98,'六、其他综合收益的税后净额','母公司利润表'),
])
def test_amounts_must_end_the_first_page_and_exact_minor_row_must_follow(number,old,new):
    rejected(replace(pages(),number,old,new))


def test_repeated_core_label_with_complete_annotation_is_also_rejected():
    source=replace(pages(),97,'（二）按所有权归属分类',
                   '1.归属于母公司股东的净利润（净亏损以“-”号填列）\n1.00\n2.00\n（二）按所有权归属分类')
    assert '重复' in rejected(source)['error']


def test_does_not_change_ordinary_complete_row_or_claim_to_identify_an_issuer():
    source=replace(pages(),97,'1.归属于母公司股东的净利润（净亏',
                   '1.归属于母公司股东的净利润（净亏损以“-”号填列）')
    assert recover_cross_page_attributable_profit(source) is None
    assert recover_cross_page_attributable_profit([(1,'not a financial statement')]) is None
