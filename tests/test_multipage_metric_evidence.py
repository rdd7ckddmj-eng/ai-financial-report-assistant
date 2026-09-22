"""Regression for real-report continuation pages; values below are synthetic."""
from src.audited_company_onboarding import _build_metric_evidence
from src.audited_company_onboarding import _compact_metric_excerpt


def evidence(pages, end=12):
    return _build_metric_evidence(
        figures_by_statement={
            'income_statement': dict(page_number=10, end_page_number=end,
                current_revenue=1000, previous_revenue=900,
                current_net_profit=120, previous_net_profit=110, unit='元'),
            'balance_sheet': None, 'cash_flow_statement': None,
        }, page_text_by_number=pages)


def test_continuation_prefers_exact_revenue_and_parent_profit():
    result = evidence({
        10: '合并利润表\n单位：元\n一、营业总收入\n1050\n950',
        11: '其中：营业收入\n1000\n900\n五、净利润\n130\n115',
        12: '归属于母公司股东的净利润\n120\n110',
        13: '母公司利润表\n营业收入\n800\n700',
    })
    revenue = result['revenue']
    profit = result['net_profit']
    assert revenue['excerpt'].startswith('其中：营业收入')
    assert '1000' in revenue['excerpt']
    assert profit['excerpt'].startswith('归属于母公司股东的净利润')
    assert '120' in profit['excerpt']
    assert profit['accounting_basis'] == '合并口径'
    assert profit['pages'] == {'start': 10, 'end': 12}
    assert '800' not in revenue['excerpt']


def test_wrapped_parent_label_on_later_page_is_preserved():
    result = evidence({10: '合并利润表', 11: '其他项目',
        12: '1.归属于母公司股东的净\n利润\n120\n110'})
    assert result['net_profit']['excerpt_status'] == 'captured'
    assert result['net_profit']['excerpt'].startswith('1.归属于')
    assert '120' in result['net_profit']['excerpt']


def test_never_search_beyond_detected_statement_range():
    result = evidence({10: '合并利润表',
        13: '归属于母公司股东的净利润\n120\n110'})
    assert result['net_profit']['excerpt'] == ''
    assert result['net_profit']['excerpt_status'] == 'not_found'


def test_parent_table_starting_on_same_last_page_is_excluded():
    result = evidence({10: '合并利润表\n营业总收入\n1000\n900',
        12: '五、净利润\n120\n110\n4、母公司利润表\n营业收入\n800\n700'})
    assert result['revenue']['excerpt'].startswith('营业总收入')
    assert '800' not in result['revenue']['excerpt']


def test_total_liabilities_excerpt_does_not_match_current_subtotal():
    excerpt, status = _compact_metric_excerpt(
        '流动负债合计\n60\n50\n非流动负债合计\n40\n30\n负债合计\n100\n80',
        ('负债合计', '总负债', 'Total liabilities'))
    assert status == 'captured'
    assert excerpt == '负债合计 ｜ 100 ｜ 80'
