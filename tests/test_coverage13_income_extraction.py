"""Preserve explicit note references, column roles and continuation pages."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation

SAMPLES = json.loads((Path(__file__).parent / 'fixtures/coverage13_income_extraction.json').read_text())


def pages(code):
    return deepcopy(next(s['pages'] for s in SAMPLES if s['code'] == code))


@pytest.mark.parametrize('code,values,span', [
    ('600085', (17256185123.82,18597281604.93,1189374356.88,1526274925.98), (76,77)),
    ('600600', (32473493664,32137830111,4588101137,4344983858), (72,72)),
    ('600089', (97226538368.58,97821953080.40,5954294958.25,4143924869.81), (140,142)),
])
def test_original_values_column_roles_and_bounded_pages(code,values,span):
    original = pages(code)
    before = deepcopy(original)
    result = find_income_statement_figures(original)
    assert tuple(result[k] for k in ('current_revenue','previous_revenue','current_net_profit','previous_net_profit')) == values
    assert (result['page_number'],result['end_page_number']) == span
    assert original == before


@pytest.mark.parametrize('old,new', [
    ('八、七、61', '八、七、61、62'),
    ('八、七、61', '八、七、'),
    ('17,256,185,123.82', '17,256,185,123.82\n999'),
    ('17,256,185,123.82', '17,256,18,123.82'),
    ('17,256,185,123.82', 'NULL'),
    ('18,597,281,604.93', '18,597,281,604.93\n/'),
    ('18,597,281,604.93', '18,597,281,604.93\n?999'),
    ('18,597,281,604.93', '18,597,281,604.93\n999元'),
    ('18,597,281,604.93', '18,597,281,604.93\n人民币999元'),
    ('18,597,281,604.93\n利息收入', '利息收入\n18,597,281,604.93'),
    ('2025 年度\n2024 年度', '2024 年度\n2025 年度'),
    ('币种：人民币', '币种：美元'),
])
def test_double_chapter_note_never_skips_malformed_or_missing_cells(old,new):
    source=pages('600085');assert old in source[0][1]
    source[0][1]=source[0][1].replace(old,new)
    assert find_income_statement_figures(source) is None


@pytest.mark.parametrize('old,new', [
    ('(五)39,(十七)5', '(五)39,(十七)'),
    ('(五)39,(十七)5', '(五)39,(十七)5,999'),
    ('32,473,493,664', '32,473,493,664\n999'),
    ('32,473,493,664', '32,473,49,664'),
    ('32,473,493,664', '/'),
    ('32,473,493,664', 'N/A'),
    ('24,560,177,793', '24,560,177,793\nNaN'),
    ('24,560,177,793', '24,560,177,793\nnan'),
    ('24,560,177,793', '24,560,177,793\nNONE'),
    ('24,560,177,793', '24,560,177,793\n?999'),
    ('24,560,177,793', '24,560,177,793\n999元'),
    ('24,560,177,793', '24,560,177,793\n人民币999元'),
    ('32,473,493,664', ''),
    ('2025 年度 \n母公司', '2025 年度 \n合并'),
    ('2024 年度 \n母公司', '2026 年度 \n母公司'),
    ('人民币元', '美元'),
])
def test_combined_revenue_requires_exact_four_columns_and_two_period_roles(old,new):
    source=pages('600600');assert old in source[0][1]
    source[0][1]=source[0][1].replace(old,new)
    assert find_income_statement_figures(source) is None


@pytest.mark.parametrize('damage',['missing_page','wrong_number','wrong_year','middle_current_year','middle_prior_year','missing_header','parent','missing_minority','malformed_amount','mismatch'])
def test_continuation_cannot_borrow_another_statement_or_make_bad_arithmetic_pass(damage):
    source=pages('600089')
    if damage=='missing_page': source.pop(2)
    elif damage=='wrong_number': source[2][0]=144
    elif damage=='wrong_year': source[2][1]=source[2][1].replace('2025 年度','2026 年度')
    elif damage=='middle_current_year': source[1][1]=source[1][1].replace('2025 年度','2026 年度')
    elif damage=='middle_prior_year': source[1][1]=source[1][1].replace('2024 年度','2023 年度')
    elif damage=='missing_header': source[2][1]=source[2][1].replace('项目\n附注\n','')
    elif damage=='parent': source[2][1]=source[2][1].replace('项目\n附注\n','母公司利润表\n项目\n附注\n',1)
    elif damage=='missing_minority': source[2][1]=source[2][1].replace('2.少数股东损益','2.其他项目')
    elif damage=='malformed_amount': source[2][1]=source[2][1].replace('46,688,454.00','46,68,454.00')
    elif damage=='mismatch': source[2][1]=source[2][1].replace('46,688,454.00','46,688,456.00')
    result=find_income_statement_figures(source)
    assert not check_general_income_reconciliation(source,result,report_year=2025)['passed']
