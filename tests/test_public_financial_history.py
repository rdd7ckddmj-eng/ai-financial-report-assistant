from copy import deepcopy
from datetime import date
import json

import pytest

from src.china_stock import build_company_identity, DataSourceError
from src.public_financial_history import (
    build_public_financial_history, validate_public_financial_history,
    fetch_public_financial_history, compare_public_financial_histories,
    render_public_financial_report, MAX_RESPONSE_BYTES,
)
from src.research_case import new_research_case, apply_case_patch
from src.research_case_public_financial_bridge import build_public_financial_case_patch
from src.comprehensive_research import build_comprehensive_research_brief
from src.comprehensive_research_report import build_comprehensive_research_audit_payload, build_comprehensive_research_report_html

NOW = '2026-09-21T12:00:00+00:00'
COMPANY = build_company_identity('000651', '格力电器')


def row(year=2025, code='000651', **changes):
    value = dict(SECUCODE=build_company_identity(code)['canonical_code'], SECURITY_CODE=code,
                 SECURITY_NAME_ABBR='测试公司', ORG_TYPE='通用', REPORT_DATE=f'{year}-12-31',
                 REPORT_TYPE='年报', NOTICE_DATE=f'{year+1}-04-20', UPDATE_DATE=f'{year+1}-04-20',
                 CURRENCY='CNY', OPERATE_INCOME_PK=1000, TOTALOPERATEREVE=1100,
                 PARENTNETPROFIT=100, NETCASH_OPERATE_PK=200, TOTAL_ASSETS_PK=2000,
                 LIABILITY=800, TOTAL_EQUITY_PK=1200)
    value.update(changes)
    return value


def history(code='000651', **changes):
    return build_public_financial_history(build_company_identity(code, '测试公司'),
            [row(2024, code=code), row(code=code, **changes)], fetched_at=NOW)


def case(code='000651', historical=False):
    return new_research_case('test-public', build_company_identity(code, '测试公司'),
        mode='historical' if historical else 'current', as_of_date='2026-09-21' if historical else None,
        effective_market_date='2026-09-21', created_at=NOW)


@pytest.mark.parametrize('code', ['600036','000651','300750','688981','920002','830799'])
def test_all_board_identities(code):
    value=history(code)
    assert validate_public_financial_history(value)==value
    assert value['company']['canonical_code']==build_company_identity(code)['canonical_code']
    assert value['status']=='public_unverified'


def test_revenue_is_not_total_and_calculations_are_deterministic():
    value=history(OPERATE_INCOME_PK=1200, PARENTNETPROFIT=150, NETCASH_OPERATE_PK=100)
    latest=value['points'][-1]
    assert latest['revenue']==1200 and latest['total_operating_revenue']==1100
    assert latest['revenue_growth']==pytest.approx(.2)
    assert latest['net_profit_growth']==pytest.approx(.5)
    assert latest['liabilities_to_assets']==.4
    assert '背离候选' in value['observations'][0]


@pytest.mark.parametrize('field,value', [('CURRENCY','USD'),('SECUCODE','600519.SH'),('SECURITY_CODE','600519'),
    ('REPORT_TYPE','中报'),('REPORT_DATE','2025-06-30'),('NOTICE_DATE','2027-01-01'),
    ('UPDATE_DATE','2025-01-01'),('PARENTNETPROFIT',float('nan')),('PARENTNETPROFIT',True),
    ('OPERATE_INCOME_PK',-1),('TOTAL_ASSETS_PK','1亿元')])
def test_invalid_fields_rejected(field,value):
    with pytest.raises(ValueError): history(**{field:value})


def test_missing_is_not_zero_or_other_revenue():
    value=history(OPERATE_INCOME_PK=None, NETCASH_OPERATE_PK=None)
    assert value['points'][-1]['revenue'] is None
    assert value['points'][-1]['revenue_growth'] is None
    assert '无法判断' in value['observations'][0]
    assert value['issues']


def test_negative_base_and_nonconsecutive_years():
    value=build_public_financial_history(COMPANY,[row(2024,PARENTNETPROFIT=-100),row()],fetched_at=NOW)
    assert value['points'][-1]['net_profit_growth'] is None
    assert value['points'][-1]['net_profit_change']==200
    value=build_public_financial_history(COMPANY,[row(2023),row()],fetched_at=NOW)
    assert value['points'][-1]['revenue_growth'] is None
    assert '无法判断' in value['observations'][0]


@pytest.mark.parametrize('org',['银行','保险','证券','未知类型'])
def test_financial_sectors_do_not_use_generic_cash_rules(org):
    value=history(ORG_TYPE=org, PARENTNETPROFIT=150, NETCASH_OPERATE_PK=-500, NEWCAPITALADER=18.2)
    assert value['points'][-1]['cash_to_parent_profit'] is None
    assert value['points'][-1]['parent_profit_margin'] is None
    assert '不适用普通企业' in value['observations'][0]
    if org=='银行': assert value['points'][-1]['sector_metrics_percent']['资本充足率']==18.2


def test_bad_balance_withholds_ratio():
    value=history(TOTAL_EQUITY_PK=1000)
    assert value['points'][-1]['balance_check']=='failed'
    assert value['points'][-1]['liabilities_to_assets'] is None


@pytest.mark.parametrize('rows',[[],[row(),row()],[row(2019+i) for i in range(7)]])
def test_bounded_unique_periods(rows):
    with pytest.raises(ValueError): build_public_financial_history(COMPANY,rows,fetched_at=NOW)


def test_tampering_and_export_escaping():
    value=history(SECURITY_NAME_ABBR='<script>alert(1)</script>')
    value['points'][-1]['revenue']=9999
    with pytest.raises(ValueError): validate_public_financial_history(value)
    value=build_public_financial_history(build_company_identity('000651','<script>'),[row()],fetched_at=NOW)
    report=render_public_financial_report(value)
    assert '<script>' not in report and '&lt;script&gt;' in report
    assert '非官方年报' in report and value['fingerprint'] in report


def test_comparison_common_year_and_duplicates():
    first,second=history(),history('600036')
    result=compare_public_financial_histories([first,second])
    assert result['year']==2025 and result['common_years']==[2024,2025]
    with pytest.raises(ValueError): compare_public_financial_histories([first,first])
    with pytest.raises(ValueError): compare_public_financial_histories([first,second],2023)


def test_bridge_is_candidate_only_and_replay_safe():
    original=case()
    patch=build_public_financial_case_patch(original,history(),emitted_at=NOW)
    updated=apply_case_patch(original,patch)
    assert updated['questions']['financial_quality']['status']=='in_progress'
    assert updated['evidence']==original['evidence']
    assert apply_case_patch(updated,patch)==updated
    assert original['revision']==0
    with pytest.raises(ValueError): build_public_financial_case_patch(case(historical=True),history(),emitted_at=NOW)
    with pytest.raises(ValueError): build_public_financial_case_patch(case('600036'),history(),emitted_at=NOW)


def test_comprehensive_and_export_preserve_public_provenance():
    value=history()
    brief=build_comprehensive_research_brief(COMPANY,public_financial_history=value,generated_on=date(2026,9,21))
    lane=brief['evidence_lanes'][-1]
    assert lane['status']=='partial' and lane['source_url'] is None
    assert '公开财务' in brief['findings'][-1]['headline']
    audit=build_comprehensive_research_audit_payload(brief)
    assert audit['public_financial_history']==value
    assert value['fingerprint'] in build_comprehensive_research_report_html(brief)
    for bad in [history('600036'), build_public_financial_history(COMPANY,[row()],fetched_at='2026-09-20T12:00:00+00:00')]:
        brief=build_comprehensive_research_brief(COMPANY,public_financial_history=bad,generated_on=date(2026,9,21))
        assert brief['public_financial_history'] is None
        assert brief['evidence_lanes'][-1]['status']=='unavailable'


class Response:
    status_code=200
    def __init__(self,content): self.content=content
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def raise_for_status(self): pass
    def iter_content(self,chunk_size): yield self.content


def test_fetch_bounds_and_identity(monkeypatch):
    calls=[]
    content=json.dumps({'success':True,'result':{'data':[row()]}}).encode()
    def get(url,**kwargs):
        calls.append(kwargs)
        return Response(content)
    monkeypatch.setattr('requests.get',get)
    value=fetch_public_financial_history(COMPANY)
    assert value['points'][-1]['revenue']==1000
    assert calls[0]['params']['pageSize']==6
    assert calls[0]['timeout']==(5,15) and not calls[0]['allow_redirects']
    content=b'x'*(MAX_RESPONSE_BYTES+1)
    with pytest.raises(DataSourceError,match='大小'): fetch_public_financial_history(COMPANY)
    content=json.dumps({'success':True,'result':{'data':[row(code='600036')]}}).encode()
    with pytest.raises(DataSourceError,match='不匹配'): fetch_public_financial_history(COMPANY)


@pytest.mark.parametrize('stamp',[None,123,{},'2026-09-21'])
def test_malformed_fetch_timestamp_rejected(stamp):
    with pytest.raises(ValueError):
        build_public_financial_history(COMPANY,[row()],fetched_at=stamp)
