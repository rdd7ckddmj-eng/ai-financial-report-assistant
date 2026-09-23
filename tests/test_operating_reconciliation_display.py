"""Show the calculation evidence without turning subitems into extra income."""
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from src.on_demand_financial_snapshot import (
    operating_reconciliation_rows, build_on_demand_financial_snapshot,
    build_financial_snapshot_report_html,
)
from test_general_operating_reconciliation import check
from test_on_demand_financial_snapshot import _candidate_result, _company


def result():
    return {'income_reconciliation': check()}


def test_source_signs_subitems_and_physical_pages_remain_visible():
    rows=operating_reconciliation_rows(result())
    finance=next(r for r in rows if r['原文科目']=='财务费用')
    assert finance=={'原文科目':'财务费用','计算方式':'减去原值',
                     '本期原值':'-10.00','比较期原值':'10.00','PDF页码':'10'}
    detail=next(r for r in rows if r['原文科目']=='其中：利息费用')
    assert detail['计算方式']=='已含在上级科目'
    subtotal=next(r for r in rows if r['原文科目']=='营业利润')
    assert subtotal['计算方式']=='核对小计'


@pytest.mark.parametrize('status',['missing_evidence','unsupported_layout',None])
def test_partial_operating_evidence_does_not_look_like_a_complete_formula(status):
    value=result()
    value['income_reconciliation']['operating_reconciliation']['status']=status
    assert operating_reconciliation_rows(value)==[]
    assert operating_reconciliation_rows({})==[]


def test_portable_report_keeps_components_and_escapes_source_labels():
    value=result()
    value['income_reconciliation']['operating_reconciliation']['evidence']['operating_revenue']['label']='<script>bad()</script>'
    candidate=_candidate_result()
    candidate.update(value)
    snapshot=build_on_demand_financial_snapshot(_company(),candidate)
    html=build_financial_snapshot_report_html(snapshot)
    assert '营业收入至税前利润的原文分项' in html
    assert '已含在上级科目' in html and '-10.00' in html
    assert '&lt;script&gt;bad()&lt;/script&gt;' in html
    assert '<script>bad()</script>' not in html


def test_page_shows_existing_differences_and_separate_source_components():
    at=AppTest.from_string('''
import streamlit as st
from src.app import _show_income_reconciliation
_show_income_reconciliation(st.session_state['sample'])
''')
    at.session_state['sample']=deepcopy(result())
    at.run(timeout=20)
    assert not at.exception
    assert len(at.dataframe)==2
    assert list(at.dataframe[1].value.columns)==['原文科目','计算方式','本期原值','比较期原值','PDF页码']
    assert any('不重复加总' in item.value for item in at.caption)
