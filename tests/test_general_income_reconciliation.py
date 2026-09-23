"""Two mandatory equations require complete, correctly scoped source evidence."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.general_income_reconciliation import check_general_income_reconciliation


SAMPLES = json.loads((Path(__file__).parent / 'fixtures/general_income_reconciliation_real.json').read_text())
TABLE = '''合并利润表
单位：人民币元
项目 附注
2025年度
2024年度
营业收入 1000.00 900.00
利润总额
100.10
90.20
减：所得税费用
20.01
18.02
净利润
80.09
72.18
归属于母公司股东的净利润
70.01
62.12
少数股东损益
10.08
10.06
六、其他综合收益的税后净额
'''


def figures(**kwargs):
    return dict(unit='人民币元', page_number=10, end_page_number=10,
                current_net_profit='70.01', previous_net_profit='62.12', **kwargs)


def check(text=TABLE, income=None, report_year=2025):
    return check_general_income_reconciliation([(10, text)], income or figures(), report_year=report_year)


def source(code):
    return deepcopy(next(sample for sample in SAMPLES if sample['code'] == code))


def check_source(sample):
    return check_general_income_reconciliation(sample['pages'], sample['income'], report_year=sample['year'])


@pytest.mark.parametrize('sample', SAMPLES, ids=lambda sample: sample['code'])
def test_fifteen_official_source_windows_have_two_period_arithmetic_evidence(sample):
    result = check_source(sample)
    assert result['status'] == 'passed'
    assert len(sample['pdf_sha256']) == 64
    assert sample['source_url'].startswith('https://')
    assert result['unit'] == sample['income']['unit']
    assert result['header_years'] in ([sample['year'], sample['year'] - 1], None)
    assert {'profit_after_tax', 'profit_attribution', 'selected_attributable_profit'} <= {c['key'] for c in result['checks']}
    for item in result['checks']:
        for period in ('current', 'previous'):
            values = item[period]
            assert values['passed']
            assert Decimal(values['left']) - Decimal(values['right']) == Decimal(values['difference'])
    assert all(row['excerpt'] and row['pages']['start'] >= sample['income']['page_number']
               for row in result['evidence'].values())


def test_decimal_math_and_explicit_check_contract():
    result = check()
    assert result['passed'] and result['header_years'] == [2025, 2024]
    assert result['checks'][0]['current'] == dict(left='80.09', right='80.09', difference='0.00', passed=True)
    assert result['checks'][0]['previous'] == dict(left='72.18', right='72.18', difference='0.00', passed=True)
    assert result['checks'][1]['current']['difference'] == '0.00'
    assert result['pages'] == dict(start=10, end=10)


@pytest.mark.parametrize('old,new', [('100.10', '100.12'), ('90.20', '90.22'),
    ('20.01', '20.03'), ('18.02', '18.04'), ('80.09', '80.11'), ('72.18', '72.20'),
    ('70.01', '70.03'), ('62.12', '62.14'), ('10.08', '10.10'), ('10.06', '10.08')])
def test_a_wrong_cell_in_either_year_is_a_demonstrated_mismatch(old, new):
    result = check(TABLE.replace('\n' + old + '\n', '\n' + new + '\n', 1))
    assert result['status'] == 'mismatch'
    assert any(period['difference'] is not None and not period['passed']
               for item in result['checks'] for period in (item['current'], item['previous']))


@pytest.mark.parametrize('old', ['利润总额\n100.10\n90.20\n', '减：所得税费用\n20.01\n18.02\n',
    '净利润\n80.09\n72.18\n', '归属于母公司股东的净利润\n70.01\n62.12\n', '少数股东损益\n10.08\n10.06\n'])
def test_missing_required_rows_are_not_zero_or_other_profit_aliases(old):
    result = check(TABLE.replace(old, '', 1))
    assert result['status'] == 'missing_evidence' and not result['passed']


def test_missing_tax_and_incorrect_attribution_still_reports_demonstrated_mismatch():
    text = TABLE.replace('减：所得税费用\n20.01\n18.02\n', '').replace('\n10.08\n', '\n20.08\n')
    assert check(text)['status'] == 'mismatch'


@pytest.mark.parametrize('extra', ['777,,777', '777.77.7', '777xyz', '不适用', 'N/A', 'NaN', '+777', '.777', '777'])
def test_extra_malformed_or_missing_numeric_cells_cannot_end_a_row_silently(extra):
    text = TABLE.replace('10.08\n10.06\n', f'10.08\n10.06\n{extra}\n')
    result = check(text)
    assert result['status'] == 'missing_evidence'
    assert result['evidence']['minority_profit']['status'] == 'missing_or_ambiguous'


@pytest.mark.parametrize('bad', ['10,,080', '10.08.0', '(10.08', '10.08)', '10.08foo', 'None'])
def test_bad_amount_in_an_expected_cell_is_missing_evidence(bad):
    assert check(TABLE.replace('\n10.08\n', f'\n{bad}\n'))['status'] == 'missing_evidence'


@pytest.mark.parametrize('header', ['2024年度\n2025年度', '2025年度\n2024年度\n2023年度', '',
    '2025年度', '2025年度\n2024年度\n上期发生额', '上年发生额\n本年发生额'])
def test_ambiguous_missing_extra_or_reversed_period_headers_are_rejected(header):
    result = check(TABLE.replace('2025年度\n2024年度', header))
    assert result['status'] == 'missing_evidence'


@pytest.mark.parametrize('header', ['项目 2025年度 2024年度', '项目 附注 2025年度 2024年度',
    '项目\n本年发生额\n上年发生额', '项目 本期发生额 上期发生额', '项目\n2025年度\n2024年度（重\n述）'])
def test_unambiguous_inline_relative_and_wrapped_restatement_headers(header):
    result = check(TABLE.replace('项目 附注\n2025年度\n2024年度', header))
    assert result['status'] == 'passed'


def test_selected_annual_report_year_must_match_numeric_columns():
    result = check(report_year=2024)
    assert result['status'] == 'missing_evidence'
    assert result['header_years'] == [2025, 2024]
    assert '所选年报年度不一致' in result['note']


@pytest.mark.parametrize('annotation', ['（重', '（未经核实）', '（重\n述'])
def test_unknown_or_incomplete_comparative_year_annotation_is_rejected(annotation):
    assert check(TABLE.replace('2024年度', '2024年度' + annotation))['status'] == 'missing_evidence'


def test_only_complete_standalone_sign_annotation_can_precede_values():
    annotated = TABLE.replace('归属于母公司股东的净利润\n', '归属于母公司股东的净利润\n（净亏损以“-”号填列）\n')
    assert check(annotated)['passed']
    assert not check(annotated.replace('（净亏损以“-”号填列）', '不包括未披露项目'))['passed']
    assert not check(annotated.replace('（净亏损以“-”号填列）', '（净亏损以“-”号填列'))['passed']


def test_complete_loss_synonyms_preserve_negative_amounts_and_column_validation():
    # Vanke 2025 uses these exact short label qualifiers rather than a full
    # “以负号填列” sentence. The qualifier cannot supply or change any amount.
    text = TABLE.replace('利润总额\n', '利润总额(亏损总额)\n')
    text = text.replace('净利润\n', '净利润(净亏损)\n')
    text = text.replace('100.10\n90.20', '(60.08)\n(54.16)')
    text = text.replace('80.09\n72.18', '(80.09)\n(72.18)')
    text = text.replace('70.01\n62.12', '(70.01)\n(62.12)')
    text = text.replace('10.08\n10.06', '(10.08)\n(10.06)')
    income = figures(); income.update(current_net_profit='-70.01', previous_net_profit='-62.12')
    assert check(text, income)['passed']
    assert check(text.replace('(净亏损)', '(含其他未列项目)'), income)['status'] == 'missing_evidence'
    assert check(text.replace('(54.16)\n', '(54.16)\n1.00\n'), income)['status'] == 'missing_evidence'
    assert check(text.replace('(净亏损)', '(净亏损'), income)['status'] == 'missing_evidence'


def test_duplicate_group_total_is_ambiguous_and_parent_table_is_not_borrowed():
    assert check(TABLE.replace('净利润\n80.09\n72.18\n', '净利润\n80.09\n72.18\n净利润\n80.09\n72.18\n', 1))['status'] == 'missing_evidence'
    group = TABLE.replace('少数股东损益\n10.08\n10.06\n', '')
    parent = '\n母公司利润表\n少数股东损益\n10.08\n10.06\n'
    assert check(group + parent)['status'] == 'missing_evidence'


def test_explicit_zero_or_dash_is_different_from_an_empty_amount():
    text = TABLE.replace('70.01\n62.12', '80.09\n72.18').replace('10.08\n10.06', '0\n—')
    income = figures(); income.update(current_net_profit='80.09', previous_net_profit='72.18')
    assert check(text, income)['passed']
    assert check(text.replace('0\n—', ''), income)['status'] == 'missing_evidence'


def test_negative_expense_is_subtracted_with_its_source_sign():
    text = TABLE.replace('20.01\n18.02', '-20.01\n(18.02)').replace('80.09\n72.18', '120.11\n108.22')
    text = text.replace('10.08\n10.06', '50.10\n46.10')
    result = check(text)
    assert result['passed']
    assert result['evidence']['income_tax']['values'] == ['-20.01', '-18.02']
    assert check_source(source('002230'))['evidence']['income_tax']['values'][0].startswith('-')


def test_only_exact_physical_page_edge_marker_is_ignored():
    first, second = TABLE.split('净利润\n80.09', 1)
    second = '净利润\n80.09' + second
    income = figures(); income['end_page_number'] = 11
    result = check_general_income_reconciliation([(10, first), (11, '11\n' + second)], income, report_year=2025)
    assert result['passed']
    assert result['evidence']['income_tax']['pages'] == {'start': 10, 'end': 10}
    result = check_general_income_reconciliation([(10, first), (11, '777\n' + second)], income, report_year=2025)
    # A nonmatching edge integer cannot be mistaken for a page marker.
    assert result['status'] == 'missing_evidence'
    interior = TABLE.replace('18.02\n净利润', '18.02\n10\n净利润')
    assert check(interior)['status'] == 'missing_evidence'


@pytest.mark.parametrize('pages,end', [([(10, TABLE), (12, TABLE)], 12), ([(10, TABLE), (10, TABLE)], 10), ([(10, TABLE)], 13)])
def test_missing_duplicate_or_overlong_page_windows_are_rejected(pages, end):
    income = figures(); income['end_page_number'] = end
    assert check_general_income_reconciliation(pages, income)['status'] == 'missing_evidence'


@pytest.mark.parametrize('declaration', ['单位：人民币千元', '单位：美元', '单位：人民币元\n单位：千元'])
def test_conflicting_unsupported_or_ambiguous_units_are_rejected(declaration):
    assert check(TABLE.replace('单位：人民币元', declaration))['status'] == 'missing_evidence'


def test_inherited_byd_unit_is_preserved_without_fabricating_local_declaration():
    sample = source('002594')
    result = check_source(sample)
    assert result['passed'] and result['unit'] == '千元'
    sample['income']['unit'] = ''
    assert check_source(sample)['status'] == 'missing_evidence'


def test_catl_scaled_integer_rounding_is_explicit_and_cannot_hide_larger_mismatch():
    sample = source('300750')
    result = check_source(sample)
    attribution = next(c for c in result['checks'] if c['key'] == 'profit_attribution')
    assert attribution['current']['difference'] == '1'
    assert result['tolerance'] == '1' and '舍入差' in result['rounding_note']
    sample['pages'] = [(n, t.replace('3,262,113', '3,262,115')) for n, t in sample['pages']]
    assert check_source(sample)['status'] == 'mismatch'
    sample = source('300750'); sample['income']['current_net_profit'] += 1
    assert check_source(sample)['status'] == 'mismatch'


def test_midea_signed_tax_checks_all_four_columns_and_explicit_credit():
    sample = source('000333')
    result = check_source(sample)
    assert result['passed'] and len(result['checks']) == 5
    assert result['evidence']['income_tax']['values'] == ['-8565147', '-7932532', '204833', '-271147']
    assert all('加带符号' in c['label'] for c in result['checks'] if c['key'].startswith('profit_after_tax'))
    sample['pages'] = [(n, t.replace('204,833', '204,835')) for n, t in sample['pages']]
    changed = check_source(sample)
    assert changed['status'] == 'mismatch'
    assert next(c for c in changed['checks'] if c['key'] == 'profit_after_tax_company')['current']['difference'] == '2'


def test_midea_four_column_role_order_is_required():
    sample = source('000333')
    sample['pages'] = [(n, t.replace('合并 \n合并 \n公司 \n公司', '合并 \n公司 \n合并 \n公司')) for n, t in sample['pages']]
    assert check_source(sample)['status'] == 'missing_evidence'


def test_english_table_is_outside_this_checker_scope():
    assert check('Group income statement\nRevenue')['status'] == 'not_applicable'


@pytest.mark.parametrize('value', [None, True, 'NaN', 'Infinity'])
def test_invalid_exposed_attributable_profit_cannot_pass(value):
    income = figures(); income['current_net_profit'] = value
    assert check(TABLE, income)['status'] == 'missing_evidence'


@pytest.mark.parametrize('reference', ['七76', '七 76', '七\n76'])
def test_compact_chinese_chapter_note_requires_note_header_and_two_complete_amounts(reference):
    table = TABLE.replace('减：所得税费用\n', '减：所得税费用\n'+reference+'\n')
    result = check(table)
    assert result['status'] == 'passed'
    assert result['evidence']['income_tax']['values'] == ['20.01', '18.02']
    assert check(table.replace('项目 附注', '项目'))['status'] == 'missing_evidence'
    assert check(table.replace('20.01\n18.02', '20.01'))['status'] == 'missing_evidence'


@pytest.mark.parametrize('reference', ['七0', '七0076', '七1000', '七76.5', '七76元', '未知76', '七76 1.00'])
def test_ambiguous_compact_notes_cannot_supply_or_consume_a_money_cell(reference):
    table = TABLE.replace('减：所得税费用\n', '减：所得税费用\n'+reference+'\n')
    assert check(table)['status'] == 'missing_evidence'
