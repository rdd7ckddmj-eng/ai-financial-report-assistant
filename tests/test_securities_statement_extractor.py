"""Synthetic rejection checks plus source-linked Huatai 2024/2025 report pages."""
from decimal import Decimal
import json
from pathlib import Path
import pytest
from src.securities_statement_extractor import extract_securities_statements, SECURITIES_TEMPLATE


def fixtures():
 def values(n):return [Decimal(str(n))*x for x in map(Decimal,['1','.9','2','1.8'])]
 rows={
 'income':dict(zip(['营业总收入','手续费及佣金净收入','利息净收入','其中：利息收入','利息支出','投资收益','其他收益','公允价值变动(损失)/收益','汇兑收益/(损失)','其他业务收入','资产处置收益','营业总支出','税金及附加','业务及管理费','信用减值损失','其他业务成本','营业利润','加：营业外收入','减：营业外支出','利润总额','减：所得税费用','净利润'],map(values,[100,25,15,20,-5,40,5,5,2,7,1,-60,-2,-50,-3,-5,40,2,-2,40,-8,32]))),
 'balance':dict(zip(['资产总计','负债合计','股东权益合计','负债和股东权益总计'],map(values,[1000,700,300,1000]))),
 'cash':dict(zip(['经营活动现金流入小计','经营活动现金流出小计','经营活动产生/(使用)的现金流量净额','投资活动现金流入小计','投资活动现金流出小计','投资活动使用的现金流量净额','筹资活动现金流入小计','筹资活动现金流出小计','筹资活动(使用)/产生的现金流量净额','汇率变动对现金及现金等价物的影响','现金及现金等价物净增加/(减少)额','加：年初现金及现金等价物余额','年末现金及现金等价物余额'],map(values,[100,-70,30,20,-40,-20,50,-55,-5,1,6,50,56])))}
 rows['income']['归属于母公司股东的净利润']=[Decimal(x) for x in ['30','27','64','57.6']]
 rows['income']['少数股东损益']=[Decimal(x) for x in ['2','1.8','0','0']]
 rows['balance']['归属于母公司股东权益合计']=[Decimal(x) for x in ['290','261','600','540']]
 rows['balance']['少数股东权益']=[Decimal(x) for x in ['10','9','0','0']]
 pages=[]
 for number,(section,title) in enumerate([('balance','资产负债表'),('income','利润表'),('cash','现金流量表')],10):
  suffix='年12月31日' if section=='balance' else '年度'
  header='合并及母公司'+title+'\n2024年12月31日\n本集团\n本公司\n附注五\n'+'\n'.join(f'{y}{suffix}\n人民币元' for y in (2024,2023,2024,2023))
  def fmt(v):return '('+str(-v)+')' if v<0 else str(v)
  body='\n'.join(k+'\n60(1)\n'+'\n'.join(map(fmt,v)) for k,v in rows[section].items())
  pages.append((number,header+'\n'+body))
 return pages


def test_group_values_are_selected_after_all_four_columns_reconcile():
 r=extract_securities_statements(fixtures(),2024)
 assert r['income']['current_revenue']==100
 assert r['income']['current_net_profit']==30
 assert r['cash']['current_operating_cash_flow']==30
 assert r['balance']['current_total_assets']==1000

@pytest.mark.parametrize('change', ['group_order','year_order','currency','missing_column','wrong_parent','wrong_group','sign','duplicate','gap','too_long'])
def test_wrong_headers_columns_and_equations_are_rejected(change):
 p=fixtures()
 if change=='group_order':p=[(n,t.replace('本集团\n本公司','本公司\n本集团')) for n,t in p]
 if change=='year_order':p=[(n,t.replace('2023年度','2022年度')) for n,t in p]
 if change=='currency':p=[(n,t.replace('人民币元','美元')) for n,t in p]
 if change=='missing_column':p[0]=(10,p[0][1].replace('1000\n900.0\n2000\n1800.0','1000\n900.0\n2000',1))
 if change=='wrong_parent':p[0]=(10,p[0][1].replace('2000\n1800.0','2001\n1800.0',1))
 if change=='wrong_group':p[0]=(10,p[0][1].replace('1000\n900.0','1001\n900.0',1))
 if change=='sign':p[2]=(12,p[2][1].replace('(70)','70',1))
 if change=='duplicate':p.append((20,p[0][1]))
 if change in ('gap','too_long'):
  title='合并及母公司现金流量表'
  continuation=p[2][1].replace(title,title+' - 续').split('经营活动现金流入小计')[0]
  p.append((14 if change=='gap' else 13,continuation))
  if change=='too_long':p.extend([(14,continuation),(15,continuation)])
 assert extract_securities_statements(p,2024) is None


def test_row_wrap_and_continuation_preserve_four_columns():
 p=fixtures();title='合并及母公司现金流量表'
 header,tail=p[2][1].split('投资活动现金流入小计',1)
 p[2]=(12,header)
 intro=p[2][1].split('经营活动现金流入小计')[0].replace(title,title+' - 续')
 p.append((13,intro+'投资活动现金流入小计'+tail))
 p[2]=(12,p[2][1].replace('经营活动产生/(使用)的现金流量净额','经营活动产生/(使用)的现金流\n量净额'))
 assert extract_securities_statements(p,2024)['cash']['end_page_number']==13


def test_snapshot_provenance_and_revenue_label():
 from src.audited_company_onboarding import build_candidate_report_result
 from src.china_stock import build_company_identity
 from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
 p=[(1,'华泰证券股份有限公司2024年年度报告')]+fixtures()
 company=build_company_identity('601688','华泰证券')
 c=build_candidate_report_result(company,dict(report_year=2024,title='2024年年度报告',published_date='2025-03-29',url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',[dict(page_number=n,text=t) for n,t in p])
 assert c['statement_template']==SECURITIES_TEMPLATE
 s=build_on_demand_financial_snapshot(company,c)
 assert s['metrics'][0]['label']=='营业总收入（证券报表）'
 assert s['metrics'][0]['source']['excerpt'].startswith('营业总收入')
 assert all('仅取本集团列' in m['source']['statement'] for m in s['metrics'])
 assert all(v is None for v in s['ratios'].values())


def real_pages(year=2025):
 data=json.loads((Path(__file__).parent/'fixtures'/f'huatai_securities_{year}_statements.json').read_text())
 return [(n,t) for n,t in data['pages']]


@pytest.mark.parametrize('year,expected',[
 (2024,(41466367393.80,36577585349.48,15351162321.66,68167706589.90,814270493580.79,622376572865.76)),
 (2025,(35809920255.16,33519165071.03,16383497118.10,-12601571386.35,1077347555872.09,870351351718.75)),
])
def test_real_reports_preserve_signed_amounts_and_own_comparative_vintage(year,expected):
 r=extract_securities_statements(real_pages(year),year)
 assert r is not None
 actual=(r['income']['current_revenue'],r['income']['previous_revenue'],
         r['income']['current_net_profit'],r['cash']['current_operating_cash_flow'],
         r['balance']['current_total_assets'],r['balance']['current_total_liabilities'])
 assert actual==expected
 basis=r['income']['metric_sources']['revenue']['comparison_basis']
 assert ('上年本集团利润表经重述' in basis)==(year==2025)
 assert '未标注重述' in r['balance']['metric_sources']['total_assets']['comparison_basis']


@pytest.mark.parametrize('page,old,new',[
 # All four income columns must reconcile, including the unused company columns.
 (206,'35,809,920,255.16','35,809,920,256.16'),
 (206,'33,519,165,071.03','41,466,367,393.80'), # do not substitute the prior report's unrevised revenue
 (206,'22,296,628,570.39','22,296,628,571.39'),
 (206,'18,725,207,083.01','18,725,207,084.01'),
 # Group/current, group/prior, company/current and company/prior assets.
 (203,'1,077,347,555,872.09','1,077,347,555,873.09'),
 (203,'814,270,493,580.79','814,270,493,581.79'),
 (203,'846,202,964,923.47','846,202,964,924.47'),
 (203,'644,967,323,077.78','644,967,323,078.78'),
 # Signed operating cash flows in all four columns.
 (209,'(12,601,571,386.35)','12,601,571,386.35'),
 (209,'68,167,706,589.90','68,167,706,590.90'),
 (209,'(2,574,790,211.96)','(2,574,790,212.96)'),
 (209,'62,634,325,305.45','62,634,325,306.45'),
])
def test_real_report_rejects_changed_current_comparative_and_parent_cells(page,old,new):
 p=real_pages()
 assert any(n==page and old in t for n,t in p)
 p=[(n,t.replace(old,new,1) if n==page else t) for n,t in p]
 assert extract_securities_statements(p,2025) is None


@pytest.mark.parametrize('change',[
 'current_marker','parent_marker','inconsistent_marker','unknown_marker',
 'duplicate_variant','extra_cell','wrong_unit','missing_continuation',
 'unobserved_label_suffix','unclosed_negative','malformed_grouping',
])
def test_real_report_rejects_ambiguous_or_inconsistent_restatement_tables(change):
 p=real_pages()
 for i,(n,t) in enumerate(p):
  if n!=206:continue
  if change=='current_marker':
   t=t.replace('( 经重述)\n','').replace('2025 年度\n人民币元','2025 年度\n人民币元\n( 经重述)',1)
  if change=='parent_marker':
   t=t.replace('( 经重述)\n','').replace('一、营业总收入','( 经重述)\n一、营业总收入',1)
  if change=='inconsistent_marker':t=t.replace('( 经重述)\n','')
  if change=='unknown_marker':t=t.replace('( 经重述)','( 未经重述)')
  if change=='duplicate_variant':
   t+='\n公允价值变动(损失)/收益\n1.00\n1.00\n1.00\n1.00\n'
  if change=='extra_cell':t=t.replace('35,809,920,255.16','1.00\n35,809,920,255.16',1)
  if change=='wrong_unit':t=t.replace('人民币元','人民币千元',1)
  if change=='unobserved_label_suffix':t=t.replace('公允价值变动损失','公允价值变动损失(其他口径)',1)
  if change=='unclosed_negative':t=t.replace('(3,008,586,602.83)','(3,008,586,602.83',1)
  if change=='malformed_grouping':t=t.replace('35,809,920,255.16','358,09,920,255.16',1)
  p[i]=(n,t)
 if change=='missing_continuation':p=[(n,t) for n,t in p if n!=207]
 assert extract_securities_statements(p,2025) is None


def test_real_2025_snapshot_carries_row_pages_restatement_and_financial_sector_policy():
 from src.audited_company_onboarding import build_candidate_report_result
 from src.china_stock import build_company_identity
 from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
 company=build_company_identity('601688','华泰证券')
 c=build_candidate_report_result(company,dict(report_year=2025,title='2025年年度报告',
   published_date='2026-03-31',url='https://static.cninfo.com.cn/finalpage/2026-03-31/1225050753.PDF'),
   b'%PDF-fixture-not-full-document',[dict(page_number=n,text=t) for n,t in real_pages()])
 assert c['statement_template']==SECURITIES_TEMPLATE
 s=build_on_demand_financial_snapshot(company,c)
 assert all(s['statement_checks'].values())
 expected_pages={'revenue':206,'net_profit':206,'operating_cash_flow':209,'total_assets':203,'total_liabilities':204}
 for metric in s['metrics']:
  page=expected_pages[metric['key']]
  assert metric['source']['pages']==dict(start=page,end=page)
  assert metric['source']['excerpt_status']=='captured'
  assert '仅取本集团列' in metric['source']['statement']
 assert s['metrics'][0]['label']=='营业总收入（证券报表）'
 assert '经重述' in s['metrics'][0]['source']['comparison_basis']
 assert all(value is None for value in s['ratios'].values())
