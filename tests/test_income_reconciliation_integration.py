"""Arithmetic evidence must survive candidate, snapshot, display and export."""
import copy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import (
    build_on_demand_financial_snapshot, build_financial_snapshot_report_html,
    income_reconciliation_rows,
)

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/general_industry_2025_statements.json').read_text())


def candidate(sample):
    return build_candidate_report_result(build_company_identity(sample['code'], sample['name']),
        dict(report_year=sample['year'], title=f"{sample['name']}2025年年度报告",
             url=sample['source_url'], published_date=sample['published_date']),
        b'%PDF-source-page-fixture', sample['pages'])


def test_real_profit_relationships_survive_snapshot_and_html():
    sample = next(s for s in SAMPLES if s['code'] == '000725')
    result = candidate(sample)
    snapshot = build_on_demand_financial_snapshot(build_company_identity(sample['code'], sample['name']), result)
    assert result['income_reconciliation']['status'] == 'passed'
    assert snapshot['income_reconciliation'] == result['income_reconciliation']
    rows = income_reconciliation_rows(snapshot)
    assert len(rows) >= 2 and all(row['检查结果'] == '通过' for row in rows)
    html = build_financial_snapshot_report_html(snapshot)
    assert '利润表金额关系复核' in html and '比较期差额' in html
    assert snapshot['income_reconciliation']['note'] in html


@pytest.mark.parametrize('status', ['mismatch', 'missing_evidence', 'not_applicable'])
def test_ready_boolean_cannot_override_explicit_arithmetic_failure(status):
    from test_on_demand_financial_snapshot import _candidate_result, _company
    result = _candidate_result()
    result['income_reconciliation'] = dict(status=status, note='利润表证据未通过。', checks=[])
    snapshot = build_on_demand_financial_snapshot(_company(), result)
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
    assert all(v is None for v in snapshot['ratios'].values())


def test_missing_income_evidence_is_not_reported_as_reconciled():
    sample = copy.deepcopy(SAMPLES[0])
    sample['pages'] = [dict(page_number=1, text='2025年年度报告')]
    result = candidate(sample)
    assert result['income_reconciliation']['status'] == 'missing_evidence'
    assert result['statement_checks']['income_statement_reconciled'] is False
    assert result['status'] == 'needs_review'


def test_legacy_snapshot_does_not_invent_arithmetic_evidence():
    from test_on_demand_financial_snapshot import _candidate_result, _company
    snapshot = build_on_demand_financial_snapshot(_company(), _candidate_result())
    assert income_reconciliation_rows(snapshot) == []
    assert '此快照未保存利润表金额关系复核明细' in build_financial_snapshot_report_html(snapshot)
    assert '旧版候选快照；利润表金额关系需重新生成核对。' in build_financial_snapshot_report_html(snapshot)


def test_arithmetic_detail_is_escaped_in_portable_export():
    from test_on_demand_financial_snapshot import _candidate_result, _company
    result = _candidate_result()
    result['income_reconciliation'] = dict(status='passed', note='<script>bad</script>', unit='元', pages={'start': 1, 'end': 1},
        checks=[dict(label='<img src=x>', passed=True, current={'difference': '0'}, previous={'difference': None})])
    snapshot = build_on_demand_financial_snapshot(_company(), result)
    html = build_financial_snapshot_report_html(snapshot)
    assert '<script>' not in html and '<img src=x>' not in html
    assert '&lt;script&gt;' in html and '&lt;img src=x&gt;' in html and '证据不足' in html


def test_review_page_renders_real_checks_and_rounding_explanation():
    from streamlit.testing.v1 import AppTest
    sample = next(s for s in SAMPLES if s['code'] == '000725')
    result = candidate(sample)
    app = AppTest.from_string('import streamlit as st\nfrom src.app import _show_income_reconciliation\n_show_income_reconciliation(st.session_state["receipt"])')
    app.session_state['receipt'] = result
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 2
    assert '本期原值' in app.dataframe[1].value.columns
    assert any(result['income_reconciliation']['rounding_note'] in text.value for text in app.caption)


@pytest.mark.parametrize('omit_detail_key', [False, True])
def test_legacy_ready_flag_does_not_claim_new_profit_check_in_ui_or_export(omit_detail_key):
    from streamlit.testing.v1 import AppTest
    from test_on_demand_financial_snapshot import _candidate_result, _company

    old_candidate = _candidate_result()
    snapshot = build_on_demand_financial_snapshot(_company(), old_candidate)
    if omit_detail_key:
        snapshot.pop('income_reconciliation')
    before = copy.deepcopy(snapshot)
    old_amount = snapshot['metrics'][0]['current_yuan']
    assert snapshot['statement_checks']['income_statement_reconciled'] is True
    assert old_amount == 10_000_000

    # Use the actual page's status and three-statement cards. Stop after the
    # detail section to exclude unrelated public-source/review interactions.
    page = AppTest.from_string('''
from contextlib import ExitStack
from unittest.mock import patch
import streamlit as st
import src.app as app
original_detail = app._show_income_reconciliation
def show_detail_and_stop(result):
    original_detail(result)
    st.stop()
with ExitStack() as stack:
    for name in ['apply_product_theme', '_sync_research_case_store',
                 'show_compact_page_header', '_render_research_case_storage_notice',
                 '_show_company_banner', '_render_manual_snapshot_input']:
        stack.enter_context(patch.object(app, name, lambda *args, **kwargs: None))
    stack.enter_context(patch.object(app, '_selected_company',
        lambda: st.session_state['on_demand_financial_snapshot']['company']))
    stack.enter_context(patch.object(app, '_show_income_reconciliation', show_detail_and_stop))
    app.render_financial_snapshot_page()
''')
    page.session_state['on_demand_financial_snapshot'] = snapshot
    page.run()
    assert not page.exception
    assert any(item.value == '旧版候选快照；利润表金额关系需重新生成核对。' for item in page.info)
    assert next(item.value for item in page.metric if item.label == '利润表') == '旧快照，需重算'
    assert not any('自动检查完成' in item.value for item in page.success)
    assert len(page.dataframe) == 0  # No invented arithmetic-detail rows.
    assert page.session_state['on_demand_financial_snapshot'] == before

    onboarding = AppTest.from_string('''
import streamlit as st
from src.app import _show_onboarding_report_result
_show_onboarding_report_result(st.session_state['receipt'])
''')
    onboarding.session_state['receipt'] = copy.deepcopy(old_candidate)
    onboarding.run()
    assert not onboarding.exception
    assert any(item.value == '合并利润表：旧快照，需重算' for item in onboarding.info)
    assert not any(item.value == '合并利润表：通过' for item in onboarding.success)
    assert onboarding.session_state['receipt'] == old_candidate

    html = build_financial_snapshot_report_html(snapshot)
    assert '旧版候选快照；利润表金额关系需重新生成核对。' in html
    assert '自动检查完成，等待人工复核' not in html
    assert income_reconciliation_rows(snapshot) == []
    assert snapshot == before and snapshot['metrics'][0]['current_yuan'] == old_amount
