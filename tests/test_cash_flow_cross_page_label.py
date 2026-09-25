"""Unchanged native page edges and counterexamples for a split exchange row."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.cash_flow_extractor import extract_cash_flow_figures, find_cash_flow_figures

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/cash_flow_cross_page_label_2025.json').read_text())


def pages():
    return [(item['page_number'], item['text']) for item in FIXTURE['pages']]


def replace_on(source, number, old, new):
    index = next(i for i, (n, _) in enumerate(source) if n == number)
    assert source[index][1].count(old) == 1
    source[index] = (number, source[index][1].replace(old, new))
    return source


def test_original_native_edges_preserve_amounts_order_and_exact_source_spans():
    source = pages()
    before = deepcopy(source)
    result = find_cash_flow_figures(source)
    assert result is not None and source == before
    assert (result['page_number'], result['end_page_number'], result['unit']) == (92, 94, '元')
    assert (result['current_exchange_effect'], result['previous_exchange_effect']) == (-7876247.43, 9827145.77)
    assert (result['current_operating_cash_flow'], result['previous_operating_cash_flow']) == (1134512903.69, 1089909099.97)
    assert (result['current_net_cash_change'], result['previous_net_cash_change']) == (105251910.05, -302959888.07)
    assert (result['current_ending_cash'], result['previous_ending_cash']) == (1196600531.98, 1091348621.93)
    recovery, = result['layout_recoveries']
    assert recovery['kind'] == 'cross_page_exchange_label'
    assert recovery['header_years'] == [2025, 2024]
    assert recovery['physical_to_printed_offset'] == 1
    assert [span['page_number'] for span in recovery['source_spans']] == [93, 94]
    for span in recovery['source_spans']:
        assert span['original_text'] in dict(source)[span['page_number']]
    assert '2025 年度报告全文' in recovery['source_spans'][1]['original_text']
    assert '93' in recovery['source_spans'][1]['original_text']


@pytest.mark.parametrize('number,old,new', [
    (92, '2025 年度 \n2024 年度', '2024 年度 \n2025 年度'),
    (92, '2025 年度 \n2024 年度', '2025 年度 \n2023 年度'),
    (92, '2025 年度 \n2024 年度', '2025 年度 \n2024 年度\n2023 年度'),
    (92, '项目 \n2025', '项目 附注 \n2025'),
    (92, '合并现金流量表', '合并及公司现金流量表'),
    (92, '单位：元', '单位：美元'),
    (92, '单位：元', '单位：元\n单位：千元'),
    (92, '单位：元', '单位不详'),
    (93, '2025 年度报告全文', '2024 年度报告全文'),
    (94, '浙江伟星实业发展股份有限公司', '其他股份有限公司'),
    (94, '全文 \n93', '全文 \n94'),
    (94, '全文 \n93', '全文 \n0'),
    (93, '-7,876,247.43 \n9,827,145.77', '9,827,145.77 \n-7,876,247.43'),
    (93, '-7,876,247.43 \n9,827,145.77', '-7,876,247.43'),
    (93, '-7,876,247.43 \n9,827,145.77', '-7,876,247.43\n99\n9,827,145.77'),
    (93, '-7,876,247.43 \n9,827,145.77', '-7,876,247.43\nNaN\n9,827,145.77'),
    (93, '-7,876,247.43', '-78,76,247.43'),
    (93, '-7,876,247.43', '-7,876,247.43 100'),
    (93, '9,827,145.77', '9,827,145.77\n无关科目'),
    (93, '汇率变动对现金及现金等价物的', '汇率变动对现金等价物的'),
    (94, '影响 \n五、', '影响额 \n五、'),
    (94, '影响 \n五、', '五、'),
    (94, '影响 \n五、', '影响\n影响 \n五、'),
    (94, '影响 \n五、', '影响\n99 \n五、'),
    (94, '影响 \n五、', '母公司现金流量表\n影响 \n五、'),
    (94, '影响 \n五、', '无关科目\n影响 \n五、'),
    (94, '五、现金及现金等价物净增加额', '其他现金流项目'),
    (94, '影响 \n五、', '影响\n四、汇率变动对现金及现金等价物的影响\n-7,876,247.43\n9,827,145.77\n五、'),
    (94, '影响 \n五、', '影响\n经营活动产生的现金流量净额\n1,134,512,903.69\n1,089,909,099.97\n五、'),
])
def test_recovery_rejects_ambiguous_edges_header_values_and_boundaries(number, old, new):
    assert find_cash_flow_figures(replace_on(pages(), number, old, new)) is None


@pytest.mark.parametrize('physical', [91, 93, 95, 194])
def test_nonconsecutive_physical_pages_do_not_join(physical):
    source = pages()
    source[-1] = (physical, source[-1][1])
    assert find_cash_flow_figures(source) is None


def test_text_concatenation_without_original_physical_boundaries_cannot_recover():
    source = pages()
    assert extract_cash_flow_figures(92, '\n'.join(text for _, text in source)) is None


def test_invalid_boundary_is_not_authorized_by_two_reconciled_cash_equations():
    source = replace_on(pages(), 93, '-7,876,247.43', '-7,876,247.42')
    source = replace_on(source, 94, '105,251,910.05', '105,251,910.06')
    source = replace_on(source, 94, '1,196,600,531.98', '1,196,600,531.99')
    source = replace_on(source, 94, '影响 \n五、', '影响\n未知科目 \n五、')
    assert find_cash_flow_figures(source) is None


def test_same_company_without_real_stock_code_is_not_hardcoded():
    source = [(n, text.replace('浙江伟星实业发展股份有限公司', '另一家示例股份有限公司')) for n, text in pages()]
    assert find_cash_flow_figures(source) is not None


def test_wrapped_duplicate_complete_exchange_row_cannot_be_treated_as_missing():
    # A wrapped competing row must be counted by the same label-span rule as
    # ordinary extraction, rather than hidden by a single-line substring test.
    source = replace_on(pages(), 93, '三、筹资活动产生的现金流量：',
        '四、汇率变动对现金及\n现金等价物的影响\n1.00\n2.00\n三、筹资活动产生的现金流量：')
    assert find_cash_flow_figures(source) is None
