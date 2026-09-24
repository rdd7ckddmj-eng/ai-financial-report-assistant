"""Two official PDFs explain a difference without inventing a later before cell."""
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


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/conch_restatement_dual_source_2026H1.json').read_text())
ANNUAL_SHA = 'a50f3e7f150954b2b45c44c50afdaa618c4184ebe4bb1e9b3a2b6475267c66d8'
LATER_SHA = '7c9b1464eb36998cad9e76c525e0979af53920c182951aa86cc4fc398efdce06'
CASES = [
    ('total_assets', '256000730169', '256494726008', 88, 60, '资产总计'),
    ('total_liabilities', '52284946547', '52490389624', 89, 61, '负债合计'),
]


def _evidence(index=0):
    key, before, after, *_ = CASES[index]
    found = registry.match_official_restatement_evidence('600585.SH', 2025, ANNUAL_SHA, key, before, after)
    assert found is not None
    return found


def _validate(entry):
    return registry.validate_official_restatement_registry(dict(schema=registry.REGISTRY_SCHEMA, entries=[entry]))


def _inputs():
    snapshot = deepcopy(FIXTURE['annual_snapshot'])
    history = build_public_financial_history(snapshot['company'], FIXTURE['source_rows'],
                                            fetched_at=FIXTURE['public_fetched_at'])
    return snapshot, history


def _page(group, number):
    return next(p['text'] for p in FIXTURE[group] if p['page_number'] == number)


@pytest.mark.parametrize('index', [0, 1])
def test_dual_sources_bind_exact_annual_and_later_comparative_cells(index):
    key, before, after, annual_page, later_page, label = CASES[index]
    e = _evidence(index)
    assert e['evidence_basis'] == registry.DUAL_SOURCE_BASIS
    assert e['human_verification'] == 'not_performed' and e['effect'] == 'explanation_only'
    assert e['annual_yuan'] == before and e['restated_yuan'] == after
    assert Decimal(e['difference_yuan']) == Decimal(after) - Decimal(before)
    for report, sha, page, count, publication, column in [
        (e['annual_report'], ANNUAL_SHA, annual_page, 268, '2026-03-25', 'annual_current'),
        (e['subsequent_report'], LATER_SHA, later_page, 238, '2026-08-27', 'restated_comparative'),
    ]:
        assert report['sha256'] == sha and report['page_count'] == count
        assert report['published_date'] == publication and report['amount_pages'] == [page]
        assert report['company_code'] == '600585.SH'
        assert report['amount_period_end'] == e['period_end'] == '2025-12-31'
        assert report['amount_unit'] == '人民币元' and report['amount_label'] == label
        assert report['amount_column'] == column
        assert report['statement_scope'] == 'consolidated'
        assert report['accounting_basis'] == 'china_accounting_standards'
    assert e['annual_report']['amount_value'] == before
    assert 'before_value' not in e['subsequent_report']
    assert e['subsequent_report']['after_value'] == after
    assert e['subsequent_report']['explanation_pages'] == [8]
    annual = re.sub(r'\s+', '', _page('annual_pages', annual_page))
    later = re.sub(r'\s+', '', _page('subsequent_pages', later_page))
    assert '合并资产负债表' in annual and '人民币元' in annual
    assert '2025年12月31日' in annual and '2024年12月31日' in annual
    assert label + format(int(before), ',') in annual
    assert '合并资产负债表' in later and '人民币元' in later
    assert '2026年6月30日2025年12月31日(经重述)' in later
    amounts = re.search(r'^\s*' + re.escape(label) + r'\s+([\d,]+)\s+([\d,]+)',
                        _page('subsequent_pages', later_page), re.MULTILINE).groups()
    # The later current column precedes the restated comparative: not a before column.
    assert amounts[1] == format(int(after), ',')
    assert amounts[0] != format(int(before), ',')
    assert format(int(before), ',') not in later
    assert _validate(e) == [e]


def test_reason_and_rounded_or_ifrs_summaries_are_not_used_as_exact_yuan_evidence():
    summary = re.sub(r'\s+', '', _page('subsequent_pages', 8))
    assert '按中国会计准则编制的会计资料' in summary
    assert '收购安徽海螺绿能售电有限公司和海螺设计院' in summary
    assert '属于同一控制下企业合并事项' in summary
    assert '总资产252,464,266256,494,726256,000,730' in summary
    assert Decimal('256494726') * 1000 != Decimal(CASES[0][2])
    assert Decimal('256000730') * 1000 != Decimal(CASES[0][1])
    ifrs = re.sub(r'\s+', '', _page('subsequent_pages', 10))
    assert '总负债50,554,41352,518,23052,312,787' in ifrs
    assert Decimal('52518230') * 1000 != Decimal(CASES[1][2])


def test_real_receipt_comparison_preserves_amounts_status_and_review_decisions():
    snapshot, history = _inputs()
    untouched = deepcopy((snapshot, history))
    comparison = build_public_financial_reconciliation(history, snapshot)
    assert (snapshot, history) == untouched
    assert comparison['status'] == 'pending_human_review'
    assert comparison['public_updated_date'] == '2026-03-25'
    rows = {r['key']: r for r in comparison['rows']}
    assert len(rows) == 5
    for key, before, after, *_ in CASES:
        row = rows[key]
        assert row['status'] == 'amount_difference'
        assert Decimal(str(row['annual_candidate_yuan'])) == Decimal(before)
        assert Decimal(str(row['public_yuan'])) == Decimal(after)
        assert Decimal(str(row['difference_yuan'])) == Decimal(before) - Decimal(after)
        assert registry.validated_stored_restatement_evidence(comparison, row) == row['official_restatement_evidence']
    assert all(rows[k]['status'] == 'amount_close' and 'official_restatement_evidence' not in rows[k]
               for k in ('revenue', 'net_profit', 'operating_cash_flow'))
    review = build_financial_snapshot_review(snapshot)
    assert all(m['decision'] == 'pending' for m in review['metrics'])
    assert FIXTURE['provenance']['human_verifications'] == 0


@pytest.mark.parametrize('index,value', [
    (0, '600585.SZ'), (0, '600028.SH'), (1, 2024), (1, True), (2, '0' * 64),
    (3, 'revenue'), (4, '256000730170'), (5, '256494726009'),
    (4, '256494726008'), (5, '256000730169'),
    (4, '256000730000'), (5, '256494726000'), (5, '252464265953'),
])
def test_near_values_rounded_summary_current_year_and_identity_mismatches_do_not_match(index, value):
    args = ['600585.SH', 2025, ANNUAL_SHA, 'total_assets', CASES[0][1], CASES[0][2]]
    args[index] = value
    assert registry.match_official_restatement_evidence(*args) is None


@pytest.mark.parametrize('value', [None, '', '256000730169', '0', False])
def test_dual_source_forbids_any_later_before_value_even_if_exact_or_null(value):
    e = _evidence()
    e['subsequent_report']['before_value'] = value
    with pytest.raises(ValueError):
        _validate(e)


@pytest.mark.parametrize('report', ['annual_report', 'subsequent_report'])
@pytest.mark.parametrize('field,value', [
    ('company_code', '600028.SH'), ('amount_period_end', '2026-06-30'),
    ('amount_label', '负债合计'), ('amount_column', 'current'),
    ('statement_scope', 'parent_company'), ('accounting_basis', 'ifrs'),
    ('amount_unit', '人民币千元'), ('amount_pages', []), ('amount_pages', [9999]),
    ('sha256', ''), ('source_url', 'https://example.com/report.pdf'),
])
def test_each_source_requires_explicit_correct_context_and_complete_provenance(report, field, value):
    e = _evidence()
    e[report][field] = value
    with pytest.raises(ValueError):
        _validate(e)
    e[report].pop(field)
    with pytest.raises(ValueError):
        _validate(e)


@pytest.mark.parametrize('field', ['sha256', 'source_url'])
def test_dual_source_cannot_collapse_to_one_pdf(field):
    e = _evidence()
    e['subsequent_report'][field] = e['annual_report'][field]
    with pytest.raises(ValueError):
        _validate(e)


@pytest.mark.parametrize('basis', [None, '', 'unrecognised', [], {}])
def test_unknown_basis_is_not_silently_treated_as_legacy(basis):
    e = _evidence()
    e['evidence_basis'] = basis
    with pytest.raises(ValueError):
        _validate(e)


def test_removing_basis_cannot_bypass_legacy_before_requirement():
    e = _evidence()
    e.pop('evidence_basis')
    with pytest.raises(ValueError):
        _validate(e)


def test_dual_source_amount_conversions_are_independent_and_exact():
    # Synthetic unit changes test the contract, not alternative source claims.
    e = _evidence()
    e['annual_report']['amount_unit'] = '人民币千元'
    e['annual_report']['amount_value'] = '256000730.169'
    assert _validate(e) == [e]
    e['subsequent_report']['amount_unit'] = '人民币百万元'
    e['subsequent_report']['after_value'] = '256494.726008'
    assert _validate(e) == [e]
    e['subsequent_report']['after_value'] = '256494.726'
    with pytest.raises(ValueError):
        _validate(e)


@pytest.mark.parametrize('report_field,value', [
    ('source_url', 'https://static.cninfo.com.cn/other.pdf'),
    ('published_date', '2026-03-26'), ('page_count', 267),
])
def test_real_comparator_requires_exact_annual_source_metadata(report_field, value):
    snapshot, history = _inputs()
    snapshot['report'][report_field] = value
    result = build_public_financial_reconciliation(history, snapshot)
    assert not any('official_restatement_evidence' in r for r in result['rows'])


def test_stored_dual_source_stays_local_and_rejects_corrupted_context(monkeypatch):
    import socket
    snapshot, history = _inputs()
    comparison = build_public_financial_reconciliation(history, snapshot)
    row = next(r for r in comparison['rows'] if r['key'] == 'total_assets')
    original = deepcopy((comparison, row))
    def forbidden(*args, **kwargs):
        pytest.fail('Stored evidence must not read registry or use network.')
    monkeypatch.setattr(registry, '_registry', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    saved = registry.validated_stored_restatement_evidence(comparison, row)
    assert saved == row['official_restatement_evidence']
    assert (comparison, row) == original
    saved['subsequent_report']['amount_pages'].clear()
    assert row['official_restatement_evidence']['subsequent_report']['amount_pages'] == [60]
    row['official_restatement_evidence']['subsequent_report']['amount_period_end'] = '2026-06-30'
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


def test_legacy_records_still_require_both_later_amounts_without_new_context():
    data = json.loads(registry.REGISTRY_PATH.read_text())
    legacy = [e for e in data['entries'] if 'evidence_basis' not in e]
    assert len(legacy) == 6
    for entry in legacy:
        assert _validate(entry) == [entry]
        damaged = deepcopy(entry)
        damaged['subsequent_report'].pop('before_value')
        with pytest.raises(ValueError):
            _validate(damaged)
