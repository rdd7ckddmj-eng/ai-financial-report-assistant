import pytest
from src.bank_statement_extractor import extract_bank_statements
from src.audited_company_onboarding import build_candidate_report_result
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.china_stock import build_company_identity


def pages():
    def table(title, rows):
        suffix='年12月31日' if '资产负债表' in title else '年度'
        head=f'{title}\n2025 年度\n人民币百万元\n附注五\n2025{suffix}\n2024{suffix}\n'
        return head+''.join(f'{label}\n{v}\n{v}\n' for label,v in rows)
    income=[('一、营业收入',1000),('利息净收入',800),('利息收入',1000),('利息支出','(200)'),
        ('手续费及佣金净收入',90),('手续费及佣金收入',100),('手续费及佣金支出','(10)'),
        ('投资收益',100),('其他收益',10),('公允价值变动损益',0),('汇兑损益',0),
        ('其他业务收入',0),('资产处置收益',0),('二、营业支出','(400)'),
        ('税金及附加','(10)'),('业务及管理费','(290)'),('信用减值损失','(90)'),('其他业务成本','(10)'),
        ('三、营业利润',600),('营业外收入',10),('营业外支出','(5)'),('四、利润总额',605),
        ('所得税费用','(105)'),('五、净利润',500),('其中：归属于母公司股东\n的净利润',490),('少数股东损益',10)]
    cash=[]
    for kind,inc,out in [('经营',1000,500),('投资',100,300),('筹资',100,150)]:
        cash += [(kind+'活动现金流入小计',inc),(kind+'活动现金流出小计',out),
                 (kind+'活动产生的现金流量净额',str(inc-out) if inc>=out else f'({out-inc})')]
    cash += [('汇率变动对现金及现金等价物的影响额','(10)'),('本年现金及现金等价物净增加额',240),
             ('加：年初现金及现金等价物余额',100),('年末现金及现金等价物余额',340)]
    return [(1,table('合并资产负债表',[('资产总计',2000)])),
            (2,table('合并资产负债表（续）',[('负债合计',1500),('股东权益合计',500),
              ('归属于母公司股东的权益',480),('少数股东权益',20),('负债及股东权益总计',2000)])),
            (3,table('合并利润表',income)),(4,table('合并现金流量表',cash)),
            (5,'测试公司\n公司资产负债表\n2025 年度\n人民币百万元\n附注十四\n资产总计\n999\n999')]


def test_unsigned_outflows_and_wrapped_parent_profit_preserve_evidence():
    result=extract_bank_statements(pages(),2025)
    assert result['cash']['current_operating_cash_flow']==500
    assert result['cash']['end_page_number']==4
    assert result['income']['current_net_profit']==490
    company=build_company_identity('002142','测试银行')
    candidate=build_candidate_report_result(company,dict(report_year=2025,published_date='2026-04-25',
        title='测试银行2025年年度报告',url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',
        [dict(page_number=n,text=t) for n,t in pages()])
    snapshot=build_on_demand_financial_snapshot(company,candidate)
    assert snapshot['status']=='ready_for_human_review'
    assert all(v is None for v in snapshot['ratios'].values())
    profit=next(m for m in snapshot['metrics'] if m['key']=='net_profit')
    assert '归属于母公司股东' in profit['source']['excerpt']
    assert profit['pages']=={'start':3,'end':3}


@pytest.mark.parametrize('index,old,new',[
    (3,'现金流出小计\n500','现金流出小计\n(500)'),
    (3,'340\n340','340\n350'),
    (3,'附注五\n2025年度\n2024年度','附注五\n2024年度\n2025年度'),
    (3,'人民币百万元','人民币万元'),
    (2,'490\n490','490\n480'),
    (2,'(90)\n(90)','(80)\n(90)'),
    (1,'480\n480','470\n480'),
    (1,'股东权益合计\n500\n500','股东权益合计'),
    (1,'合并资产负债表（续）','公司资产负债表'),
    (1,'2024年12月31日','2023年12月31日'),
])
def test_invalid_unsigned_layout_fails_closed(index,old,new):
    data=pages();n,t=data[index];assert old in t;data[index]=(n,t.replace(old,new))
    result=extract_bank_statements(data,2025)
    assert all(result[k] is None for k in ('income','balance','cash'))


def test_alternative_financing_label_keeps_unsigned_cash_formula():
    data=[(n,t.replace('筹资活动产生的现金流量净额','筹资活动产生/(使用)的现金流量净额')) for n,t in pages()]
    result=extract_bank_statements(data,2025)
    assert result['cash']['current_operating_cash_flow']==500
