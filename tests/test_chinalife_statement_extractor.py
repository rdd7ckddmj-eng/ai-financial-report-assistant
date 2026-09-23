"""Verified issuer report excerpts; mutations below are synthetic failures."""
import json
from pathlib import Path
import pytest
from src.chinalife_statement_extractor import extract_chinalife_statements, matches_chinalife_issuer, CHINALIFE_TEMPLATE


def fixture(year):
    return json.loads((Path(__file__).parent/f'fixtures/chinalife_insurance_{year}_statements.json').read_text())


@pytest.mark.parametrize('year',[2024,2025])
def test_real_report_values_pages_and_prior_year(year):
    result=extract_chinalife_statements(fixture(year)['pages'],year)
    expected={2024:[(528567,405040,100),(106935,51184,100),(6769546,5653727,96),(6248298,5316011,97),(378795,384366,108)],
              2025:[(615678,528567,93),(154078,106935,93),(7591004,6769546,89),(6982611,6248298,90),(459925,378795,99)]}
    for (section,key),(current,previous,page) in zip([('income','revenue'),('income','net_profit'),('balance','total_assets'),('balance','total_liabilities'),('cash','operating_cash_flow')],expected[year]):
        assert result[section]['current_'+key]==current
        assert result[section]['previous_'+key]==previous
        assert result[section]['metric_sources'][key]['page_number']==page
        assert result[section]['metric_sources'][key]['comparison_comparable']==(year==2025)


@pytest.mark.parametrize('year',[2024,2025])
@pytest.mark.parametrize('change',['wrong_year','wrong_unit','missing_page','gap','parent','duplicate','bad_amount','bad_previous','bad_comma','extra_integer','extra_decimal','extra_na','extra_year','bad_notes','missing_end'])
def test_statement_boundaries_fail_closed(year,change):
    p=fixture(year)['pages']
    def replace(old,new):
        nonlocal p
        assert any(old in t for _,t in p)
        p=[(n,t.replace(old,new)) for n,t in p]
    first='528,567\n405,040\n388,895' if year==2024 else '615,678\n528,567'
    if change=='wrong_year': replace(str(year-1)+'年',str(year-2)+'年')
    if change=='wrong_unit': replace('人民币百万元','人民币万元')
    if change=='missing_page': p.pop(-1)
    if change=='gap': p[-1]=(p[-1][0]+1,p[-1][1])
    if change=='parent': replace('合并利润表','公司利润表')
    if change=='duplicate': p+=[(n+1000,t) for n,t in p[2:]]
    if change=='bad_amount': replace(first,first.replace(first.splitlines()[0],'999,999'))
    if change=='bad_previous': replace(first,first.replace(first.splitlines()[1],'999,999'))
    if change=='bad_comma': replace(first,first.replace(',',',,',1))
    if change=='extra_integer': replace(first,first+'\n999,999')
    if change=='extra_decimal': replace(first,first+'\n777.77')
    if change=='extra_na': replace(first,first+'\n不适用')
    if change=='extra_year': replace('一、营业收入',f'{year-3}年度\n一、营业收入')
    if change=='bad_notes': replace(first,'99\n'+first)
    if change=='missing_end': replace('后附财务报表附注为本财务报表的组成部分。','')
    assert extract_chinalife_statements(p,year) is None


@pytest.mark.parametrize('change',['restatement','opening_amount','na_to_zero','current_to_na'])
def test_transition_columns_not_applicable_and_restated_markers(change):
    p=fixture(2024)['pages']
    def replace(old,new):
        nonlocal p
        assert any(old in t for _,t in p)
        p=[(n,t.replace(old,new)) for n,t in p]
    if change=='restatement': replace('已重述','未重述')
    if change=='opening_amount': replace('4,665,367','4,665,467')
    if change=='na_to_zero': replace('不适用','0')
    if change=='current_to_na': replace('120,958','不适用')
    assert extract_chinalife_statements(p,2024) is None


@pytest.mark.parametrize('year',[2024,2025])
def test_cover_and_legal_information_page_both_required(year):
    c=dict(code='601628',name='中国人寿');p=fixture(year)['pages']
    assert matches_chinalife_issuer(c,p)
    assert not matches_chinalife_issuer(c,p[1:])
    assert not matches_chinalife_issuer(c,p[:1]+p[2:])
    assert not matches_chinalife_issuer(dict(code='601319',name='中国人寿'),p)
    assert not matches_chinalife_issuer(dict(code='601628',name='其他公司'),p)
    assert not matches_chinalife_issuer(c,[(n,t.replace('公司法定中文名称','合作方中文名称')) for n,t in p])


def snapshot(year):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    f=fixture(year);company=build_company_identity('601628','中国人寿')
    result=build_candidate_report_result(company,dict(report_year=year,title=f'{year}年年度报告',url=f['source_url'],published_date=f['published_date']),b'%PDF-synthetic-integration',[dict(page_number=n,text=t) for n,t in f['pages']])
    assert result['status']=='ready_for_human_review'
    assert result['statement_template']==CHINALIFE_TEMPLATE
    return build_on_demand_financial_snapshot(company,result)


@pytest.mark.parametrize('year',[2024,2025])
def test_comparability_kept_in_snapshot_review_and_export(year):
    from src.financial_snapshot_review import build_financial_snapshot_review, confirm_snapshot_metric, build_exportable_review_workpaper
    s=snapshot(year)
    assert all(v is None for v in s['ratios'].values())
    for m in s['metrics']:
        assert m['source']['excerpt_status']=='captured'
        assert (m['change_rate'] is None)==(year==2024)
        if year==2024:
            assert '不自动计算同比' in m['change_rate_note']
            assert '金融工具未重述' in m['source']['comparison_basis']
    review=build_financial_snapshot_review(s)
    assert all(m['decision']=='pending' for m in review['metrics'])
    # Synthetic confirmation only exercises downstream policy, not real human work.
    for m in s['metrics']:review=confirm_snapshot_metric(review,m['key'])
    workpaper=build_exportable_review_workpaper(review)
    assert all(v is None for v in workpaper['ratios'].values())
    assert all(m['source']['comparison_comparable']==(year==2025) for m in workpaper['metrics'])


def test_unknown_year_is_not_enabled():
    assert extract_chinalife_statements(fixture(2025)['pages'],2026) is None


def test_transition_rejects_extra_leading_date_column():
    p=fixture(2024)['pages']
    p=[(n,t.replace('2024年 \n12月31日','2025年\n12月31日\n2024年 \n12月31日')) for n,t in p]
    assert extract_chinalife_statements(p,2024) is None


@pytest.mark.parametrize('extra',['N/A','NA','n.a.'])
@pytest.mark.parametrize('year',[2024,2025])
def test_english_missing_value_cannot_hide_extra_column(year,extra):
    p=fixture(year)['pages'];first='528,567\n405,040\n388,895' if year==2024 else '615,678\n528,567'
    p=[(n,t.replace(first,first+'\n'+extra)) for n,t in p]
    assert extract_chinalife_statements(p,year) is None


@pytest.mark.parametrize('year',[2024,2025])
def test_no_leading_combined_date_before_header(year):
    p=fixture(year)['pages']
    p=[(n,t.replace('（除特别注明外，金额单位为人民币百万元）','（除特别注明外，金额单位为人民币百万元）\n2026年12月31日')) for n,t in p]
    assert extract_chinalife_statements(p,year) is None
