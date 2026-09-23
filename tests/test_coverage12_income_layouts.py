"""Three official layouts, with damaged rows kept outside publishable values."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.financial_statement_extractor import find_income_statement_figures
from src.general_income_reconciliation import check_general_income_reconciliation
from src.statement_evidence_rules import extract_statement_unit

SAMPLES = {s['code']: s for s in json.loads(
    (Path(__file__).parent/'fixtures/coverage12_income_layouts.json').read_text())}
EXPECTED = {
    '000063': (133895460,121298752,5617745,8424792,'人民币千元'),
    '000625': (163999803875.87,159733034213.25,4075223181.54,7321363897.24,'人民币元'),
    '600547': (104287391583.12,82517993538.30,4739393120.72,2951551189.32,'人民币元'),
}


def pages(code, old=None, new=None):
    source = [(p['page_number'],p['text']) for p in SAMPLES[code]['pages']]
    if old is not None:
        assert sum(text.count(old) for _,text in source) == 1
        source = [(n,t.replace(old,new,1)) for n,t in source]
    return source


@pytest.mark.parametrize('code', EXPECTED)
def test_real_rows_two_period_amounts_and_arithmetic_preserve_original_text(code):
    source = pages(code); before = deepcopy(source)
    figures = find_income_statement_figures(source)
    assert tuple(figures[k] for k in ('current_revenue','previous_revenue',
        'current_net_profit','previous_net_profit','unit')) == EXPECTED[code]
    result = check_general_income_reconciliation(source,figures,report_year=2025)
    assert result['status'] == 'passed'
    assert all(c['passed'] for c in result['checks'])
    assert source == before
    assert result['header_years'] == [2025,2024]


@pytest.mark.parametrize('replacement', ('按持续经营分类','按所有权归属分类\n六、其他综合收益的税后净额',''))
def test_short_ordinary_shareholder_label_requires_profit_ownership_section(replacement):
    assert find_income_statement_figures(pages('000063','按所有权归属分类',replacement)) is None


def test_ordinary_shareholder_profit_cannot_replace_consolidated_profit():
    source = pages('000063','5,617,745','5,565,073')
    figures = find_income_statement_figures(source)
    assert figures['current_net_profit'] == 5565073
    result = check_general_income_reconciliation(source,figures,report_year=2025)
    assert result['status'] == 'mismatch'


@pytest.mark.parametrize('code,old,new', (
    ('000625','本期金额','上期金额'),
    ('000625','2025 年度','2024 年度'),
    ('600547','2025 年度','2024 年度'),
))
def test_inconsistent_year_columns_do_not_pass(code,old,new):
    source = pages(code,old,new)
    figures = find_income_statement_figures(source)
    assert check_general_income_reconciliation(source,figures,report_year=2025)['status'] != 'passed'


@pytest.mark.parametrize('code,old,new', (
    ('000625','其中：营业收入 \n（四十九）','其中：营业收入 \n（未知）'),
    ('000625','（四十九） \n163,999,803,875.87','（四十九） \n163,,999,803,875.87'),
    ('600547','其中：营业收入\n七．61','其中：营业收入\n七．61\n999'),
    ('600547','其中：营业收入\n七．61','其中：营业收入\n七．61\nNaN'),
))
def test_bad_note_or_amount_does_not_fall_back_to_total_revenue(code,old,new):
    source = pages(code,old,new)
    assert find_income_statement_figures(source) is None


@pytest.mark.parametrize('unit', ('元','千元','万元','百万元'))
def test_exact_all_amounts_unit_declaration(unit):
    assert extract_statement_unit([f'（除特别注明外，金额单位均为人民币{unit}）']) == '人民币'+unit


@pytest.mark.parametrize('other', ('单位：人民币万元','单位均为美元','币种：港元','金额单位为欧元'))
def test_all_amounts_unit_declaration_cannot_override_conflicting_currency_or_scale(other):
    assert extract_statement_unit(['（除特别注明外，金额单位均为人民币元）',other]) == ''
