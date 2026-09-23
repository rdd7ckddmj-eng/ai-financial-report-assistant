"""CITIC's exact revenue-vintage difference is explained, never approved."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from src.financial_snapshot_review import build_financial_snapshot_review
from src.official_restatement_evidence import (
    match_official_restatement_evidence, validate_official_restatement_registry,
    validated_stored_restatement_evidence,
)
from src.public_financial_history import build_public_financial_history
from src.public_financial_reconciliation import build_public_financial_reconciliation

FOLDER = Path(__file__).parent/'fixtures'
FIXTURE = json.loads((FOLDER/'citic_securities_restatement_2025.json').read_text())
REPORTS = json.loads((FOLDER/'citic_securities_2024_2025.json').read_text())
ANNUAL_SHA = '27ee61ad5296d8f200861692af538a7db034aadf770ba0ae67f736d4e693d50d'
LATER_SHA = '438f2a53dcf4bf0569b6783b51674aae25076d23d53198b08cf7b539e14003c2'
ARGS = ['600030.SH',2024,ANNUAL_SHA,'revenue','63789215688.23','58119003450.22']


def page(year, number):
    sample = next(s for s in REPORTS if s['year']==year)
    return next(p['text'] for p in sample['pages'] if p['page_number']==number)


def compact(text):
    return re.sub(r'\s+','',text)


def test_registration_binds_two_full_official_reports_and_observed_pages():
    e = match_official_restatement_evidence(*ARGS)
    assert e['annual_report']['page_count'] == 393
    assert e['annual_report']['amount_pages'] == [169]
    assert e['annual_report']['published_date'] == '2025-03-27'
    assert e['subsequent_report']['page_count'] == 389
    assert e['subsequent_report']['published_date'] == '2026-03-27'
    assert e['subsequent_report']['sha256'] == LATER_SHA
    assert e['subsequent_report']['amount_pages'] == [19,182]
    assert e['subsequent_report']['explanation_pages'] == [230]
    assert e['subsequent_report']['amount_unit'] == '人民币元'
    assert e['human_verification'] == 'not_performed' and e['effect'] == 'explanation_only'
    assert e['difference_yuan'] == '-5670212238.01'
    assert validate_official_restatement_registry(dict(schema='official-restatement-evidence.v1',entries=[e])) == [e]


def test_real_summary_has_2024_adjusted_and_unadjusted_columns_in_that_order():
    text = compact(page(2025,19))
    assert '单位：人民币元主要会计数据2025年2024年本期比上年同期增减(%)2023年调整后调整前调整后调整前' in text
    assert '营业收入74,854,368,352.8558,119,003,450.2263,789,215,688.2328.7955,411,575,431.1860,067,992,766.11' in text
    old = compact(page(2024,169));new = compact(page(2025,182))
    assert '2024年度2023年度一、营业收入63,789,215,688.2360,067,992,766.11' in old
    assert '2025年度2024年度(已重述)一、营业收入74,854,368,352.8558,119,003,450.22' in new
    assert '(除另有注明外，金额单位均为人民币元)本集团' in new


def test_original_accounting_note_exactly_bridges_both_revenue_and_cost_adjustments():
    text = compact(page(2025,230))
    assert '31重要会计政策变更' in text
    assert '标准仓单交易相关会计处理实施问答' in text
    assert '原按总额确认收入成本' in text and '差额计入投资收益' in text
    assert '对可比期间财务报表数据进行追溯调整' in text
    assert '其他业务收入6,437,064,339.07(5,760,577,410.27)676,486,928.80' in text
    assert '投资收益32,485,942,803.70222,861,084.8032,708,803,888.50' in text
    assert '(6,023,331,456.68)(132,495,912.54)(6,155,827,369.22)' in text
    assert '其他业务成本5,840,185,927.89(5,537,716,325.47)302,469,602.42' in text
    assert '其他资产减值损失153,472,089.94(132,495,912.54)20,976,177.40' in text
    income_delta = -Decimal('5760577410.27')+Decimal('222861084.80')-Decimal('132495912.54')
    cost_delta = -Decimal('5537716325.47')-Decimal('132495912.54')
    assert income_delta == cost_delta == Decimal(ARGS[5])-Decimal(ARGS[4])


def test_actual_production_snapshot_public_comparison_preserves_difference_and_no_human_confirmation():
    snapshot = deepcopy(FIXTURE['annual_snapshot'])
    history = build_public_financial_history(snapshot['company'],FIXTURE['source_rows'],fetched_at=FIXTURE['public_fetched_at'])
    original = deepcopy((snapshot,history))
    comparison = build_public_financial_reconciliation(history,snapshot)
    assert (snapshot,history) == original
    row = next(r for r in comparison['rows'] if r['key']=='revenue')
    assert comparison['status'] == 'pending_human_review'
    assert row['status'] == 'amount_difference' and row['public_field'] == 'revenue'
    assert row['annual_candidate_yuan'] == 63789215688.23
    assert row['public_yuan'] == 58119003450.22
    assert row['difference_yuan'] == 5670212238.01
    assert row['official_restatement_evidence']['effect'] == 'explanation_only'
    assert validated_stored_restatement_evidence(comparison,row) == row['official_restatement_evidence']
    assert all(r['status']=='amount_close' and 'official_restatement_evidence' not in r for r in comparison['rows'] if r['key']!='revenue')
    assert all(r['decision']=='pending' for r in build_financial_snapshot_review(snapshot)['metrics'])
    assert all(v is None for v in snapshot['ratios'].values())


@pytest.mark.parametrize('index,value', [
    (0,'600030.SZ'),(0,'600999.SH'),(1,2025),(1,'2024'),(1,True),
    (2,LATER_SHA),(2,'0'*64),(3,'net_profit'),(3,'total_operating_revenue'),
    (4,'63789215688.24'),(5,'58119003450.23'),(4,'58119003450.22'),(5,'63789215688.23'),
    (4,'74854368352.85'),(5,'55411575431.18'),(4,'60067992766.11'),
])
def test_wrong_company_year_version_metric_or_even_one_cent_does_not_match(index,value):
    args = list(ARGS);args[index]=value
    assert match_official_restatement_evidence(*args) is None


@pytest.mark.parametrize('field,value', [('before_value','63789215688.24'),('after_value','58119003450.23'),('amount_unit','人民币千元')])
def test_revenue_does_not_weaken_registry_unit_and_exact_amount_validation(field,value):
    e = match_official_restatement_evidence(*ARGS)
    e['subsequent_report'][field]=value
    with pytest.raises(ValueError):
        validate_official_restatement_registry(dict(schema='official-restatement-evidence.v1',entries=[e]))
