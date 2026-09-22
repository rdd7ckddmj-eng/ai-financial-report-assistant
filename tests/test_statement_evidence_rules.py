import copy
import pytest
from src.statement_evidence_rules import integer_rounding_tolerance, inherit_statement_units
from src.cash_flow_extractor import extract_cash_flow_figures
from test_cash_flow_extractor import CHINESE_CASH_FLOW_TEXT
from src.balance_sheet_extractor import extract_balance_sheet_figures
from test_balance_sheet_extractor import CHINESE_BALANCE_SHEET_TEXT

@pytest.mark.parametrize('unit,rows,lines,expected',[
 ('千元',[(100,90)],['100 90'],1),('人民币百万元',[(100,90)],['100 90'],1),
 ('元',[(100,90)],['100 90'],.5),('',[(100,90)],['100 90'],.5),
 ('千元',[(100,90)],['100.00 90.00'],.5),('千元',[(100.1,90)],['100 90'],.5),
 ('美元',[(100,90)],['100 90'],.5),('千元',[None],[],.5)])
def test_rounding_requires_explicit_scaled_integer_display(unit,rows,lines,expected):
 assert integer_rounding_tolerance(unit,rows,lines)==expected


def unit_fixture():
 pages=[(10,'二、财务报表\n财务附注中报表的单位为：千元\n1、合并资产负债表'),
        (11,'合并利润表'),(12,'合并现金流量表')]
 statements=[dict(page_number=p,end_page_number=p,unit='') for p in (10,11,12)]
 return pages,statements


def test_inherited_unit_keeps_declaration_page():
 p,s=unit_fixture();inherit_statement_units(p,s)
 assert all(x['unit']=='千元' and 'PDF第10页' in x['unit_source_note'] for x in s)

@pytest.mark.parametrize('case',['no_header','duplicate','gap','too_far','notes','mixed','currency','local_conflict','missing_statement'])
def test_ambiguous_or_out_of_scope_units_never_inherit(case):
 p,s=unit_fixture()
 if case=='no_header':p[0]=(10,p[0][1].replace('二、财务报表',''))
 if case=='duplicate':p.append((13,p[0][1]))
 if case=='gap':p.pop(1)
 if case=='too_far':s[-1]['end_page_number']=31
 if case=='notes':p[1]=(11,'三、财务报表附注\n合并利润表')
 if case=='mixed':p[1]=(11,'合并利润表\n单位：万元')
 if case=='currency':p[1]=(11,'合并利润表\n单位：美元')
 if case=='local_conflict':s[0]['unit']='万元'
 if case=='missing_statement':s[0]=None
 inherit_statement_units(p,s)
 assert all(not x.get('unit_source_note') for x in s if x)
 assert not all(x and x['unit'] for x in s)

@pytest.mark.parametrize('delta,accepted',[(1,True),(2,False),(-1,True),(-2,False)])
def test_cash_scaled_integer_rounding_is_bounded_in_both_periods(delta,accepted):
 text=CHINESE_CASH_FLOW_TEXT.replace('单位：元','单位：千元').replace('.00','')
 text=text.replace('10,000',f'{10000+delta:,}').replace('9,000',f'{9000-delta:,}')
 assert (extract_cash_flow_figures(1,text) is not None)==accepted
 # Same discrepancy remains invalid for yuan or explicit fractional precision.
 assert extract_cash_flow_figures(1,text.replace('单位：千元','单位：元')) is None
 assert extract_cash_flow_figures(1,text.replace('20,000','20,000.00')) is None

@pytest.mark.parametrize('delta,accepted',[(1,True),(2,False),(-1,True),(-2,False)])
def test_balance_scaled_rounding_is_bounded(delta,accepted):
 text=f'''合并资产负债表
单位：千元
流动资产合计 {100+delta} {90-delta}
非流动资产合计 200 210
资产总计 300 300
流动负债合计 50 50
非流动负债合计 30 30
负债合计 80 80
所有者权益合计 220 220
'''
 assert (extract_balance_sheet_figures(1,text) is not None)==accepted
 assert extract_balance_sheet_figures(1,text.replace('千元','元')) is None


def test_inherited_source_survives_snapshot_and_human_review(monkeypatch):
 from test_manual_financial_snapshot import pages,COMPANY,arguments
 from src.manual_financial_snapshot import build_manual_financial_snapshot
 from src.financial_snapshot_review import build_financial_snapshot_review
 samples=pages()
 # Put the section declaration at the balance-sheet start; later statements
 # have no local unit. No synthetic page text is modified by the production rule.
 texts=[samples[0]['text'],
        '二、财务报表\n财务附注中报表的单位为：千元\n'+samples[2]['text'].replace('单位：元 币种：人民币',''),
        samples[1]['text'].replace('单位：元 币种：人民币',''),
        samples[3]['text'].replace('单位：元 币种：人民币','')]
 p=[dict(page_number=i+1,text=t) for i,t in enumerate(texts)]
 before=copy.deepcopy(p)
 monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *a,**kw:p)
 snapshot=build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())
 assert p==before
 assert snapshot['status']=='ready_for_human_review'
 assert all(m['source']['original_unit']=='千元' for m in snapshot['metrics'])
 assert snapshot['metrics'][0]['current_yuan']==168838102514.79*1000
 review=build_financial_snapshot_review(snapshot)
 assert all('PDF第2页' in m['source']['excerpt'] and m['decision']=='pending' for m in review['metrics'])
