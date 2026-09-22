import pytest
from src.financial_sector_policy import unsupported_issuer_template,is_special_financial_template

@pytest.mark.parametrize('name,text,expected',[
 ('华泰证券','华泰证券股份有限公司','securities_unsupported_v1'),
 ('中国平安','中国平安保险（集团）股份有限公司','insurance_unsupported_v1'),
 ('某某保险','某某保险股份有限公司','insurance_unsupported_v1'),
 ('格力电器','格力电器股份有限公司 委托华泰证券股份有限公司 购买中国平安保险产品',None),
 ('华泰证券','华泰证券产品介绍',None),
 ('待核验公司','华泰证券股份有限公司',None)])
def test_issuer_binding(name,text,expected):
 assert unsupported_issuer_template(dict(name=name),[(1,text)])==expected

@pytest.mark.parametrize('template',['insurance_unsupported_v1','securities_unsupported_v1'])
def test_special_policy_persists_through_review(template):
 from test_manual_financial_snapshot import COMPANY,arguments,pages
 from src.audited_company_onboarding import build_candidate_report_result
 from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
 from src.financial_snapshot_review import build_financial_snapshot_review
 p=pages();name='中国平安' if template.startswith('insurance') else '华泰证券'
 p[0]['text']=name+('保险（集团）股份有限公司' if template.startswith('insurance') else '股份有限公司')
 company=dict(COMPANY,name=name)
 args=arguments()
 r=build_candidate_report_result(company,dict(report_year=2025,title='2025年年度报告',url=args['source_url'],published_date=args['published_date']),b'%PDF-test',p)
 assert r['statement_template']==template and r['status']=='needs_review'
 s=build_on_demand_financial_snapshot(company,r)
 assert all(v is None for v in s['ratios'].values())
 assert all(m['current_yuan'] is None for m in s['metrics'])
 review=build_financial_snapshot_review(s)
 assert review['report']['statement_template']==template
 assert all(m['decision']=='pending' for m in review['metrics'])
 assert is_special_financial_template(template)

@pytest.mark.parametrize('title,year,accepted',[
 ('二零二五年年报',2025,True),('二零二四年年报',2025,False),
 ('二零二五年年报摘要',2025,False),('二零二五年中报',2025,False)])
def test_chinese_year_still_checks_exact_year_and_full_report(monkeypatch,title,year,accepted):
 from test_manual_financial_snapshot import COMPANY,arguments,pages
 from src.manual_financial_snapshot import build_manual_financial_snapshot
 p=pages();p[0]['text']=f'贵州茅台600519\n{title}'
 # The remaining synthetic headers must not supply a competing year title.
 for page in p[1:]:page['text']=page['text'].replace('2025年度','本年度')
 monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *a,**kw:p)
 if accepted:assert build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())['status']=='ready_for_human_review'
 else:
  with pytest.raises(ValueError):build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())

@pytest.mark.parametrize('template',['insurance_unsupported_v1','securities_unsupported_v1','securities_group_parent_yuan_v1'])
def test_manually_reviewed_special_metrics_do_not_reenable_ratios(template):
 # Synthetic ready figures exercise the downstream manual-review contract;
 # production unsupported parsers still return no amounts.
 from test_bank_statement_extractor import (pages,build_company_identity,
  build_candidate_report_result,build_on_demand_financial_snapshot,
  build_financial_snapshot_review,confirm_snapshot_metric,CORE_METRIC_KEYS,
  build_exportable_review_workpaper,new_research_case,_validate_workpaper,
  build_financial_review_research_case_patch,apply_case_patch)
 import json
 company=build_company_identity('600036','测试银行')
 c=build_candidate_report_result(company,dict(report_year=2025,published_date='2026-03-28',title='2025年年度报告',url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',[dict(page_number=n,text=t) for n,t in pages()])
 c['statement_template']=template
 snapshot=build_on_demand_financial_snapshot(company,c)
 review=build_financial_snapshot_review(snapshot)
 for key in CORE_METRIC_KEYS:review=confirm_snapshot_metric(review,key)
 workpaper=build_exportable_review_workpaper(review)
 assert all(x is None for x in workpaper['ratios'].values())
 case=new_research_case('special-fixture',company,mode='current',as_of_date=None,effective_market_date='2026-09-21',created_at='2026-09-21T00:00:00+00:00')
 clean=_validate_workpaper(case,workpaper)
 assert clean['report']['statement_template']==template
 patch=build_financial_review_research_case_patch(case,workpaper,patch_id='special-write',emitted_at=workpaper['exported_at'])
 updated=apply_case_patch(case,patch)
 assert '金融机构模板不计算普通公司比例' in json.dumps(updated,ensure_ascii=False)
