from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from streamlit.testing.v1 import AppTest

from src.annual_report_coverage import (load_coverage_catalog, validate_coverage_catalog,
    coverage_summary, reports_for_company, sample_company_identity, build_coverage_catalog, MAX_BYTES)
from src.china_stock import build_company_identity


def catalog():
    return load_coverage_catalog()


def test_published_register_contains_exact_versions_and_no_local_paths_or_financial_approval():
    data = catalog()
    summary = coverage_summary(data)
    assert summary['report_versions'] == len(data['reports'])
    assert summary['candidates'] + summary['needs_review'] == summary['report_versions']
    assert summary['companies'] < summary['report_versions']
    assert not any('path' in key for row in data['reports'] for key in row)
    assert all(r['human_verification'] == 'not_performed' for r in data['reports'])
    assert '财务金额仍需' in next(r for r in data['reports'] if r['status']=='ready_for_human_review')['reason']


@pytest.mark.parametrize('damage', ['sha', 'url', 'exchange', 'future', 'date', 'year', 'page', 'status', 'checks', 'bool', 'approval', 'path', 'duplicate'])
def test_damaged_register_fails_instead_of_publishing_success(damage):
    data = catalog();row = data['reports'][0]
    if damage == 'sha': row['source_sha256'] = 'a'*63
    if damage == 'url': row['source_url'] = 'https://evil.invalid/report.pdf'
    if damage == 'exchange': row['canonical_code'] = row['canonical_code'][:6]+'.BJ'
    if damage == 'future': data['tested_at'] = '2099-01-01T00:00:00+00:00'
    if damage == 'date': row['published_date'] = f"{row['report_year']}-12-31"
    if damage == 'year': row['report_year'] = True
    if damage == 'page': row['page_count'] = 0
    if damage == 'status': row['status'] = 'human_verified'
    if damage == 'checks': row['statement_checks']['income_statement_reconciled'] = False
    if damage == 'bool': row['statement_checks']['income_statement_reconciled'] = 1
    if damage == 'approval': row['human_verification'] = 'verified'
    if damage == 'path': row['path'] = '/private/source.pdf'
    if damage == 'duplicate': data['reports'].append(deepcopy(row))
    with pytest.raises(ValueError): validate_coverage_catalog(data)


def test_same_company_year_different_pdf_stays_distinct_and_does_not_inherit_pass():
    data = catalog();row = deepcopy(data['reports'][0]);row['source_sha256'] = 'f'*64
    row['status'] = 'needs_review';row['statement_checks']['income_statement_reconciled'] = False
    row['reason'] = '另一个版本缺少可读取的金额。';data['reports'].append(row)
    checked = validate_coverage_catalog(data)
    selected = reports_for_company(checked, build_company_identity(row['canonical_code'][:6]))
    assert any(r['source_sha256']==row['source_sha256'] and r['status']=='needs_review' for r in selected)
    assert any(r['source_sha256']!=row['source_sha256'] and r['status']=='ready_for_human_review' for r in selected)


def test_unknown_company_is_uncovered_and_historical_name_does_not_override_given_name():
    data = catalog()
    assert reports_for_company(data, build_company_identity('600777')) == []
    unknown = build_company_identity('601012')
    assert unknown['name'] == '待核验公司'
    assert sample_company_identity(unknown, data)['name'] == '隆基绿能'
    assert unknown['name'] == '待核验公司'
    explicit = build_company_identity('601012', '用户选择的名称')
    assert sample_company_identity(explicit, data) == explicit
    with pytest.raises(ValueError): reports_for_company(data, dict(unknown,canonical_code='601012.SZ'))


def test_read_is_bounded_and_invalid_json_is_not_a_silent_empty_catalog(tmp_path):
    path = tmp_path/'catalog.json';path.write_bytes(b' '* (MAX_BYTES+1))
    with pytest.raises(ValueError): load_coverage_catalog(path)
    path.write_text('{broken')
    with pytest.raises(ValueError): load_coverage_catalog(path)


def compiler_input():
    row = deepcopy(catalog()['reports'][0]);path = '/local/not-published.pdf'
    entry = dict(code=row['canonical_code'][:6],name=row['company_name'],year=row['report_year'],path=path,
                 source_url=row['source_url'],published_date=row['published_date'],identity_confirmed=True)
    receipt_row = dict(row, path=path,layer='report',fingerprint=row['source_sha256'],
        metrics=[dict(key=k,current_yuan=10,previous_yuan=9) for k in ('revenue','net_profit','operating_cash_flow','total_assets','total_liabilities')])
    return dict(reports=[entry]),dict(schema='financial-coverage-multibatch-receipt.v1',rows=[receipt_row],
        completed_at=datetime.now(timezone.utc).isoformat(),human_verified_new=0)


def test_compiler_matches_each_source_and_keeps_receipt_fingerprint():
    plan, receipt = compiler_input()
    result = build_coverage_catalog(plan, receipt)
    assert len(result['receipt_sha256']) == 64 and 'path' not in result['reports'][0]
    assert result['reports'][0]['source_sha256'] == receipt['rows'][0]['fingerprint']


@pytest.mark.parametrize('damage', ['drop_failure','source','year','company','missing_amount','nan','error','approved'])
def test_compiler_cannot_hide_failures_or_publish_unproven_candidate(damage):
    plan,receipt = compiler_input();row = receipt['rows'][0]
    if damage == 'drop_failure': receipt['rows'] = []
    if damage == 'source': row['source_url'] += '?different=1'
    if damage == 'year': row['report_year'] -= 1
    if damage == 'company': row['canonical_code'] = '600519.SH'
    if damage == 'missing_amount': row['metrics'][0]['previous_yuan'] = None
    if damage == 'nan': row['metrics'][0]['current_yuan'] = float('nan')
    if damage == 'error': row['status'] = 'unexpected_error'
    if damage == 'approved': receipt['human_verified_new'] = 1
    with pytest.raises(ValueError): build_coverage_catalog(plan,receipt)


def test_ui_filters_and_discloses_uncovered_company_without_fetching_or_financial_decisions(monkeypatch):
    from src import app
    def forbidden(*args, **kwargs):raise AssertionError('coverage view cannot fetch reports')
    monkeypatch.setattr(app,'download_official_pdf',forbidden)
    at = AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\napp._show_annual_report_coverage(build_company_identity('600777'))").run()
    assert not at.exception and not at.dataframe
    assert any('尚无这家公司' in x.value for x in at.info)
    assert any('自动检查通过也不代表完成人工复核' in x.value for x in at.caption)
    at.checkbox(key='annual_report_coverage_all').check().run()
    assert not at.exception and len(at.dataframe[0].value) == len(catalog()['reports'])
    assert not at.button and not at.get('download_button')
    assert 'on_demand_financial_snapshot' not in at.session_state


def test_bad_catalog_ui_does_not_block_the_actual_workflow(monkeypatch):
    import src.annual_report_coverage as module
    def invalid():raise ValueError('bad')
    monkeypatch.setattr(module,'load_coverage_catalog',invalid)
    at = AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\nc=build_company_identity('601012')\nassert app._show_annual_report_coverage(c)==c").run()
    assert not at.exception and not at.dataframe
    assert any('仍须独立检查' in x.value for x in at.caption)


@pytest.mark.parametrize('invalid_status', [[], {}])
def test_invalid_json_status_is_rejected_without_breaking_financial_workflow(monkeypatch, tmp_path, invalid_status):
    import src.annual_report_coverage as module
    data = catalog();data['reports'][0]['status'] = invalid_status
    path = tmp_path/'catalog.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError):load_coverage_catalog(path)
    monkeypatch.setattr(module, 'CATALOG_PATH', path)
    at = AppTest.from_string("import streamlit as st\nfrom src import app\nfrom src.china_stock import build_company_identity\nc=build_company_identity('601012')\nassert app._show_annual_report_coverage(c)==c\nst.info('downstream reached')").run()
    assert not at.exception and not at.dataframe
    assert any(x.value == 'downstream reached' for x in at.info)
