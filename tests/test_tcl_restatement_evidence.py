"""TCL's exact later comparative balances explain, but do not erase, differences."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

import src.official_restatement_evidence as registry
from src.financial_snapshot_review import build_financial_snapshot_review
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/tcl_restatement_dual_source_2026H1.json').read_text())
ANNUAL_SHA = 'f787f5489df911d12f8534f912fe7f71312413d1bec19e60ec9ee184e691c3b6'
LATER_SHA = '561af4b2dce6afc60a3ae97f5c4db583e1eb1f4d47450ba8f549b886b39884be'
CASES = [
    ('total_assets', '117997173481.15', '118020660725.66', '23487244.51', 77, 50, '资产总计'),
    ('total_liabilities', '78738123809.74', '78649163862.64', '-88959947.10', 78, 51, '负债合计'),
]


def inputs():
    snapshot = deepcopy(FIXTURE['annual_snapshot'])
    history = build_public_financial_history(snapshot['company'], FIXTURE['source_rows'],
                                            fetched_at=FIXTURE['public_fetched_at'])
    return snapshot, history


def evidence(index=0):
    key, before, after, *_ = CASES[index]
    found = registry.match_official_restatement_evidence('002129.SZ', 2025, ANNUAL_SHA, key, before, after)
    assert found is not None
    return found


def page(group, number):
    return next(p['text'] for p in FIXTURE[group] if p['page_number'] == number)


def raw_row(text, label):
    row = re.search(r'^\s*' + re.escape(label) + r'\s+([\d,.]+)\s+([\d,.]+)', text, re.MULTILINE)
    assert row is not None
    return tuple(Decimal(s.replace(',', '')) for s in row.groups())


def validate(e):
    return registry.validate_official_restatement_registry(dict(schema=registry.REGISTRY_SCHEMA, entries=[e]))


@pytest.mark.parametrize('index', [0, 1])
def test_exact_dual_source_values_bind_original_and_later_physical_pages(index):
    key, before, after, delta, annual_page, later_page, label = CASES[index]
    e = evidence(index)
    assert e['evidence_basis'] == registry.DUAL_SOURCE_BASIS
    assert e['period_end'] == '2025-12-31'
    assert e['annual_yuan'] == before and e['restated_yuan'] == after
    assert e['difference_yuan'] == delta
    assert Decimal(delta) == Decimal(after) - Decimal(before)
    assert e['status'] == registry.EVIDENCE_STATUS
    assert e['effect'] == 'explanation_only' and e['human_verification'] == 'not_performed'
    assert e['annual_report']['amount_value'] == before
    assert e['subsequent_report']['after_value'] == after
    assert 'before_value' not in e['subsequent_report']
    for report, sha, pages, count, publication, column in [
        (e['annual_report'], ANNUAL_SHA, [annual_page], 240, '2026-03-25', 'annual_current'),
        (e['subsequent_report'], LATER_SHA, [later_page], 213, '2026-08-27', 'restated_comparative'),
    ]:
        assert report['sha256'] == sha and report['page_count'] == count
        assert report['published_date'] == publication and report['amount_pages'] == pages
        assert report['company_code'] == '002129.SZ' and report['amount_period_end'] == '2025-12-31'
        assert report['amount_unit'] == '人民币元' and report['amount_label'] == label
        assert report['amount_column'] == column and report['statement_scope'] == 'consolidated'
        assert report['accounting_basis'] == 'china_accounting_standards'
    assert e['subsequent_report']['explanation_pages'] == [8]
    assert raw_row(page('annual_pages', annual_page), label)[0] == Decimal(before)
    assert raw_row(page('subsequent_pages', later_page), label)[1] == Decimal(after)
    assert validate(e) == [e]


def test_table_dates_columns_units_and_summary_support_do_not_invent_a_later_before_cell():
    annual = re.sub(r'\s+', '', page('annual_pages', 76))
    later = re.sub(r'\s+', '', page('subsequent_pages', 49))
    summary = re.sub(r'\s+', '', page('subsequent_pages', 8))
    assert '合并资产负债表' in annual and '2025年12月31日' in annual
    assert '合并资产负债表' in later and '2026年6月30日' in later
    assert '期末余额期初余额' in annual and '期末余额期初余额' in later
    assert '单位：元' in annual and '单位：元' in later
    assert '未经审计' in later
    assert '同一控制下合并茂兴控股有限公司' in summary
    assert '自2026年2月起纳入合并报表范围' in summary
    assert '总资产（元）112,762,644,351.24117,997,173,481.15118,020,660,725.66' in summary
    assert '负债合计' not in summary
    assert '第8页主要财务指标摘要另并列' in evidence(0)['explanation']
    assert '没有列负债调整前值' in evidence(1)['explanation']
    assert '母公司资产负债表' in page('annual_pages', 78)
    assert page('annual_pages', 78).index('负债合计') < page('annual_pages', 78).index('母公司资产负债表')


def test_production_comparison_preserves_both_sources_all_five_amounts_and_pending_review():
    snapshot, history = inputs()
    original = deepcopy((snapshot, history))
    result = build_public_financial_reconciliation(history, snapshot)
    assert (snapshot, history) == original
    assert result['status'] == 'pending_human_review'
    assert result['public_updated_date'] == '2026-03-25'
    assert result['public_fetched_at'] == '2026-09-24T04:29:38+00:00'
    rows = {r['key']: r for r in result['rows']}
    for key, before, after, delta, *_ in CASES:
        row = rows[key]
        assert row['status'] == 'amount_difference'
        assert Decimal(str(row['annual_candidate_yuan'])) == Decimal(before)
        assert Decimal(str(row['public_yuan'])) == Decimal(after)
        assert Decimal(str(row['difference_yuan'])) == -Decimal(delta)
        assert registry.validated_stored_restatement_evidence(result, row) == row['official_restatement_evidence']
    for key in ('revenue', 'net_profit', 'operating_cash_flow'):
        assert rows[key]['status'] == 'amount_close' and rows[key]['difference_yuan'] == 0
        assert 'official_restatement_evidence' not in rows[key]
    assert all(m['decision'] == 'pending' for m in build_financial_snapshot_review(snapshot)['metrics'])
    assert FIXTURE['provenance']['human_verifications'] == 0


@pytest.mark.parametrize('index,value', [
    (0, '002129.SH'), (0, '600585.SH'), (1, 2026), (1, 2024), (1, True),
    (2, LATER_SHA), (2, '0' * 64), (3, 'revenue'),
    (4, '117997173481.14'), (5, '118020660725.65'),
    (4, '118020660725.66'), (5, '117997173481.15'),
    (4, '125597525162.66'), (5, '112762644351.24'),
    (4, '117997173.48115'), (5, '118020660.72566'),
])
def test_other_identity_period_column_unit_scale_and_one_cent_difference_do_not_match(index, value):
    args = ['002129.SZ', 2025, ANNUAL_SHA, 'total_assets', CASES[0][1], CASES[0][2]]
    args[index] = value
    assert registry.match_official_restatement_evidence(*args) is None


@pytest.mark.parametrize('report', ['annual_report', 'subsequent_report'])
@pytest.mark.parametrize('field,value', [
    ('company_code', '600585.SH'), ('amount_period_end', '2026-06-30'),
    ('amount_label', '负债合计'), ('amount_column', 'current'),
    ('statement_scope', 'parent_company'), ('accounting_basis', 'ifrs'),
    ('amount_unit', '人民币千元'), ('amount_pages', []), ('amount_pages', [9999]),
    ('sha256', ''), ('source_url', 'https://example.com/report.pdf'),
])
def test_each_registered_source_requires_correct_complete_context(report, field, value):
    e = evidence()
    e[report][field] = value
    with pytest.raises(ValueError): validate(e)
    e[report].pop(field)
    with pytest.raises(ValueError): validate(e)


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('value', [None, '', '117997173481.15', '78738123809.74'])
def test_dual_source_never_accepts_a_subsequent_before_field(index, value):
    e = evidence(index)
    e['subsequent_report']['before_value'] = value
    with pytest.raises(ValueError): validate(e)


@pytest.mark.parametrize('field,value', [
    ('source_url', 'https://static.cninfo.com.cn/other.pdf'),
    ('published_date', '2026-03-26'), ('page_count', 239),
])
def test_live_comparator_requires_the_exact_annual_report_metadata(field, value):
    snapshot, history = inputs()
    snapshot['report'][field] = value
    result = build_public_financial_reconciliation(history, snapshot)
    assert not any('official_restatement_evidence' in r for r in result['rows'])
    assert sum(r['status'] == 'amount_difference' for r in result['rows']) == 2


def test_saved_replay_is_local_and_preserves_original_evidence(monkeypatch):
    import socket
    snapshot, history = inputs()
    result = build_public_financial_reconciliation(history, snapshot)
    row = next(r for r in result['rows'] if r['key'] == 'total_liabilities')
    before = deepcopy((result, row))
    def forbidden(*args, **kwargs): pytest.fail('No current registry or network while replaying saved evidence.')
    monkeypatch.setattr(registry, '_registry', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    found = registry.validated_stored_restatement_evidence(result, row)
    assert found == row['official_restatement_evidence']
    assert (result, row) == before
    found['subsequent_report']['amount_pages'].clear()
    assert row['official_restatement_evidence']['subsequent_report']['amount_pages'] == [51]
    row['official_restatement_evidence']['subsequent_report']['amount_period_end'] = '2026-06-30'
    assert registry.validated_stored_restatement_evidence(result, row) is None
