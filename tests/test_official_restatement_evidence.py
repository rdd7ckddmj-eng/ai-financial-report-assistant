"""Exact, local explanation matching must never turn a difference into approval."""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

import src.official_restatement_evidence as registry


HUICHUAN_SHA = '622e4c655a31d41eca5e18fde18be214aeddef7d8a29a51d429efa1f322f8f01'
SHENHUA_SHA = '7068df1231922b8a2fcfd0336d9ae6550dabf7c7edc152d680089df8cc126bd2'
CASES = [
    ('300124.SZ', 2025, HUICHUAN_SHA, 'total_assets', '71314393635.15', '71314783635.15'),
    ('601088.SH', 2025, SHENHUA_SHA, 'total_assets', '627761000000', '903830000000'),
    ('601088.SH', 2025, SHENHUA_SHA, 'total_liabilities', '146310000000', '300203000000'),
]


def _data():
    return json.loads(registry.REGISTRY_PATH.read_text())


@pytest.mark.parametrize('args', CASES)
@pytest.mark.parametrize('kind', [str, Decimal, float])
def test_three_registered_amounts_match_exactly_with_complete_provenance(args, kind):
    values = (*args[:4], kind(args[4]), kind(args[5]))
    found = registry.match_official_restatement_evidence(*values)
    assert found is not None
    assert found['status'] == 'registered_official_restatement_explanation'
    assert found['human_verification'] == 'not_performed'
    assert found['effect'] == 'explanation_only'
    assert Decimal(found['annual_yuan']) == Decimal(args[4])
    assert Decimal(found['restated_yuan']) == Decimal(args[5])
    assert Decimal(found['difference_yuan']) == Decimal(args[5]) - Decimal(args[4])
    assert found['annual_report']['sha256'] == args[2]
    assert found['annual_report']['amount_pages']
    assert found['subsequent_report']['amount_pages']
    assert found['subsequent_report']['explanation_pages']
    assert found['explanation'] and found['limitations']
    assert 'comparison_status' not in found and 'verified' not in found


def test_original_units_and_later_report_pages_are_not_lost():
    h = registry.match_official_restatement_evidence(*CASES[0])
    assert h['subsequent_report']['sha256'] == 'b46cd264afdab99455b303240a702e729a4d3e6b57b97dca753c09695cf393ba'
    assert h['subsequent_report']['amount_unit'] == '人民币元'
    assert h['subsequent_report']['amount_pages'] == [2, 7]
    assert h['subsequent_report']['explanation_pages'] == [2, 11]
    s = registry.match_official_restatement_evidence(*CASES[1])
    assert s['subsequent_report']['sha256'] == 'ff4a670c7aa9e0309dc610a0e225d490970731dcc14eda234d73bb8c9b9b54f4'
    assert s['subsequent_report']['amount_unit'] == '人民币百万元'
    assert s['subsequent_report']['after_value'] == '903830'
    assert s['subsequent_report']['amount_pages'] == [6, 76]
    assert s['subsequent_report']['explanation_pages'] == [7]


@pytest.mark.parametrize('index,value', [
    (0, '300124'), (0, '300124.SH'), (0, '300124.sz'), (0, ' 300124.SZ'),
    (0, '601088.SH'), (1, 2024), (1, '2025'), (1, True),
    (2, '0' * 64), (2, HUICHUAN_SHA.upper()), (2, ''),
    (3, 'total_liabilities'), (3, 'revenue'),
    (4, '71314393635.150001'), (5, '71314783635.150001'),
    (4, '71314783635.15'), (5, '71314393635.15'),
])
def test_every_identity_and_amount_dimension_is_required(index, value):
    args = list(CASES[0]); args[index] = value
    assert registry.match_official_restatement_evidence(*args) is None


@pytest.mark.parametrize('value', [None, True, float('nan'), float('inf'),
    Decimal('NaN'), Decimal('-Infinity'), 'NaN', '1e10', '71,314,393,635.15',
    '71314393635.15元', ' 71314393635.15', '', [], {}, Decimal('1e100')])
def test_invalid_amounts_do_not_create_explanations(value):
    assert registry.match_official_restatement_evidence(*CASES[0][:4], value, CASES[0][5]) is None
    assert registry.match_official_restatement_evidence(*CASES[0][:5], value) is None


def test_match_is_local_and_returned_records_cannot_mutate_later_results(monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network must not be used.'))
    first = registry.match_official_restatement_evidence(*CASES[0])
    first['annual_report']['amount_pages'].append(999)
    first['status'] = 'verified'
    first['limitations'].clear()
    second = registry.match_official_restatement_evidence(*CASES[0])
    assert second['annual_report']['amount_pages'] == [9, 117, 118]
    assert second['status'] == registry.EVIDENCE_STATUS
    assert second['limitations']


@pytest.mark.parametrize('url', [
    'https://static.cninfo.com.cn.evil.test/report.pdf',
    'https://evil.test/static.cninfo.com.cn/report.pdf',
    'http://static.cninfo.com.cn/report.pdf',
    'https://user@static.cninfo.com.cn/report.pdf',
    'https://static.cninfo.com.cn:8443/report.pdf',
    'https://static.cninfo.com.cn/report.pdf?redirect=evil',
    'https://static.cninfo.com.cn/report.pdf#fragment',
    'javascript:alert(1)', 'file:///tmp/report.pdf',
])
def test_registry_rejects_nonofficial_or_ambiguous_pdf_links(url):
    data = _data(); data['entries'][0]['subsequent_report']['source_url'] = url
    with pytest.raises(ValueError):
        registry.validate_official_restatement_registry(data)


@pytest.mark.parametrize('path,value', [
    (('company_code',), '300124.SH'), (('period_end',), '2024-12-31'),
    (('status',), 'amount_close'), (('human_verification',), 'verified'),
    (('effect',), 'overwrite'), (('limitations',), []), (('explanation',), ''),
    (('annual_report', 'sha256'), 'a' * 63),
    (('subsequent_report', 'title'), ''),
    (('subsequent_report', 'published_date'), '2026-04-27'),
    (('subsequent_report', 'amount_pages'), [12]),
    (('subsequent_report', 'explanation_pages'), [2, 2]),
    (('subsequent_report', 'page_count'), True),
    (('subsequent_report', 'amount_unit'), '美元'),
    (('subsequent_report', 'amount_unit'), []),
    (('subsequent_report', 'before_value'), '71314393635.14'),
    (('subsequent_report', 'after_value'), '71314783635.14'),
    (('annual_report', 'amount_value'), '71314393635.14'),
    (('annual_yuan',), '71314393635.14'), (('difference_yuan',), '390001'),
])
def test_incomplete_or_inconsistent_registry_is_rejected(path, value):
    data = _data(); target = data['entries'][0]
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        registry.validate_official_restatement_registry(data)


def test_duplicate_or_conflicting_metric_registration_is_rejected():
    data = _data(); duplicate = deepcopy(data['entries'][0]); data['entries'].append(duplicate)
    with pytest.raises(ValueError): registry.validate_official_restatement_registry(data)
    duplicate['evidence_id'] = 'same-original-different-record'
    with pytest.raises(ValueError): registry.validate_official_restatement_registry(data)


@pytest.mark.parametrize('content', [None, '{bad json', '{}', '{"schema":"official-restatement-evidence.v1","entries":[{}]}'])
def test_missing_or_damaged_local_register_returns_no_explanation(tmp_path, monkeypatch, content):
    path = tmp_path / 'registry.json'
    if content is not None: path.write_text(content)
    monkeypatch.setattr(registry, 'REGISTRY_PATH', path)
    assert registry.match_official_restatement_evidence(*CASES[0]) is None


def test_invalid_unrelated_entry_cannot_leave_a_partially_trusted_register(tmp_path, monkeypatch):
    data = _data(); data['entries'][-1]['subsequent_report']['sha256'] = 'bad'
    path = tmp_path / 'registry.json'; path.write_text(json.dumps(data))
    monkeypatch.setattr(registry, 'REGISTRY_PATH', path)
    assert registry.match_official_restatement_evidence(*CASES[0]) is None


def _stored(index=0, schema='public-financial-reconciliation-artifact.v1'):
    evidence = _data()['entries'][index]
    annual = evidence['annual_report']
    comparison = dict(schema=schema, company={'canonical_code': evidence['company_code']},
        report_year=evidence['report_year'], annual_pdf_fingerprint=annual['sha256'],
        annual_source_url=annual['source_url'], annual_published_date=annual['published_date'])
    row = dict(key=evidence['metric_key'], status='amount_difference',
        annual_candidate_yuan=evidence['annual_yuan'], public_yuan=evidence['restated_yuan'],
        difference_yuan=str(-Decimal(evidence['difference_yuan'])),
        official_restatement_evidence=evidence)
    return comparison, row


@pytest.mark.parametrize('index', [0, 1, 2])
@pytest.mark.parametrize('schema', ['public-financial-reconciliation.v1',
                                  'public-financial-reconciliation-artifact.v1'])
def test_stored_evidence_validates_without_reading_register_or_network(index, schema, monkeypatch):
    import socket
    comparison, row = _stored(index, schema)
    original = deepcopy((comparison, row))
    def forbidden(*args, **kwargs):
        pytest.fail('Historical evidence must not read the register or use network.')
    monkeypatch.setattr(registry, '_registry', forbidden)
    monkeypatch.setattr(registry, 'match_official_restatement_evidence', forbidden)
    monkeypatch.setattr(type(registry.REGISTRY_PATH), 'read_text', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    found = registry.validated_stored_restatement_evidence(comparison, row)
    assert found == row['official_restatement_evidence']
    assert (comparison, row) == original
    found['subsequent_report']['amount_pages'].clear()
    assert row['official_restatement_evidence']['subsequent_report']['amount_pages']


@pytest.mark.parametrize('field,value', [
    ('schema', 'public-financial-reconciliation-artifact.v0'),
    ('schema', None), ('company', None), ('company', {'canonical_code': '300124.SH'}),
    ('company', {'canonical_code': '300124'}), ('report_year', 2024),
    ('report_year', '2025'), ('report_year', True),
    ('annual_pdf_fingerprint', '0' * 64),
    ('annual_source_url', 'https://static.cninfo.com.cn/other.pdf'),
    ('annual_published_date', '2026-04-29'),
])
def test_stored_evidence_requires_same_receipt_identity_and_original_report(field, value):
    comparison, row = _stored()
    comparison[field] = value
    assert registry.validated_stored_restatement_evidence(comparison, row) is None
    comparison.pop(field)
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


@pytest.mark.parametrize('field,value', [
    ('key', 'total_liabilities'), ('status', 'amount_close'),
    ('annual_candidate_yuan', '71314393635.150001'),
    ('public_yuan', '71314783635.150001'),
    ('difference_yuan', '390000.00'), ('difference_yuan', '-390000.000001'),
    ('annual_candidate_yuan', None), ('public_yuan', True),
    ('public_yuan', Decimal('1e10000000')),
    ('difference_yuan', float('nan')),
    ('official_restatement_evidence', None), ('official_restatement_evidence', []),
])
def test_stored_evidence_rejects_mismatched_or_incomplete_row(field, value):
    comparison, row = _stored()
    row[field] = value
    assert registry.validated_stored_restatement_evidence(comparison, row) is None
    row.pop(field)
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


def test_stored_evidence_rejects_changed_public_amount_even_with_recalculated_difference():
    comparison, row = _stored()
    row['public_yuan'] = '71314795980.15'
    row['difference_yuan'] = str(Decimal(row['annual_candidate_yuan']) - Decimal(row['public_yuan']))
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


@pytest.mark.parametrize('path,value', [
    (('status',), 'amount_close'), (('human_verification',), 'verified'),
    (('effect',), 'overwrite'), (('limitations',), []),
    (('annual_report', 'amount_pages'), []),
    (('subsequent_report', 'source_url'), 'https://evil.test/report.pdf'),
    (('subsequent_report', 'sha256'), 'broken'),
    (('subsequent_report', 'published_date'), '2026-04-27'),
    (('subsequent_report', 'explanation_pages'), [12]),
    (('subsequent_report', 'after_value'), '71314783635.16'),
    (('subsequent_report', 'amount_unit'), []),
])
def test_stored_evidence_revalidates_complete_source_metadata_and_amounts(path, value):
    comparison, row = _stored()
    target = row['official_restatement_evidence']
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


@pytest.mark.parametrize('comparison,row', [(None, {}), ({}, None), ([], {}), ({}, [])])
def test_stored_evidence_rejects_invalid_container_types(comparison, row):
    assert registry.validated_stored_restatement_evidence(comparison, row) is None


def test_stored_evidence_accepts_json_numeric_amounts_without_rounding():
    comparison, row = _stored()
    for key in ('annual_candidate_yuan', 'public_yuan', 'difference_yuan'):
        row[key] = float(row[key])
    assert registry.validated_stored_restatement_evidence(comparison, row) is not None
