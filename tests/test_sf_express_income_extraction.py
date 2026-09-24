"""Actual SF income columns keep company 不适用 cells out of group amounts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.financial_statement_extractor import find_income_statement_figures


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/sf_express_combined_income_2025.json').read_text())
HEADER = '项目\n附注\n2025年度\n2024年度\n2025年度\n2024年度\n合并\n合并\n公司\n公司'
PROFIT = '归属于母公司股东的净利润\n11,117,216\n10,170,427\n不适用\n不适用'
REVENUE = '一、营业收入\n四(42)\n308,226,647\n284,420,059\n–\n–'


def source():
    return [(p['page_number'], p['text']) for p in deepcopy(FIXTURE['pages'])]


def replace(pages, number, old, new):
    assert any(n == number and old in text for n, text in pages)
    return [(n, text.replace(old, new) if n == number else text) for n, text in pages]


def test_real_two_page_statement_selects_only_consolidated_amounts_and_preserves_source():
    pages = source(); original = deepcopy(pages)
    figures = find_income_statement_figures(pages)
    assert figures == dict(current_revenue=308226647.0, previous_revenue=284420059.0,
                          current_net_profit=11117216.0, previous_net_profit=10170427.0,
                          unit='人民币千元', page_number=159, end_page_number=160,
                          current_period_weeks=None, previous_period_weeks=None)
    assert pages == original
    assert FIXTURE['sha256'] == '240c05b80783bc350ba9fedf22487bc4ed0e370ccd3943ed6c2736de06050ae2'
    assert FIXTURE['source_url'] == 'https://static.cninfo.com.cn/finalpage/2026-03-31/1225057387.PDF'
    assert FIXTURE['visual_checked_physical_pages'] == [159, 160]
    assert '11,684,811\n10,218,845\n2,485,583\n5,031,094' in pages[1][1]
    assert '不适用\n不适用\n少数股东损益' in pages[1][1]


@pytest.mark.parametrize('page', [159, 160])
@pytest.mark.parametrize('header', [
    '',
    HEADER.replace('项目', '未知项目'),
    HEADER.replace('2025年度', '2026年度', 1),
    HEADER.replace('2024年度', '2023年度', 1),
    HEADER.replace('2025年度\n2024年度', '2024年度\n2025年度'),
    HEADER.replace('合并\n合并\n公司\n公司', '合并\n公司\n合并\n公司'),
    HEADER.replace('合并\n合并\n公司\n公司', '公司\n公司\n合并\n合并'),
    HEADER.replace('公司\n公司', '母公司\n母公司'),
    HEADER.replace('附注\n', ''),
    HEADER.replace('2024年度\n合并', '2024年度\n2023年度\n合并'),
])
def test_unknown_order_or_inconsistent_continuation_header_is_not_inferred(page, header):
    assert find_income_statement_figures(replace(source(), page, HEADER, header)) is None


def test_two_headers_cannot_both_belong_to_the_first_page():
    pages = replace(source(), 159, HEADER, HEADER + '\n' + HEADER)
    pages = replace(pages, 160, HEADER, '')
    assert find_income_statement_figures(pages) is None


@pytest.mark.parametrize('cells', [
    '11,117,216\n10,170,427',
    '11,117,216\n10,170,427\n不适用',
    '11,117,216\n10,170,427\n不适用\n不适用\n777',
    '11,117,216\n10,170,427\n不适用\n不适用\n777,,777',
    '11,117,216\n10,170,427\n不适用\n不适用\n未知说明',
    '11,117,216\n10,170,427\n不适用\n不适用\n四(54)',
    '11,117,216\n10,170,427\n/\n/',
    '11,117,216\n10,170,427\nNaN\nNaN',
    '11,117,216\n10,170,427\n0\n不适用',
    '11,117,216\n不适用\n10,170,427\n不适用',
    '不适用\n不适用\n11,117,216\n10,170,427',
    '11,117,216\n不适用\n不适用',
    '11,117,216x\n10,170,427\n不适用\n不适用',
])
def test_exact_two_numbers_and_two_explicit_company_na_cells_are_required(cells):
    changed = replace(source(), 160, PROFIT, PROFIT.split('\n')[0] + '\n' + cells)
    assert find_income_statement_figures(changed) is None


@pytest.mark.parametrize('old,new', [
    ('308,226,647\n284,420,059\n–\n–', '308,226,647\n284,420,059\n–'),
    ('308,226,647\n284,420,059\n–\n–', '308,226,647\n284,420,059\n–\n–\n777'),
    ('308,226,647\n284,420,059\n–\n–', '308,226,647\n284,420,059\n–\n–\nNAN'),
    ('308,226,647\n284,420,059\n–\n–', '308,226,647\n284,420,059\n不适用\n不适用'),
    ('四(42)', '四(42)\n777'),
    ('四(42)', '未知附注'),
    ('四(42)', '四(42)\n四(43)'),
    ('284,420,059', '284,,420,059'),
    ('–\n–', '–\n10000000000000000000000000000'),
])
def test_revenue_row_cannot_hide_extra_cells_notes_or_unknown_text(old, new):
    changed = replace(source(), 159, REVENUE, REVENUE.replace(old, new))
    assert find_income_statement_figures(changed) is None


@pytest.mark.parametrize('damage', ['duplicate_profit', 'duplicate_revenue', 'missing_minority_boundary',
                                  'parent_before_profit', 'missing_first', 'missing_second',
                                  'wrong_page', 'duplicate_page', 'unit_conflict'])
def test_duplicates_missing_pages_and_parent_table_boundaries_remain_closed(damage):
    pages = source()
    if damage == 'duplicate_profit': pages = replace(pages, 160, PROFIT, PROFIT + '\n' + PROFIT)
    elif damage == 'duplicate_revenue': pages = replace(pages, 159, REVENUE, REVENUE + '\n' + REVENUE)
    elif damage == 'missing_minority_boundary': pages = replace(pages, 160, '少数股东损益', '未知归属项目')
    elif damage == 'parent_before_profit': pages = replace(pages, 160, PROFIT, '母公司利润表\n' + PROFIT)
    elif damage == 'missing_first': pages = pages[1:]
    elif damage == 'missing_second': pages = pages[:1]
    elif damage == 'wrong_page': pages[1] = (161, pages[1][1])
    elif damage == 'duplicate_page': pages[1] = (159, pages[1][1])
    elif damage == 'unit_conflict': pages = replace(pages, 160, '人民币千元', '人民币元')
    assert find_income_statement_figures(pages) is None


def test_company_name_is_not_a_production_match_key_and_negative_profit_keeps_sign():
    pages = [(n, t.replace('顺丰控股股份有限公司', '示例公司')) for n, t in source()]
    pages = replace(pages, 160, '11,117,216\n10,170,427', '(11,117,216)\n(10,170,427)')
    figures = find_income_statement_figures(pages)
    assert figures['current_net_profit'] == -11117216
    assert figures['previous_net_profit'] == -10170427
