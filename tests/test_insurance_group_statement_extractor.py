"""Real issuer excerpts and synthetic corruptions; no human confirmations."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from src.insurance_group_statement_extractor import extract_insurance_group_statements, TEMPLATES
from src.financial_sector_policy import matches_known_insurer, unsupported_issuer_template

CASES = [('picc','601319','中国人保'),('cpic','601601','中国太保'),('nci','601336','新华保险')]
LEGAL = {'601319':'中国人民保险集团股份有限公司','601601':'中国太平洋保险（集团）股份有限公司','601336':'新华人寿保险股份有限公司'}


def fixture(name, year=2024):
    return json.loads((Path(__file__).parent/f'fixtures/{name}_insurance_{year}_statements.json').read_text())


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


@pytest.mark.parametrize('name,code,issuer,year', [(*c, 2024) for c in CASES] + [(*c, 2025) for c in CASES[1:]])
@pytest.mark.parametrize('change',['year','unit','gap','missing','parent','current_amount','prior_amount','extra_column','duplicate_row','duplicate_table','missing_footer','sign','note','bad_commas'])
def test_corrupt_statements_are_rejected(name,code,issuer,year,change):
    pages = fixture(name,year)['pages']
    from src.insurance_group_statement_extractor import PROFILES, _lines
    p = PROFILES[code]
    pages = [(n,'\n'.join(_lines(t))) for n,t in pages]
    def replace(old,new):
        nonlocal pages
        assert any(old in t for _,t in pages)
        pages = [(n,t.replace(old,new)) for n,t in pages]
    first = {'picc':'621,972\n553,097','cpic':'404,089\n323,945','nci':'132,555\n71,547\n129,609\n70,995'}[name]
    if year == 2025:
        first = {'cpic':'435,156\n404,089','nci':'157,745\n132,555\n153,132\n129,609'}[name]
    if change == 'year': replace(f'{year-1}年',f'{year-2}年')
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
        if year == 2025: value = {'cpic':'(368,982)','nci':'(120,544)'}[name]
        replace(value,'('+value+')' if name == 'picc' else value.strip('()'))
    if change == 'note': replace(first,'99\n'+first)
    if change == 'bad_commas': replace(first, first.replace(',', ',,', 1))
    assert extract_insurance_group_statements(pages,year,code) is None


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


@pytest.mark.parametrize('name,code,expected', [
    ('cpic','601601',[(435156,404089,160),(53505,44960,161),(3144767,2834907,158),(2810543,2516426,159),(195523,154404,163)]),
    ('nci','601336',[(157745,132555,122),(36284,26229,123),(1899484,1692297,120),(1787906,1596028,121),(110916,96290,128)]),
])
def test_real_2025_values_preserve_both_years_and_physical_pages(name,code,expected):
    result = extract_insurance_group_statements(fixture(name,2025)['pages'],2025,code)
    for (section,key),(current,prior,page) in zip([('income','revenue'),('income','net_profit'),('balance','total_assets'),('balance','total_liabilities'),('cash','operating_cash_flow')],expected):
        assert result[section]['current_'+key] == current
        assert result[section]['previous_'+key] == prior
        assert result[section]['metric_sources'][key]['page_number'] == page
    # No blanket enabling of the next year or other insurers.
    assert extract_insurance_group_statements(fixture(name,2025)['pages'],2026,code) is None
    assert extract_insurance_group_statements(fixture(name,2025)['pages'],2025,'601319') is None


@pytest.mark.parametrize('name,code,year', [('picc','601319',2024),('cpic','601601',2024),('nci','601336',2024),('cpic','601601',2025),('nci','601336',2025)])
@pytest.mark.parametrize('change',['extra_year','restated_header','decimal_cell','malformed_cell','na_cell','slash_decimal'])
def test_extra_header_and_malformed_cells_cannot_hide_as_labels(name,code,year,change):
    from src.insurance_group_statement_extractor import _lines, _profile
    profile = _profile(code,year)
    pages = [(n,'\n'.join(_lines(t))) for n,t in fixture(name,year)['pages']]
    first = {
        ('picc',2024):'621,972\n553,097',('cpic',2024):'404,089\n323,945',
        ('nci',2024):'132,555\n71,547\n129,609\n70,995',
        ('cpic',2025):'435,156\n404,089',('nci',2025):'157,745\n132,555\n153,132\n129,609',
    }[name,year]
    if change in ('extra_year','restated_header'):
        old = '\n'+profile['revenue']+'\n'+first
        extra = '2022年度' if change == 'extra_year' else '(已重述)'
        new = '\n'+extra+old
    else:
        old = first
        extra = dict(decimal_cell='777.77',malformed_cell='777,,777',na_cell='不适用',slash_decimal='/7.77')[change]
        new = first+'\n'+extra
    assert any(old in text for _,text in pages)
    pages = [(n,t.replace(old,new)) for n,t in pages]
    assert extract_insurance_group_statements(pages,year,code) is None


@pytest.mark.parametrize('change',['parent_amount','parent_order','parent_na','old_note','footer_order'])
def test_nci_2025_group_parent_and_pdf_order_are_explicit(change):
    from src.insurance_group_statement_extractor import _lines,END
    pages = [(n,'\n'.join(_lines(t))) for n,t in fixture('nci',2025)['pages']]
    if change == 'footer_order':
        pages = [(n,t.replace(END+'。','')+'\n'+END+'。' if n in (122,123,128,129) else t) for n,t in pages]
    else:
        old,new = dict(parent_amount=('153,132','153,232'),parent_order=('合并\n公司','公司\n合并'),parent_na=('/\n/','0\n0'),old_note=('53(1)/56(6)','51(1)/54(6)'))[change]
        assert any(old in text for _,text in pages)
        pages = [(n,t.replace(old,new)) for n,t in pages]
    assert extract_insurance_group_statements(pages,2025,'601336') is None


@pytest.mark.parametrize('name,code,issuer', CASES[1:])
def test_2025_candidate_keeps_insurance_review_and_page_evidence(name,code,issuer):
    from src.audited_company_onboarding import build_candidate_report_result
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
    from src.financial_snapshot_review import build_financial_snapshot_review
    f = fixture(name,2025)
    pages = [dict(page_number=1,text=LEGAL[code])]+[dict(page_number=n,text=t) for n,t in f['pages']]
    result = build_candidate_report_result(build_company_identity(code,issuer),
        dict(report_year=2025,title='2025年年度报告',published_date='2026-03-27',url=f['source_url']),
        b'%PDF-synthetic-integration',pages)
    assert result['statement_template'] == TEMPLATES[code]
    assert result['status'] == 'ready_for_human_review'
    snapshot = build_on_demand_financial_snapshot(build_company_identity(code,issuer),result)
    assert all(v is None for v in snapshot['ratios'].values())
    assert all(m['decision'] == 'pending' for m in build_financial_snapshot_review(snapshot)['metrics'])
    assert all(m['source']['excerpt_status'] == 'captured' for m in snapshot['metrics'])


def test_picc_2025_real_pdf_without_numeric_text_stays_unsupported():
    from src.insurance_group_statement_extractor import VERIFIED_YEARS, _extract
    f = json.loads((Path(__file__).parent/'fixtures/picc_insurance_2025_numeric_text_missing.json').read_text())
    assert 2025 not in VERIFIED_YEARS['601319']
    assert extract_insurance_group_statements(f['pages'],2025,'601319') is None
    # Even if the explicit year gate were removed, the actual text layer
    # cannot meet the statement year/amount requirements.
    with pytest.raises(ValueError):
        _extract(f['pages'],2025,'601319')
