"""Native report fixtures and hostile edits for the batch-14 bounded layouts."""
import json
from pathlib import Path

import pytest

from src.balance_sheet_extractor import find_balance_sheet_figures
from src.cash_flow_extractor import find_cash_flow_figures, _extract_chinese_row_pair, _normalise_lines, CHINESE_CASH_FLOW_LABELS
from src.statement_page_layout_recovery import recover_printed_statement_page_numbers


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/coverage14_balance_cash_native_pages.json').read_text())


def pages(code, start, end):
    report = next(item for item in FIXTURE if item['code'] == code)
    return [(p['page_number'], p['text']) for p in report['pages'] if start <= p['page_number'] <= end]


def replace(source, index, old, new):
    result = list(source)
    number, text = result[index]
    assert old in text
    result[index] = (number, text.replace(old, new, 1))
    return result


@pytest.mark.parametrize('code,start,end,assets,liabilities,offset', [
    ('600132',72,75,(10690758918.93,10968339719.39),(7830279049.20,8514681613.95),1),
    ('600233',104,107,(54177859555.90,48294063910.00),(18885011350.85,16085981310.78),3),
    ('002352',153,156,(216469037,213824213),(106144286,111488992),1),
])
def test_balance_totals_and_exact_printed_page_provenance(code,start,end,assets,liabilities,offset):
    source = pages(code,start,end)
    result = find_balance_sheet_figures(source)
    assert result is not None
    assert (result['current_total_assets'],result['previous_total_assets']) == assets
    assert (result['current_total_liabilities'],result['previous_total_liabilities']) == liabilities
    assert (result['page_number'],result['end_page_number']) == (start,end)
    recovery = result['layout_recoveries'][0]
    assert recovery['physical_to_printed_offset'] == offset
    assert [span['page_number'] for span in recovery['source_spans']] == list(range(start,end+1))
    for span in recovery['source_spans']:
        assert span['original_text'] in dict(source)[span['page_number']]
        assert int(span['original_text'].strip()) == span['printed_page_number']


@pytest.mark.parametrize('edit', ['wrong_printed','gap','wrong_period','extra_cell','missing_cell','duplicate_row','parent'])
def test_balance_printed_page_recovery_rejects_ambiguous_evidence(edit):
    source = pages('600233',104,107)
    if edit == 'wrong_printed':
        source = replace(source,0,'\n101\n','\n100\n')
    elif edit == 'gap':
        source[1] = (source[1][0]+1,source[1][1])
    elif edit == 'wrong_period':
        source = replace(source,1,'2024 年12 月31 日','2023 年12 月31 日')
    elif edit == 'extra_cell':
        source = replace(source,0,'15,238,484,896.00\n101','15,238,484,896.00\n777\n101')
    elif edit == 'missing_cell':
        source = replace(source,0,'15,893,391,841.15\n','')
    elif edit == 'duplicate_row':
        source = replace(source,0,'\n101\n','\n流动资产合计\n15,893,391,841.15\n15,238,484,896.00\n101\n')
    else:
        source = replace(source,2,'项目\n','母公司资产负债表\n项目\n')
    assert find_balance_sheet_figures(source) is None


def test_trailing_financial_integer_is_not_enough_to_infer_a_page_number():
    source = pages('600233',104,107)
    source = [(n,t.replace('2025 年度报告','')) for n,t in source]
    assert recover_printed_statement_page_numbers(source,'资产负债表') is None
    assert find_balance_sheet_figures(source) is None


def test_same_verified_footer_contract_available_to_income_parser():
    source = pages('002352',159,160)
    clean, recovery = recover_printed_statement_page_numbers(source,'利润表')
    assert [n for n,_ in clean] == [159,160]
    assert recovery['header_years'] == [2025,2024]
    assert recovery['source_spans'] == [
        dict(page_number=159,original_text='158\n',printed_page_number=158),
        dict(page_number=160,original_text='159\n',printed_page_number=159),
    ]
    assert clean[0][1] == source[0][1].removeprefix('158\n')
    assert clean[1][1] == source[1][1].removeprefix('159\n')


@pytest.mark.parametrize('old,new', [('159\n','157\n'),('2024年度','2023年度'),
                                  ('合并\n合并\n公司\n公司','公司\n公司\n合并\n合并')])
def test_income_footer_contract_rejects_wrong_page_or_period_or_scope(old,new):
    source = replace(pages('002352',159,160),1,old,new)
    assert recover_printed_statement_page_numbers(source,'利润表') is None


@pytest.mark.parametrize('edit', ['wrong_report_year','different_company','wrong_printed','wrong_period','wrong_title_year','missing_first_amount'])
def test_leading_footers_need_identity_period_and_whole_pairs(edit):
    source = pages('002352',153,156)
    if edit == 'wrong_report_year':
        source = replace(source,1,'2025年度报告','2024年度报告')
    elif edit == 'different_company':
        source = replace(source,1,'顺丰控股股份有限公司','另一公司股份有限公司')
    elif edit == 'wrong_printed':
        source = replace(source,0,'152\n','151\n')
    elif edit == 'wrong_period':
        source = replace(source,1,'2024年\n资产','2023年\n资产')
    elif edit == 'wrong_title_year':
        source = replace(source,0,'2025年12月31日合并资产负债表','2023年12月31日合并资产负债表')
    else:
        source = replace(source,0,'91,327,047\n','')
    assert find_balance_sheet_figures(source) is None


def test_sf_four_column_cash_selects_group_and_preserves_negative_flows():
    result = find_cash_flow_figures(pages('002352',161,162))
    assert result is not None
    assert (result['current_operating_cash_flow'],result['previous_operating_cash_flow']) == (27555275,32186373)
    assert (result['current_investing_cash_flow'],result['previous_investing_cash_flow']) == (-17327253,-12054744)
    assert (result['current_financing_cash_flow'],result['previous_financing_cash_flow']) == (-22935460,-27979113)
    assert (result['current_ending_cash'],result['previous_ending_cash']) == (19959631,32646055)
    assert result['unit'] == '人民币千元'
    assert result['layout_recoveries'][0]['kind'] == 'consecutive_printed_statement_page_numbers'


@pytest.mark.parametrize('old,new', [
    ('合并\n合并\n公司\n公司','公司\n公司\n合并\n合并'),
    ('2024年度\n2025年度','2023年度\n2025年度'),
    ('27,555,275\n',''),
    ('(11,083)\n','not-a-cell\n'),
    ('32,186,373\n','32,186,373\n777\n'),
    ('160\n','159\n'),
])
def test_sf_cash_no_parent_or_incomplete_column_fallback(old,new):
    source = replace(pages('002352',161,162),0,old,new)
    assert find_cash_flow_figures(source) is None


@pytest.mark.parametrize('code,start,end,current,previous', [
    ('600377',154,155,6761638748.35,6316202433.54),
    ('000027',144,146,11817010849.29,9611803315.56),
])
def test_explicit_note_layouts_have_exact_cash_evidence(code,start,end,current,previous):
    source = pages(code,start,end)
    result = find_cash_flow_figures(source)
    assert result is not None
    assert (result['current_operating_cash_flow'],result['previous_operating_cash_flow']) == (current,previous)
    assert (result['page_number'],result['end_page_number']) == (start,end)
    for recovery in result['layout_recoveries']:
        for span in recovery['source_spans']:
            assert span['original_text'] in dict(source)[span['page_number']]


@pytest.mark.parametrize('bad_note', ['五、62(1)ab','五、62(1)a说明','五、62(1)a 777','其他科目','五、62(1)a\n五、62(1)b'])
def test_lettered_note_does_not_skip_unknown_or_extra_cells(bad_note):
    source = replace(pages('600377',154,155),0,'五、62(1)a',bad_note)
    assert find_cash_flow_figures(source) is None


@pytest.mark.parametrize('old,new', [
    ('五、65(1) 11,817,010,849.29','五、65(1)BAD 11,817,010,849.29'),
    ('五、65(1) 11,817,010,849.29','五、65(1)11,817,010,849.29'),
    ('五、65(1) 11,817,010,849.29','五、65(1) 11,817,010,849.29 777'),
    ('五、65(1) 11,817,010,849.29','其他科目\n五、65(1) 11,817,010,849.29'),
    ('9,611,803,315.56',''),
    ('9,611,803,315.56','9,611,803,315.56\nNaN'),
    ('9,611,803,315.56','9,611,803,315.56\n123.1.2'),
    ('9,611,803,315.56','9,611,803,315.56\n无数据'),
])
def test_adjacent_note_requires_bounded_two_cells(old,new):
    source = replace(pages('000027',144,146),0,old,new)
    assert find_cash_flow_figures(source) is None


@pytest.mark.parametrize('code,start,end', [('600027',197,197),('600132',84,85)])
def test_actual_blank_exchange_rows_remain_missing(code,start,end):
    source = pages(code,start,end)
    assert find_cash_flow_figures(source) is None
    lines = _normalise_lines('\n'.join(text for _,text in source))
    assert _extract_chinese_row_pair(lines,CHINESE_CASH_FLOW_LABELS['exchange']) is None
