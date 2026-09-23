"""Spelling equivalence must not erase source units or merge different scales."""
import pytest

from src.statement_evidence_rules import consistent_statement_unit
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from test_on_demand_financial_snapshot import _candidate_result,_company


@pytest.mark.parametrize('unit',['元','千元','万元','百万元','亿元'])
def test_only_rmb_prefix_aliases_share_a_conversion_unit(unit):
    assert consistent_statement_unit(['人民币'+unit,unit,unit])=='人民币'+unit
    assert consistent_statement_unit([unit,'人民币'+unit,unit])==unit


@pytest.mark.parametrize('units',[
    ['人民币元','千元','元'],['人民币元','美元','元'],['人民币元','港元','元'],
    ['人民币元','','元'],['人民币元','人民币人民币元','元'],
    ['人民币元','元'],['人民币元','元','元','元'],['人民币元',None,'元'],
    ['美元','美元','美元'],['foo','foo','foo'],['£m','£m','£m'],
])
def test_unknown_missing_foreign_or_different_scales_do_not_match(units):
    assert consistent_statement_unit(units) is None


def test_snapshot_preserves_individual_original_units_and_only_converts_once():
    candidate=_candidate_result(unit='人民币万元')
    candidate['unit_check']['units']=['人民币万元','万元','万元']
    candidate['metric_evidence']={
        'revenue':{'original_unit':'人民币万元','excerpt':'收入原文'},
        'total_assets':{'original_unit':'万元','excerpt':'资产原文'},
    }
    snapshot=build_on_demand_financial_snapshot(_company(),candidate)
    assert snapshot['status']=='ready_for_human_review'
    assert snapshot['metrics'][0]['current_yuan']==10_000_000
    assert snapshot['metrics'][0]['source']['original_unit']=='人民币万元'
    assert snapshot['metrics'][3]['source']['original_unit']=='万元'
    candidate['unit_check']['units'][1]='千元'
    bad=build_on_demand_financial_snapshot(_company(),candidate)
    assert bad['status']=='needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in bad['metrics'])
