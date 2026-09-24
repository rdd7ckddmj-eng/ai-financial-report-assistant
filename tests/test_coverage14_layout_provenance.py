"""Real page windows keep layout evidence through candidate, snapshot and views.

These are source-window integration tests with synthetic PDF bytes, not new
full-PDF audits or human confirmations. The original fixtures remain unchanged.
"""
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.financial_snapshot_review import (
    FinancialSnapshotReviewError,
    build_exportable_review_workpaper,
    build_financial_snapshot_review,
)
from src.on_demand_financial_snapshot import (
    build_financial_snapshot_report_html,
    build_on_demand_financial_snapshot,
)


FIXTURES = Path(__file__).parent / 'fixtures'
TEST_BYTES = b'%PDF-layout-provenance-test-only-not-an-official-file'
CASES = [
    ('balance', '600233', '圆通速递', 'coverage14_balance_cash_native_pages.json',
     'balance_sheet_layout_recoveries', '资产负债表页码读取依据'),
    ('pretax', '600008', '首创环保', 'coverage14_income_boundaries.json',
     'income_layout_recoveries', '税前利润跨页读取依据'),
]


def pipeline(kind):
    _, code, name, filename, field, heading = next(case for case in CASES if case[0] == kind)
    sample = deepcopy(next(s for s in json.loads((FIXTURES / filename).read_text()) if s['code'] == code))
    original = deepcopy(sample)
    company = build_company_identity(code, name)
    published_date = sample.get('published_date', sample['source_url'].split('/finalpage/')[1].split('/')[0])
    report = dict(report_year=sample['year'], published_date=published_date,
                  title=f"{name}{sample['year']}年年度报告", url=sample['source_url'])
    result = build_candidate_report_result(company, report, TEST_BYTES, sample['pages'])
    snapshot = build_on_demand_financial_snapshot(company, result)
    assert sample == original
    return sample, company, result, snapshot, field, heading


def source_texts(kind, recovery):
    field = 'source_spans' if kind == 'balance' else 'source_segments'
    text_key = 'original_text' if kind == 'balance' else 'text'
    return [(item['page_number'], item[text_key]) for item in recovery[field]]


def assert_pending(snapshot):
    review = build_financial_snapshot_review(snapshot, review_id='layout-provenance-test',
                                              created_at='2026-09-24T05:00:00+00:00')
    assert all(metric['decision'] == 'pending' for metric in review['metrics'])
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)
    return review


@pytest.mark.parametrize('kind', ['balance', 'pretax'])
def test_real_source_ranges_survive_candidate_snapshot_json_and_html_without_release(kind):
    sample, _, result, snapshot, field, heading = pipeline(kind)
    assert result[field] and snapshot['report'][field] == result[field]
    assert snapshot['report'][field] is not result[field]
    assert snapshot['source_fingerprint_sha256'] == sha256(TEST_BYTES).hexdigest()
    # These fixtures contain only the selected source window. Missing other
    # statements must not become a complete/approved financial snapshot.
    assert result['status'] == snapshot['status'] == 'needs_review'
    assert all(metric['current_yuan'] is None and metric['previous_yuan'] is None
               for metric in snapshot['metrics'])
    original = deepcopy((result, snapshot))
    recovery = result[field][0]
    native = {p['page_number']: p['text'] for p in sample['pages']}
    if kind == 'balance':
        assert recovery['kind'] == 'consecutive_printed_statement_page_numbers'
        assert recovery['physical_to_printed_offset'] == 3
        assert result['statement_pages']['balance_sheet'] == {'start': 104, 'end': 107}
        assert [n for n, _ in source_texts(kind, recovery)] == [104, 105, 106, 107]
        assert result['values']['current_total_assets'] == 54177859555.90
        assert result['values']['previous_total_liabilities'] == 16085981310.78
    else:
        assert recovery == result['income_reconciliation']['evidence']['profit_before_tax']
        assert recovery['label'] == '利润总额'
        assert recovery['values'] == ['2936298518.05', '4882397416.54']
        assert recovery['pages'] == {'start': 114, 'end': 115}
        assert recovery['amount_pages'] == {'start': 114, 'end': 114}
        assert [n for n, _ in source_texts(kind, recovery)] == [114, 115]
        for segment in recovery['source_segments']:
            assert native[segment['page_number']][segment['start_offset']:segment['end_offset']] == segment['text']
    for number, text in source_texts(kind, recovery):
        assert text in native[number]
    restored = json.loads(json.dumps(snapshot, ensure_ascii=False))
    assert restored['report'][field] == result[field]
    html = build_financial_snapshot_report_html(restored)
    assert heading in html
    for number, text in source_texts(kind, recovery):
        assert f'PDF第{number}页' in html
        assert escape(text) in html
    assert '未经人工复核' in html
    assert_pending(restored)
    assert (result, snapshot) == original
    # A view/edit of the snapshot's copied provenance must not edit the
    # candidate evidence which supplied it.
    copied = snapshot['report'][field][0]
    copied['source_spans' if kind == 'balance' else 'source_segments'][0]['page_number'] = 999
    assert result == original[0]


@pytest.mark.parametrize('kind', ['balance', 'pretax'])
@pytest.mark.parametrize('view_source', ['candidate', 'snapshot'])
def test_candidate_and_snapshot_ui_keep_exact_raw_code_pages_and_official_page_links(kind, view_source):
    from src import app
    _, _, result, snapshot, field, heading = pipeline(kind)
    payload = result if view_source == 'candidate' else snapshot
    before = deepcopy(payload)
    review_before = assert_pending(snapshot)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_pdf_text_adjustments(st.session_state['payload'])")
    at.session_state['payload'] = payload
    at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = review_before
    at.run()
    assert not at.exception
    assert any(heading in element.label for element in at.expander)
    expected = source_texts(kind, result[field][0])
    # Streamlit strips boundary whitespace in code blocks. The candidate,
    # snapshot, JSON and HTML assertions above retain the exact newline bytes.
    assert [element.value for element in at.code] == [text.strip() for _, text in expected]
    captions = [element.value for element in at.caption]
    assert captions == [f'PDF第{number}页原始文字' for number, _ in expected]
    buttons = at.get('link_button')
    assert [element.proto.url for element in buttons] == [result['source_url'] + f'#page={number}' for number, _ in expected]
    assert at.session_state['payload'] == before
    assert at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == review_before
    assert assert_pending(snapshot) == review_before


@pytest.mark.parametrize('kind', ['balance', 'pretax'])
def test_untrusted_source_span_and_note_are_escaped_in_html_and_displayed_as_ui_code(kind):
    _, _, _, snapshot, field, heading = pipeline(kind)
    marker = '<script>alert("source")</script>&<img src=x onerror=bad()>'
    item = snapshot['report'][field][0]
    segments = item['source_spans' if kind == 'balance' else 'source_segments']
    segments[0]['original_text' if kind == 'balance' else 'text'] = marker
    item['note'] = marker
    before = deepcopy(snapshot)
    html = build_financial_snapshot_report_html(snapshot)
    assert heading in html and escape(marker) in html and marker not in html
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_pdf_text_adjustments(st.session_state['payload'])")
    at.session_state['payload'] = snapshot
    at.run()
    assert not at.exception
    assert at.code[0].value == marker
    assert all(not element.proto.allow_html for element in at.markdown)
    assert snapshot == before and at.session_state['payload'] == before
    assert_pending(snapshot)


@pytest.mark.parametrize('kind', ['balance', 'pretax'])
@pytest.mark.parametrize('missing', ['absent', 'empty'])
def test_legacy_or_empty_recovery_field_does_not_invent_a_trace_or_manual_confirmation(kind, missing):
    _, company, result, original_snapshot, field, heading = pipeline(kind)
    if missing == 'absent': result.pop(field)
    else: result[field] = []
    before = deepcopy(result)
    snapshot = build_on_demand_financial_snapshot(company, result)
    assert field not in snapshot['report']
    assert snapshot['metrics'] == original_snapshot['metrics']
    assert snapshot['statement_checks'] == original_snapshot['statement_checks']
    assert snapshot['status'] == original_snapshot['status'] == 'needs_review'
    assert heading not in build_financial_snapshot_report_html(snapshot)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_pdf_text_adjustments(st.session_state['payload'])")
    at.session_state['payload'] = snapshot
    at.run()
    assert not at.exception
    assert not at.expander and not at.code and not at.get('link_button')
    assert result == before
    assert_pending(snapshot)


def sf_pipeline():
    sample = json.loads((FIXTURES / 'sf_express_combined_income_2025.json').read_text())
    company = build_company_identity('002352', '顺丰控股')
    report = dict(report_year=sample['year'], published_date=sample['published_date'],
                  title='顺丰控股2025年年度报告', url=sample['source_url'])
    original = deepcopy(sample)
    result = build_candidate_report_result(company, report, TEST_BYTES, sample['pages'])
    snapshot = build_on_demand_financial_snapshot(company, result)
    assert sample == original
    return sample, company, result, snapshot


def test_sf_printed_pages_signed_expenses_and_company_na_survive_snapshot_and_json():
    sample, _, result, snapshot = sf_pipeline()
    detail = snapshot['income_reconciliation']
    assert detail == result['income_reconciliation'] and detail['status'] == 'passed'
    assert result['statement_checks']['income_statement_reconciled'] is True
    assert result['status'] == snapshot['status'] == 'needs_review'
    assert all(metric['current_yuan'] is None for metric in snapshot['metrics'])
    assert detail['layout_recoveries'][0]['source_spans'] == [
        dict(page_number=159, original_text='158\n', printed_page_number=158),
        dict(page_number=160, original_text='159\n', printed_page_number=159),
    ]
    native = {p['page_number']: p['text'] for p in sample['pages']}
    presentation = detail['signed_expense_presentation']
    assert presentation['kind'] == 'explicit_four_column_signed_expenses'
    assert '未通过试算选择' in presentation['note']
    assert [e['label'] for e in presentation['evidence']] == [
        '减：营业成本', '税金及附加', '管理费用', '财务(费用)/收入']
    for item in presentation['evidence']:
        assert item['pages'] == {'start': 159, 'end': 159}
        assert all(part in native[159] for part in item['excerpt'].split(' ｜ '))
        assert all(raw in native[159] for raw in item['raw_values'])
    assert detail['evidence']['income_tax']['values'] == ['-3233066', '-3388416', '-397', '-11227']
    restored = json.loads(json.dumps(snapshot, ensure_ascii=False))
    assert restored['income_reconciliation'] == detail
    for key in ('attributable_profit', 'minority_profit'):
        row = restored['income_reconciliation']['evidence'][key]
        assert row['values'][2:] == [None, None]
        assert row['raw_values'][2:] == ['不适用', '不适用']
        assert row['not_applicable_columns'] == ['company_current', 'company_previous']
    assert 'profit_attribution_company' not in [check['key'] for check in detail['checks']]
    assert detail['not_applicable_checks'][0]['key'] == 'profit_attribution_company'
    assert '未补零、未计作通过' in detail['note']
    html = build_financial_snapshot_report_html(restored)
    assert '利润表页码读取依据' in html and '费用符号读取依据' in html
    assert '未补零、未计作通过' in html
    for item in presentation['evidence']:
        assert escape(item['excerpt']) in html
    assert '<pre>158\n</pre>' in html and '<pre>159\n</pre>' in html
    assert_pending(snapshot)


@pytest.mark.parametrize('view_source', ['candidate', 'snapshot'])
def test_sf_ui_shows_expense_source_and_footer_links_without_approving_company_attribution(view_source):
    from src import app
    _, _, result, snapshot = sf_pipeline()
    payload = result if view_source == 'candidate' else snapshot
    original = deepcopy(payload)
    review = assert_pending(snapshot)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_income_reconciliation(st.session_state['payload'])")
    at.session_state['payload'] = payload
    at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = review
    at.run()
    assert not at.exception
    assert {'查看利润表页码读取依据', '查看费用符号读取依据'} <= {e.label for e in at.expander}
    expense_rows = payload['income_reconciliation']['signed_expense_presentation']['evidence']
    assert [e.value for e in at.code] == ['158', '159'] + [e['excerpt'] for e in expense_rows]
    assert [e.proto.url for e in at.get('link_button')] == [result['source_url'] + '#page=159', result['source_url'] + '#page=160']
    assert '未补零、未计作通过' in '\n'.join(e.value for e in at.markdown)
    assert at.session_state['payload'] == original
    assert at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] == review


def test_sf_signed_expense_note_and_source_html_are_escaped_without_changing_review():
    _, _, _, snapshot = sf_pipeline()
    detail = snapshot['income_reconciliation']
    marker = '<script>alert("expense")</script>&<img src=x onerror=bad()>'
    detail['signed_expense_presentation']['note'] = marker
    detail['signed_expense_presentation']['evidence'][0]['excerpt'] = marker
    detail['layout_recoveries'][0]['source_spans'][0]['original_text'] = marker
    original = deepcopy(snapshot)
    html = build_financial_snapshot_report_html(snapshot)
    assert html.count(escape(marker)) >= 3 and marker not in html
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_income_reconciliation(st.session_state['payload'])")
    at.session_state['payload'] = snapshot
    at.run()
    assert not at.exception
    assert [e.value for e in at.code].count(marker) == 2
    assert all(not e.proto.allow_html for e in at.markdown)
    assert at.session_state['payload'] == original and snapshot == original
    assert_pending(snapshot)


def test_sf_missing_saved_presentation_paths_are_not_rebuilt_from_known_amounts():
    _, company, result, _ = sf_pipeline()
    detail = result['income_reconciliation']
    detail.pop('layout_recoveries')
    detail.pop('signed_expense_presentation')
    original = deepcopy(result)
    snapshot = build_on_demand_financial_snapshot(company, result)
    html = build_financial_snapshot_report_html(snapshot)
    assert '利润表页码读取依据' not in html and '费用符号读取依据' not in html
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_income_reconciliation(st.session_state['payload'])")
    at.session_state['payload'] = snapshot
    at.run()
    assert not at.exception
    assert not ({'查看利润表页码读取依据', '查看费用符号读取依据'} & {e.label for e in at.expander})
    assert not at.code and not at.get('link_button')
    assert result == original
    assert snapshot['income_reconciliation'] == detail
    assert snapshot['status'] == 'needs_review'
    assert_pending(snapshot)
