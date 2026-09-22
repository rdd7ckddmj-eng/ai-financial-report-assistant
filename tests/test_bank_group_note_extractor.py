"""Synthetic group-column bank layout with separate EPS-note evidence."""
import pytest

from src.bank_statement_extractor import extract_bank_statements
from src.bank_group_note_extractor import UNIT, PARENT, ORDINARY
from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.financial_snapshot_review import build_financial_snapshot_review


def fixture_pages():
    def rows(items):
        return ''.join(f'{label}\n{value}\n{value}\n' for label, value in items)

    def table(title, items):
        suffix = '年12月31日' if '资产负债表' in title else '年度'
        return (f'{title}\n2025{suffix}\n{UNIT}\n本集团\n附注四\n'
                f'2025{suffix}\n2024{suffix}\n' + rows(items))

    income = [('利息收入',1000), ('利息支出','(200)'), ('利息净收入',800),
        ('手续费及佣金收入',100), ('手续费及佣金支出','(10)'), ('手续费及佣金净收入',90),
        ('投资收益',100), ('公允价值变动损益',10), ('汇兑损益',0),
        ('其他业务收入',0), ('资产处置损益',0), ('其他收益',0), ('营业收入合计',1000),
        ('税金及附加','(10)'), ('业务及管理费','(290)'), ('营业支出合计','(300)'),
        ('三、减值损失前营业利润',700), ('信用减值损失','(90)'), ('其他资产减值损失','(10)'),
        ('四、营业利润',600), ('加：营业外收入',10), ('减：营业外支出','(5)'),
        ('五、利润总额',605), ('减：所得税费用','(105)'), ('六、净利润',500),
        ('(一) 持续经营净利润',500), ('(二) 终止经营净利润','-')]
    cash = []
    for kind, incoming, outgoing in [('经营',1000,500), ('投资',100,300), ('筹资',100,150)]:
        cash += [(kind+'活动现金流入小计',incoming), (kind+'活动现金流出小计',f'({outgoing})'),
                 (kind+'活动'+('产生' if kind=='经营' else '使用')+'的现金流量净额',
                  str(incoming-outgoing) if incoming>=outgoing else f'({outgoing-incoming})')]
    cash += [('汇率变动对现金及现金等价物的影响','(10)'), ('现金及现金等价物净增加/(减少)额',240),
             ('加：年初现金及现金等价物余额',100), ('年末现金及现金等价物余额',340)]
    note = (f'财务报表附注(续)\n2025年度\n{UNIT}\n每股收益\n(a)\n基本每股收益具体计算如下：\n'
            '2025年度\n2024年度\n' + rows([(PARENT,500), ('减：母公司优先股宣告股息','(10)'),
                ('母公司永续债利息','(20)'), (ORDINARY,470)]))
    return [(1,table('合并资产负债表',[('资产总计',2000)])),
            (2,table('合并资产负债表(续)',[('负债合计',1500),('股东权益合计',500),('负债及股东权益总计',2000)])),
            (3,table('合并利润表',income)), (4,table('合并现金流量表',cash[:3])),
            (5,table('合并现金流量表(续)',cash[3:])+'\n银行现金流量表\n'), (10,note)]


def test_explicit_note_profit_and_per_metric_provenance_survive_snapshot_review():
    data = fixture_pages()
    result = extract_bank_statements(data,2025)
    assert result['income']['current_net_profit'] == 500  # not ordinary-profit 470
    assert result['cash']['current_operating_cash_flow'] == 500
    company = build_company_identity('000001','测试银行')
    candidate = build_candidate_report_result(company,
        dict(report_year=2025,published_date='2026-03-21',title='测试银行2025年年度报告',
             url='https://static.cninfo.com.cn/test.pdf'),b'%PDF-test',
        [dict(page_number=n,text=t) for n,t in data])
    assert candidate['status'] == 'ready_for_human_review'
    evidence = candidate['metric_evidence']['net_profit']
    assert evidence['pages'] == {'start':10,'end':10}
    assert PARENT in evidence['excerpt']
    assert evidence['statement'] == '每股收益附注（归母利润）'
    snapshot = build_on_demand_financial_snapshot(company,candidate)
    assert all(v is None for v in snapshot['ratios'].values())
    review = build_financial_snapshot_review(snapshot)
    profit = next(m for m in snapshot['metrics'] if m['key']=='net_profit')
    assert profit['statement'] == '每股收益附注（归母利润）'
    assert profit['pages'] == {'start':10,'end':10}
    reviewed = next(m for m in review['metrics'] if m['key']=='net_profit')
    assert reviewed['source']['pages'] == {'start':10,'end':10}
    assert all(m['decision']=='pending' for m in review['metrics'])


@pytest.mark.parametrize('index,old,new',[
    (5,PARENT,'归属于其他股东的本年净利润'),
    (5,'470\n470','470\n460'),
    (5,'500\n500','501\n502'),
    (5,'(10)\n(10)','10\n10'),
    (5,'2025年度\n2024年度','2024年度\n2025年度'),
    (5,'人民币百万元','人民币万元'),
    (1,'合并资产负债表(续)','银行资产负债表'),
    (4,'2025年度\n2024年度','2024年度\n2025年度'),
    (4,'人民币百万元','人民币万元'),
    (2,'(90)\n(90)','(80)\n(90)'),
    (4,'340\n340','340\n350'),
    (4,'(300)\n(300)','300\n300'),
])
def test_invalid_note_or_statement_never_produces_bank_amounts(index,old,new):
    data = fixture_pages()
    n,t = data[index]
    assert old in t
    data[index] = n,t.replace(old,new)
    result = extract_bank_statements(data,2025)
    assert all(result[key] is None for key in ('income','balance','cash'))


@pytest.mark.parametrize('mutation',['missing','duplicate','page_gap'])
def test_missing_ambiguous_note_and_nonconsecutive_statement_pages_reject(mutation):
    data = fixture_pages()
    if mutation=='missing':
        data.pop()
    elif mutation=='duplicate':
        data.append((11,data[-1][1]))
    else:
        data[4] = 6,data[4][1]
    result = extract_bank_statements(data,2025)
    assert all(result[key] is None for key in ('income','balance','cash'))


@pytest.mark.parametrize('break_prior_year', [False, True])
def test_alternative_cash_labels_preserve_opposite_year_signs(break_prior_year):
    data = fixture_pages()
    number, text = data[4]
    text = text.replace('筹资活动使用的现金流量净额\n(50)\n(50)',
                        '筹资活动(使用)/产生的现金流量净额\n(50)\n50')
    text = text.replace('筹资活动现金流出小计\n(150)\n(150)',
                        '筹资活动现金流出小计\n(150)\n(50)')
    text = text.replace('现金及现金等价物净增加/(减少)额\n240\n240',
                        '现金及现金等价物净(减少)/增加额\n240\n340')
    text = text.replace('年末现金及现金等价物余额\n340\n340',
                        '年末现金及现金等价物余额\n340\n' + ('450' if break_prior_year else '440'))
    data[4] = number, text
    result = extract_bank_statements(data, 2025)
    if break_prior_year:
        assert all(result[key] is None for key in ('income', 'balance', 'cash'))
    else:
        assert result['cash']['current_operating_cash_flow'] == 500
        assert result['cash']['previous_operating_cash_flow'] == 500
