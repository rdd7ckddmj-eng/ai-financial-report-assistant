"""Production boundaries for signed statements and geometry-derived text."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot, build_financial_snapshot_report_html
from src.pdf_text_derivation import replay_financial_geometry
from src.financial_snapshot_review import (
    build_financial_snapshot_review, build_exportable_review_workpaper, confirm_snapshot_metric,
    FinancialSnapshotReviewError,
)

FIXTURES = Path(__file__).parent / 'fixtures'
TEST_BYTES = b'%PDF-fixture-only-source'


def longi_source():
    sample = next(s for s in json.loads((FIXTURES/'sector_expansion_8a.json').read_text()) if s['code'] == '601012')
    adjustment = json.loads((FIXTURES/'longi_geometry_adjustment.json').read_text())[0]
    page = next(p for p in sample['pages'] if p['page_number'] == 126)
    text = page['text']
    start, end = adjustment['start_offset'], adjustment['end_offset']
    assert text[start:end] == adjustment['original_span']
    page['financial_geometry'] = dict(schema='pdf-signed-amount-geometry.v1',
        document_sha256=sha256(TEST_BYTES).hexdigest(), original_text_sha256=sha256(text.encode()).hexdigest(),
        parser_text=text[:start] + adjustment['replacement_span'] + text[end:], adjustments=[adjustment])
    return sample, page


def candidate(sample):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(report_year=sample['year'], published_date=sample['published_date'],
        title=f"{sample['name']}{sample['year']}年年度报告", url=sample['source_url'])
    result = build_candidate_report_result(company, report, TEST_BYTES, sample['pages'])
    return result, build_on_demand_financial_snapshot(company, result)


def test_known_geometric_join_preserves_original_text_negative_values_and_export():
    sample, page = longi_source()
    before = deepcopy(sample)
    result, snapshot = candidate(sample)
    assert sample == before
    assert result['status'] == snapshot['status'] == 'ready_for_human_review'
    assert '-\n10,205,897,803.72' in page['text']
    assert result['income_reconciliation']['evidence']['profit_before_tax']['values'] == ['-7561633667.41', '-10205897803.72']
    evidence = result['income_reconciliation']['evidence']['profit_before_tax']
    assert '-\n10,205,897,803.72' in evidence['excerpt']
    assert '-10,205,897,803.72' in evidence['parser_excerpt']
    assert evidence['excerpt_kind'] == 'original_pdf_text'
    assert len(snapshot['report']['text_adjustments']) == 1
    for metric in snapshot['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
    assert snapshot['ratios']['operating_cash_conversion'] is None  # loss denominator
    html = build_financial_snapshot_report_html(snapshot)
    assert '负号换行处理依据' in html and '-\n10,205,897,803.72' in html and '-10,205,897,803.72' in html
    assert json.loads(json.dumps(snapshot))['report']['text_adjustments'] == result['pdf_text_adjustments']
    review = build_financial_snapshot_review(snapshot)
    assert all(m['decision'] == 'pending' for m in review['metrics'])
    assert review['report']['text_adjustments'] == snapshot['report']['text_adjustments']
    with pytest.raises(FinancialSnapshotReviewError):
        build_exportable_review_workpaper(review)


@pytest.mark.parametrize('damage', ['pdf_hash', 'text_hash', 'parser_text', 'span', 'replacement', 'page', 'year', 'offset', 'bbox', 'too_many',
    'outside_cell', 'wrong_column', 'false_neighbors', 'wrong_label', 'bad_bounds', 'bounds_nan', 'row_outside', 'sign_below', 'bounds_order'])
def test_bad_derivation_never_supplies_a_missing_minus_or_releases_amounts(damage):
    sample, page = longi_source()
    derived = page['financial_geometry']; item = derived['adjustments'][0]
    if damage == 'pdf_hash': derived['document_sha256'] = '0' * 64
    if damage == 'text_hash': derived['original_text_sha256'] = '0' * 64
    if damage == 'parser_text': derived['parser_text'] += '1.00'
    if damage == 'span': item['original_span'] = '10,205,897,803.72'
    if damage == 'replacement': item['replacement_span'] = '-10,205,897,803.73'
    if damage == 'page': item['page_number'] = 125
    if damage == 'year': item['column_year'] = 2023
    if damage == 'offset': item['start_offset'] -= 1
    if damage == 'bbox': item['sign_bbox'][0] = float('nan')
    if damage == 'too_many': derived['adjustments'] *= 3
    if damage == 'outside_cell': item['sign_bbox'] = [1, 1, 2, 2]
    if damage == 'wrong_column': item['column_year'] = 2025
    if damage == 'false_neighbors': item['supporting_row_labels'] = {'previous': '资产总计', 'next': '负债合计'}
    if damage == 'wrong_label': item['label'] = '利润总额'
    if damage == 'bad_bounds': item['year_column_bounds'] = [[1, 2]]
    if damage == 'bounds_nan': item['year_column_bounds'][0][0] = float('nan')
    if damage == 'row_outside': item['row_bbox'] = [1, 1, 2, 2]
    if damage == 'sign_below': item['sign_bbox'] = [540.24, 212, 543.72, 225.7]
    if damage == 'bounds_order': item['year_column_bounds'].reverse()
    with pytest.raises(ValueError):
        replay_financial_geometry(page, pdf_fingerprint=sha256(TEST_BYTES).hexdigest(), report_year=2025)
    result, snapshot = candidate(sample)
    assert snapshot['status'] == 'needs_review'
    assert not result['statement_checks']['income_statement_reconciled']
    assert all(m['current_yuan'] is None for m in snapshot['metrics'])
    assert result['pdf_text_adjustments'] == []


def test_plain_text_cannot_supply_geometry_even_when_amounts_are_known():
    sample, page = longi_source()
    del page['financial_geometry']
    result, snapshot = candidate(sample)
    assert snapshot['status'] == 'needs_review' and not result['pdf_text_adjustments']


def test_geometry_audit_ui_and_html_keep_the_sign_join_visible_and_escape_notes():
    _, snapshot = candidate(longi_source()[0])
    snapshot['report']['text_adjustments'][0]['reason'] = '<script>bad()</script>'
    html = build_financial_snapshot_report_html(snapshot)
    assert '&lt;script&gt;' in html and '<script>bad()' not in html
    at = AppTest.from_string("import streamlit as st\nfrom src import app\napp._show_income_reconciliation(st.session_state['snapshot'])")
    at.session_state['snapshot'] = snapshot
    at.run()
    assert not at.exception
    assert any('负号换行处理依据' in e.label for e in at.expander)
    assert [block.value for block in at.code] == ['-\n10,205,897,803.72', '-10,205,897,803.72']


@pytest.mark.parametrize('sample', json.loads((FIXTURES/'petrochina_signed_fourcols.json').read_text()), ids=lambda s: str(s['year']))
def test_full_signed_profile_enters_existing_snapshot_with_all_audit_sections(sample):
    result, snapshot = candidate(sample)
    assert snapshot['status'] == 'ready_for_human_review'
    assert snapshot['report']['statement_template'] == 'petrochina_signed_fourcols_million_v1'
    assert {k: len(v) for k,v in snapshot['statement_reconciliation'].items()} == {'income': 10, 'balance': 20, 'cash': 22}
    profit = next(m for m in snapshot['metrics'] if m['key'] == 'net_profit')
    assert profit['current_yuan'] == sample['expected']['income']['current_net_profit'] * 1000000
    assert profit['previous_yuan'] == sample['expected']['income']['previous_net_profit'] * 1000000
    assert '资产负债与现金流金额关系' in build_financial_snapshot_report_html(snapshot)
    assert all(m['decision'] == 'pending' for m in build_financial_snapshot_review(snapshot)['metrics'])


def test_reviewed_case_keeps_compact_derivation_but_requires_actual_review_steps():
    from src.research_case import new_research_case, apply_case_patch
    from src.research_case_financial_review_bridge import build_financial_review_research_case_patch
    _, snapshot = candidate(longi_source()[0])
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    review = build_financial_snapshot_review(snapshot, created_at=now)
    # Simulated explicit decisions only in this unit test, never production QA.
    for metric in review['metrics']:
        review = confirm_snapshot_metric(review, metric['key'], decided_at=now)
    paper = build_exportable_review_workpaper(review, exported_at=now)
    case = new_research_case('geometry-test', snapshot['company'], mode='current',
        as_of_date=None, effective_market_date=now[:10], created_at=now)
    update = build_financial_review_research_case_patch(case, paper, patch_id='geometry-test-patch', emitted_at=now)
    saved = apply_case_patch(case, update)
    payload = saved['artifacts'][0]['payload']
    assert payload['report']['text_adjustments'][0]['original_span'] == '-\n10,205,897,803.72'
    assert 'sign_bbox' not in payload['report']['text_adjustments'][0]
    assert 'sign_bbox' in paper['report']['text_adjustments'][0]
    assert len(json.dumps(payload, ensure_ascii=False).encode()) < 8000
