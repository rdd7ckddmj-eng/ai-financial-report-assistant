"""Cross-sector full-report observations, including genuine unsupported cases."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/sector_expansion_8b.json').read_text())


def snapshot(sample):
    company = build_company_identity(sample['code'], sample['name'])
    report = dict(report_year=sample['year'], title=f"{sample['name']}2025年年度报告",
                  url=sample['source_url'], published_date=sample['published_date'])
    result = build_candidate_report_result(company, report, b'%PDF-source-page-fixture', sample['pages'])
    return build_on_demand_financial_snapshot(company, result)


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda sample: sample['code'])
def test_observed_official_report_status_and_all_five_metrics(sample):
    result = snapshot(sample)
    assert result['status'] == sample['status']
    assert [key for key, passed in result['statement_checks'].items() if not passed] == sample['expected_failed_checks']
    assert len(sample['sha256']) == 64 and sample['bytes'] < 32 * 1024 * 1024
    assert sample['human_verification'] == 'not_performed'
    assert result['report']['source_url'] == sample['source_url']
    for metric in result['metrics']:
        expected = sample['expected'][metric['key']]
        assert metric['current_yuan'] == expected['current_yuan']
        assert metric['previous_yuan'] == expected['previous_yuan']
        assert metric['source']['raw_current_value'] == expected['raw_current_value']
        assert metric['source']['raw_previous_value'] == expected['raw_previous_value']
        assert metric['pages'] == expected['pages']


def test_vanke_loss_and_negative_operating_cash_are_preserved():
    sample = next(s for s in SAMPLES if s['code'] == '000002')
    result = snapshot(sample)
    assert result['income_reconciliation']['status'] == 'passed'
    values = {m['key']: (m['current_yuan'], m['previous_yuan']) for m in result['metrics']}
    assert values['net_profit'] == (-88556470495.64, -49478429211.96)
    assert values['operating_cash_flow'] == (-988124860.96, 3799847632.35)
    assert all(c['current']['passed'] and c['previous']['passed'] for c in result['income_reconciliation']['checks'])


@pytest.mark.parametrize('code,token', [('000002', '(3,253,620,605.85)'), ('600900', '446,461,711.16')])
def test_changed_profit_attribution_blocks_every_standardized_metric(code, token):
    sample = deepcopy(next(s for s in SAMPLES if s['code'] == code))
    changed = False
    for page in sample['pages']:
        if token in page['text']:
            page['text'] = page['text'].replace(token, '1.00', 1)
            changed = True
            break
    assert changed
    result = snapshot(sample)
    assert result['status'] == 'needs_review'
    assert result['income_reconciliation']['status'] == 'mismatch'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in result['metrics'])


def test_cmoc_image_only_core_tables_cannot_borrow_summary_or_note_numbers():
    sample = next(s for s in SAMPLES if s['code'] == '603993')
    assert all(not page['text'].strip() for page in sample['pages'] if 91 <= page['page_number'] <= 108)
    # Other sections do contain numbers; they do not supply the missing tables.
    assert any('20,338,750,797.53' in page['text'] for page in sample['pages'])
    result = snapshot(sample)
    assert result['status'] == 'needs_review'
    assert not any(result['statement_checks'].values())
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in result['metrics'])


def test_petrochina_signed_expense_layout_is_not_inferred_from_which_sum_balances():
    sample = next(s for s in SAMPLES if s['code'] == '601857')
    result = snapshot(sample)
    assert result['status'] == 'needs_review'
    assert result['income_reconciliation']['status'] == 'mismatch'
    assert result['income_reconciliation']['evidence']['income_tax']['values'] == ['-54144', '-57755', '-26270', '-27741']
    assert not result['statement_checks']['cash_flow_statement_reconciled']
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in result['metrics'])


def test_vanke_unknown_loss_qualifier_is_not_skipped():
    sample = deepcopy(next(s for s in SAMPLES if s['code'] == '000002'))
    original = '利润总额(亏损总额)'
    page = next(p for p in sample['pages'] if p['page_number'] == 155)
    assert original in page['text']
    page['text'] = page['text'].replace(original, '利润总额(未披露项目调整后)', 1)
    result = snapshot(sample)
    assert result['status'] == 'needs_review'
    assert result['income_reconciliation']['status'] == 'missing_evidence'
