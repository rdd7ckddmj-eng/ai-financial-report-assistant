"""Official later comparative balances explain, but never approve, differences."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from src.financial_snapshot_review import build_financial_snapshot_review
from src.official_restatement_evidence import (
    match_official_restatement_evidence, validated_stored_restatement_evidence,
)
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/petrochina_restatement_2026H1.json').read_text())
ANNUAL_SHA = '840b15aa4dc38745a6b86a3656063e6a73081ce87407acb0ca93554f4e836e65'
LATER_SHA = '05e2f4240beebde9bb29acd8a0d39e4db3e8c474cc7727bdbe7c244177871aa1'
CASES = [
    ('total_assets', '2828017000000', '2863458000000', [8, 32, 107], [6, 51, 86]),
    ('total_liabilities', '1028469000000', '1032684000000', [32, 108], [52, 86]),
]


def _pages():
    return {p['page_number']: p['text'] for p in FIXTURE['pages']}


def _row(text, label):
    """Read an exact four-amount fixture row; never use it as production parsing."""
    values = re.search(r'^[^\S\n]*' + re.escape(label) + r'\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)', text, re.MULTILINE)
    assert values is not None
    return [Decimal(v.replace(',', '')) for v in values.groups()]


@pytest.mark.parametrize('key,before,after,annual_pages,later_pages', CASES)
def test_registered_records_bind_original_and_complete_later_pdf(key, before, after, annual_pages, later_pages):
    evidence = match_official_restatement_evidence('601857.SH', 2025, ANNUAL_SHA, key, before, after)
    assert evidence is not None
    assert evidence['human_verification'] == 'not_performed'
    assert evidence['effect'] == 'explanation_only'
    assert evidence['annual_report']['amount_pages'] == annual_pages
    assert evidence['annual_report']['page_count'] == 273
    assert evidence['subsequent_report']['sha256'] == LATER_SHA
    assert evidence['subsequent_report']['page_count'] == FIXTURE['subsequent_report']['pages'] == 169
    assert evidence['subsequent_report']['published_date'] == '2026-08-31'
    assert evidence['subsequent_report']['amount_pages'] == later_pages
    assert evidence['subsequent_report']['amount_unit'] == '人民币百万元'
    assert '2026-03-30' in ' '.join(evidence['limitations'])
    assert Decimal(evidence['difference_yuan']) == Decimal(after) - Decimal(before)


def test_raw_halfyear_tables_distinguish_year_end_comparison_from_current_and_parent_columns():
    pages = _pages()
    summary = re.sub(r'\s+', '', pages[6])
    # The first summary is IFRS; select only the explicit Chinese GAAP part.
    chinese = summary.split('2、按中国企业会计准则编制的主要财务数据', 1)[1]
    assert '上年度期末(追溯后)(a)上年度期末(追溯前)(a)' in chinese
    assert '总资产3,024,2722,863,4582,828,017' in chinese
    assert '同一控制下企业合并' in chinese and '追溯调整' in chinese
    assert _row(pages[51], '资产总计') == [3024272, 2863458, 2224716, 2086892]
    assert _row(pages[52], '负债合计') == [1175918, 1032684, 775575, 677610]
    for number in (51, 52):
        compact = re.sub(r'\s+', '', pages[number])
        assert '2026年6月30日2025年12月31日注释2026年6月30日2025年12月31日' in compact
        assert '合并合并公司公司' in compact
        assert '人民币百万元' in compact and '未经审计' in compact
        assert '最早财务报告年度期初即纳入合并范围列报' in compact


@pytest.mark.parametrize('key,label,total', [
    ('total_assets', '资产总计', '35441'),
    ('total_liabilities', '负债总计', '4215'),
])
def test_same_control_acquisition_note_exactly_reconciles_each_difference(key, label, total):
    note = _pages()[86]
    compact = re.sub(r'\s+', '', note)
    assert '(2)同一控制下企业合并' in compact
    assert '合并日及2025年12月31日被合并方资产、负债的账面价值' in compact
    assert compact.count('2026年1月4日') == 3
    amounts = _row(note, label)
    assert sum(amounts[:3]) == amounts[3] == Decimal(total)
    case = next(c for c in CASES if c[0] == key)
    assert (Decimal(case[2]) - Decimal(case[1])) == amounts[3] * 1000000
    assert Decimal('35441') - Decimal('4215') == _row(note, '所有者权益')[-1] == 31226


def test_real_production_comparison_keeps_both_values_difference_status_and_zero_confirmations():
    snapshot = deepcopy(FIXTURE['annual_snapshot'])
    history = build_public_financial_history(snapshot['company'], FIXTURE['source_rows'],
        fetched_at=FIXTURE['public_fetched_at'])
    original = deepcopy((snapshot, history))
    result = build_public_financial_reconciliation(history, snapshot)
    assert (snapshot, history) == original
    rows = {r['key']: r for r in result['rows']}
    assert result['status'] == 'pending_human_review'
    assert result['public_updated_date'] == '2026-03-30'  # not the true ingestion date
    for key in ('revenue', 'net_profit', 'operating_cash_flow'):
        assert rows[key]['status'] == 'amount_close'
        assert 'official_restatement_evidence' not in rows[key]
    for key, before, after, _, _ in CASES:
        row = rows[key]
        assert row['status'] == 'amount_difference'
        assert Decimal(str(row['annual_candidate_yuan'])) == Decimal(before)
        assert Decimal(str(row['public_yuan'])) == Decimal(after)
        assert Decimal(str(row['difference_yuan'])) == Decimal(before) - Decimal(after)
        assert row['official_restatement_evidence']['effect'] == 'explanation_only'
        assert validated_stored_restatement_evidence(result, row) == row['official_restatement_evidence']
    assert all(r['decision'] == 'pending' for r in build_financial_snapshot_review(snapshot)['metrics'])


@pytest.mark.parametrize('index,value', [
    (0, '601857.SZ'), (0, '601088.SH'), (1, 2024),
    (2, '0' * 64), (3, 'net_profit'),
    (4, '2828017000001'), (5, '2863458000001'),
    (4, '2863458000000'), (5, '2828017000000'),
    (4, '2086892000000'), (5, '3024272000000'),
    (4, '2827777000000'), (5, '2863218000000'),
])
def test_cross_year_parent_current_ifrs_and_even_one_yuan_changed_values_do_not_match(index, value):
    args = ['601857.SH', 2025, ANNUAL_SHA, 'total_assets', '2828017000000', '2863458000000']
    args[index] = value
    assert match_official_restatement_evidence(*args) is None
