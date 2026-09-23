"""Real issuer excerpts and synthetic corruptions; no human confirmations."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from src.insurance_group_statement_extractor import extract_insurance_group_statements, TEMPLATES
from src.financial_sector_policy import matches_known_insurer, unsupported_issuer_template

CASES = [('picc','601319','中国人保'),('cpic','601601','中国太保'),('nci','601336','新华保险')]
LEGAL = {'601319':'中国人民保险集团股份有限公司','601601':'中国太平洋保险（集团）股份有限公司','601336':'新华人寿保险股份有限公司'}


def fixture(name):
    return json.loads((Path(__file__).parent/f'fixtures/{name}_insurance_2024_statements.json').read_text())


@pytest.mark.parametrize('name,code,issuer',CASES)
def test_real_two_year_values_and_page_sources(name,code,issuer):
    result = extract_insurance_group_statements(fixture(name)['pages'],2024,code)
    expected = {
        'picc': [(621972,553097,145),(42869,22773,146),(1766384,1557159,142),(1399158,1225490,143),(87990,70549,151)],
        'cpic': [(404089,323945,156),(44960,27257,157),(2834907,2343962,154),(2516426,2076258,155),(154404,137863,159)],
        'nci': [(132555,71547,119),(26229,8712,120),(1692297,1403257,117),(1596028,1298165,118),(96290,91548,125)],
    }
    for (section,key),(current,prior,page) in zip([('income','revenue'),('income','net_profit'),('balance','total_assets'),('balance','total_liabilities'),('cash','operating_cash_flow')],expected[name]):
        assert result[section]['current_'+key] == current
        assert result[section]['previous_'+key] == prior
        assert result[section]['metric_sources'][key]['page_number'] == page
        assert result[section]['unit'] == '人民币百万元'


@pytest.mark.parametrize('name,code,issuer',CASES)
@pytest.mark.parametrize('change',['year','unit','gap','missing','parent','current_amount','prior_amount','extra_column','duplicate_row','duplicate_table','missing_footer','sign','note','bad_commas'])
def test_corrupt_statements_are_rejected(name,code,issuer,change):
    pages = fixture(name)['pages']
    from src.insurance_group_statement_extractor import PROFILES, _lines
    p = PROFILES[code]
    pages = [(n,'\n'.join(_lines(t))) for n,t in pages]
    def replace(old,new):
        nonlocal pages
        assert any(old in t for _,t in pages)
        pages = [(n,t.replace(old,new)) for n,t in pages]
    first = {'picc':'621,972\n553,097','cpic':'404,089\n323,945','nci':'132,555\n71,547\n129,609\n70,995'}[name]
    if change == 'year': replace('2023年','2022年')
    if change == 'unit': replace('人民币百万元','人民币万元')
    if change == 'gap': pages[1] = (pages[1][0]+1,pages[1][1])
    if change == 'missing': pages.pop(1)
    if change == 'parent': replace('合并','母公司')
    if change == 'current_amount': replace(first,first.replace(first.splitlines()[0],'999,999'))
    if change == 'prior_amount': replace(first,first.replace(first.splitlines()[1],'999,999'))
    if change == 'extra_column': replace(first,first+'\n888,888')
    if change == 'duplicate_row': replace(first,first+'\n'+p['revenue']+'\n'+first)
    if change == 'duplicate_table': pages += [(n+1000,t) for n,t in pages]
    if change == 'missing_footer': replace('后附财务报表附注为本财务报表的组成部分','')
    if change == 'sign':
        value = {'picc':'551,328','cpic':'(348,378)','nci':'(104,338)'}[name]
        replace(value,'('+value+')' if name == 'picc' else value.strip('()'))
    if change == 'note': replace(first,'99\n'+first)
    if change == 'bad_commas': replace(first, first.replace(',', ',,', 1))
    assert extract_insurance_group_statements(pages,2024,code) is None


@pytest.mark.parametrize('change',['parent_value','parent_order','parent_na','group_na','parent_year','no_group_heading'])
def test_nci_four_columns_and_not_applicable_cells(change):
    p = fixture('nci')['pages']
    def replace(old,new):
        nonlocal p
        assert any(old in t for _,t in p)
        p = [(n,t.replace(old,new)) for n,t in p]
    if change == 'parent_value': replace('129,609','129,619')
    if change == 'parent_order': replace('合并\n公司','公司\n合并')
    if change == 'parent_na': replace('/\n/','0\n0')
    if change == 'group_na': replace('26,229\n8,712','/\n8,712')
    if change == 'parent_year': replace('2024年度\n2023年度\n2024年度\n2023年度','2024年度\n2023年度\n2023年度\n2024年度')
    if change == 'no_group_heading': replace('合并\n公司','')
    assert extract_insurance_group_statements(p,2024,'601336') is None


@pytest.mark.parametrize('name,code,issuer',CASES)
def test_candidate_and_review_preserve_insurance_basis(name,code,issuer):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    from src.financial_snapshot_review import build_financial_snapshot_review
    company = build_company_identity(code,issuer); f = fixture(name)
    pages = [dict(page_number=1,text=LEGAL[code])]+[dict(page_number=n,text=t) for n,t in f['pages']]
    result = build_candidate_report_result(company,dict(report_year=2024,title='2024年年度报告',published_date='2025-03-28',url=f['source_url']),b'%PDF-synthetic-integration',pages)
    assert result['statement_template'] == TEMPLATES[code]
    assert result['status'] == 'ready_for_human_review'
    snapshot = build_on_demand_financial_snapshot(company,result)
    assert all(v is None for v in snapshot['ratios'].values())
    assert all(m['decision'] == 'pending' for m in build_financial_snapshot_review(snapshot)['metrics'])
    revenue = snapshot['metrics'][0]
    assert '非保费收入' in revenue['source']['accounting_basis']
    if name != 'nci':
        assert revenue['label'] == '营业总收入（保险报表）'
        assert '营业总收入' in revenue['source']['accounting_basis']
    assert all(m['source']['excerpt_status'] == 'captured' for m in snapshot['metrics'])
    for c in [dict(company,name='其他保险'),dict(company,code='601628')]:
        assert not matches_known_insurer(c,[(1,LEGAL[code])])


@pytest.mark.parametrize('name,code,issuer',CASES)
def test_wrong_year_or_wrong_profile_does_not_enable_template(name,code,issuer):
    assert extract_insurance_group_statements(fixture(name)['pages'],2023,code) is None
    assert extract_insurance_group_statements(fixture(name)['pages'],2024,'601628') is None


def test_chinalife_identity_is_recognised_but_remains_unsupported():
    c = dict(code='601628',name='中国人寿'); p = [(1,'中国人寿保险股份有限公司')]
    assert unsupported_issuer_template(c,p) == 'insurance_unsupported_v1'
    assert not matches_known_insurer(c,[(1,'中国人寿产品简介')])
    assert not matches_known_insurer(dict(code='600519',name='贵州茅台'),p)


@pytest.mark.parametrize('url',[
 'https://www.cpic.com.cn/upload/resources/file/2025/04/09/86079.pdf',
 'https://www.pingan.com/app_upload/images/info/upload/e1fd26bb-177b-485f-9778-cd6fabcc6476.pdf',
])
def test_individually_verified_issuer_sources_do_not_allow_other_urls(url):
    from src.china_stock import is_allowed_disclosure_url,build_cninfo_pdf_url
    assert is_allowed_disclosure_url(url)
    for invalid in [url+'?redirect=https://example.com',url.replace('https:','http:'),url.replace('.pdf','-other.pdf'),url.replace('www.','evil.'),url.replace('.com','.com.evil.test'),url.replace('https://','https://user@')]:
        assert not is_allowed_disclosure_url(invalid)
    with pytest.raises(ValueError): build_cninfo_pdf_url(url)


@pytest.mark.parametrize('name,code,issuer',CASES)
def test_known_insurer_with_image_only_name_never_falls_back_to_general(name,code,issuer):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    f = fixture(name)
    # Even valid figures cannot enable the issuer adapter without legal-name evidence.
    result = build_candidate_report_result(build_company_identity(code,issuer),dict(report_year=2024,title='2024年年度报告',published_date='2025-03-28',url=f['source_url']),b'%PDF-synthetic',
        [dict(page_number=n,text=t.replace(LEGAL[code],'')) for n,t in f['pages']])
    assert result['statement_template'] == 'insurance_unsupported_v1'
    assert all(v is None for v in result['values'].values())
    assert result['status'] == 'needs_review'


def test_chinalife_image_cover_cannot_trigger_general_company_ratios():
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    result=build_candidate_report_result(build_company_identity('601628','中国人寿'),dict(report_year=2024,title='2024年年度报告',published_date='2025-03-27',url='https://static.cninfo.com.cn/synthetic-fixture.pdf'),b'%PDF-fixture',
        [dict(page_number=1,text='年报\nA股股票代码: 601628')])
    assert result['statement_template'] == 'insurance_unsupported_v1'
    assert all(v is None for v in result['values'].values())
