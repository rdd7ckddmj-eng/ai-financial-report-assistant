"""Real source windows: consumer/agriculture coverage and explicit failures."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot

SAMPLES=json.loads((Path(__file__).parent/'fixtures/industry_expansion_11.json').read_text())


def candidate(sample):
    company=build_company_identity(sample['code'],sample['name'])
    report=dict(report_year=sample['year'],title=sample['name']+'2025年年度报告',
                url=sample['source_url'],published_date=sample['published_date'])
    result=build_candidate_report_result(company,report,b'%PDF-source-window-fixture',sample['pages'])
    return result,build_on_demand_financial_snapshot(company,result)


def sample(code):
    return deepcopy(next(s for s in SAMPLES if s['code']==code))


@pytest.mark.parametrize('source',SAMPLES,ids=lambda s:s['code'])
def test_both_periods_from_original_windows_or_explicitly_withheld(source):
    result,snapshot=candidate(source)
    assert snapshot['status']==source['expected_status']
    for metric in snapshot['metrics']:
        expected=source['expected'][metric['key']]
        assert metric['current_yuan']==expected['current_yuan']
        assert metric['previous_yuan']==expected['previous_yuan']
        if snapshot['status']=='ready_for_human_review':
            assert metric['pages']==expected['pages']
            assert metric['source']['original_unit']==expected['original_unit']
            assert metric['source']['accounting_basis']=='合并口径'
            assert metric['source']['excerpt_status']=='captured'
    assert snapshot['status']!='ready_for_human_review' or all(result['statement_checks'].values())


def test_yili_interest_income_is_not_added_to_operating_revenue():
    source=sample('600887')
    text=next(p['text'] for p in source['pages'] if p['page_number']==86)
    assert '115,931,105,774.99' in text and '294,874,524.94' in text
    _,snapshot=candidate(source)
    assert snapshot['metrics'][0]['current_yuan']==115_636_231_250.05


def test_muyuan_consolidated_profit_does_not_borrow_adjacent_parent_row():
    source=sample('002714')
    page=next(p for p in source['pages'] if p['page_number']==116)
    assert '母公司利润表' in page['text']
    page['text']=page['text'].replace('1.归属于母公司股东的净利润','1.本行标签缺失',1)
    result,snapshot=candidate(source)
    assert not result['statement_checks']['income_statement_reconciled']
    assert snapshot['status']=='needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])


@pytest.mark.parametrize('code',['600028','600050'])
def test_unhandled_mixed_columns_or_corrupt_text_never_use_summary_values(code):
    source=sample(code)
    result,snapshot=candidate(source)
    assert not result['statement_checks']['income_statement_reconciled']
    assert snapshot['status']=='needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
