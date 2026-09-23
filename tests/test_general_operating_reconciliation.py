"""Complete operating rows extend evidence; partial rows never manufacture it."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.general_income_reconciliation import check_general_income_reconciliation
from src.general_operating_reconciliation import _REQUIRED


SAMPLES = json.loads((Path(__file__).parent / 'fixtures/general_income_reconciliation_real.json').read_text())
SUPPORTED = ('002594', '000725', '002415', '300760')
ROWS = [
    ('营业收入', '1000.00', '900.00'),
    ('减：营业成本', '500.00', '400.00'),
    ('税金及附加', '20.00', '20.00'),
    ('销售费用', '30.00', '30.00'),
    ('管理费用', '40.00', '40.00'),
    ('研发费用', '50.00', '50.00'),
    ('财务费用', '-10.00', '10.00'),
    ('其中：利息费用', '2.00', '2.00'),
    ('利息收入', '12.00', '12.00'),
    ('加：其他收益', '10.00', '10.00'),
    ('投资收益', '5.00', '5.00'),
    ('其中：对联营企业和合营企业的投资收益', '1.00', '1.00'),
    ('以摊余成本计量的金融资产终止确认收益', '2.00', '2.00'),
    ('公允价值变动收益', '2.00', '2.00'),
    ('信用减值损失', '-3.00', '-3.00'),
    ('资产减值损失', '-4.00', '-4.00'),
    ('资产处置收益', '1.00', '1.00'),
    ('营业利润', '381.00', '361.00'),
    ('加：营业外收入', '8.00', '7.00'),
    ('减：营业外支出', '9.00', '6.00'),
    ('利润总额', '380.00', '362.00'),
    ('减：所得税费用', '80.00', '72.00'),
    ('净利润', '300.00', '290.00'),
    ('归属于母公司股东的净利润', '280.00', '270.00'),
    ('少数股东损益', '20.00', '20.00'),
]


def table(rows=ROWS):
    return ('合并利润表\n单位：人民币元\n项目\n2025年度\n2024年度\n'
            + '\n'.join('\n'.join(row) for row in rows) + '\n六、其他综合收益的税后净额\n')


def income(**changes):
    return dict(unit='人民币元', page_number=10, end_page_number=10,
        current_revenue='1000.00', previous_revenue='900.00',
        current_net_profit='280.00', previous_net_profit='270.00', **changes)


def check(text=None, figures=None):
    return check_general_income_reconciliation([(10, text or table())], figures or income(), report_year=2025)


def operating(result):
    return result['operating_reconciliation']


def change_row(label, *, current=None, previous=None):
    return [(name, current if current is not None and name == label else a,
             previous if previous is not None and name == label else b) for name, a, b in ROWS]


@pytest.mark.parametrize('code', SUPPORTED)
def test_four_official_source_windows_reconcile_all_operating_components(code):
    source = next(sample for sample in SAMPLES if sample['code'] == code)
    result = check_general_income_reconciliation(source['pages'], source['income'], report_year=source['year'])
    extra = operating(result)
    assert result['passed'] and extra['passed']
    assert len(result['checks']) == 6 and len(extra['checks']) == 3
    assert len(source['pdf_sha256']) == 64 and source['source_url'].startswith('https://')
    for item in extra['checks']:
        for period in ('current', 'previous'):
            assert item[period]['passed']
            assert Decimal(item[period]['difference']) == 0
    for row in extra['evidence'].values():
        assert len(row['values']) == 2 and row['excerpt']
        assert source['income']['page_number'] <= row['pages']['start'] <= row['pages']['end'] <= source['income']['end_page_number']


def test_equations_signs_subrows_and_evidence_are_explicit():
    result = check(); extra = operating(result)
    assert result['passed'] and extra['passed']
    relation = extra['checks'][0]
    assert relation['current'] == dict(left='381.00', right='381.00', difference='0.00', passed=True)
    assert relation['previous']['left'] == '361.00'
    assert extra['evidence']['financial_expense']['coefficient'] == -1
    assert extra['evidence']['financial_expense']['values'] == ['-10.00', '10.00']
    assert extra['evidence']['credit_impairment']['coefficient'] == 1
    assert extra['evidence']['credit_impairment']['values'] == ['-3.00', '-3.00']
    for key in ('interest_expense_detail', 'interest_income_detail', 'associate_income_detail', 'derecognition_detail'):
        assert extra['evidence'][key]['coefficient'] == 0
        assert '不重复加总' in extra['evidence'][key]['role']
    assert '收入与成本全部分项尚未逐项勾稽' not in result['note']


@pytest.mark.parametrize('key', _REQUIRED)
@pytest.mark.parametrize('period', ('current', 'previous'))
def test_wrong_cell_in_any_required_operating_row_or_year_is_not_hidden(key, period):
    before = check(); row = operating(before)['evidence'][key]
    changed = str(Decimal(row['values'][0 if period == 'current' else 1]) + Decimal('0.02'))
    result = check(table(change_row(row['label'], **{period: changed})))
    assert result['status'] == 'mismatch' and not result['passed']
    assert operating(result)['status'] == 'mismatch'
    assert any(not item[period]['passed'] for item in operating(result)['checks'])


@pytest.mark.parametrize('key', _REQUIRED[:-1])
def test_required_operating_rows_are_never_assumed_zero_when_absent(key):
    label = operating(check())['evidence'][key]['label']
    result = check(table([row for row in ROWS if row[0] != label]))
    if key == 'operating_revenue':
        # Without an income row even the older boundary validator stops.
        assert result['status'] == 'missing_evidence' and not result['checks']
        return
    assert operating(result)['status'] == 'missing_evidence'
    assert not operating(result)['passed'] and operating(result)['checks'] == []
    assert len(result['checks']) == 3  # Existing tax and attribution scope only.


@pytest.mark.parametrize('label', ('营业收入', '营业利润', '利润总额', '财务费用', '利息收入', '投资收益'))
def test_duplicate_totals_components_and_detail_rows_are_rejected(label):
    rows = []
    for row in ROWS:
        rows.append(row)
        if row[0] == label:
            rows.append(row)
    result = check(table(rows))
    assert operating(result)['status'] == 'missing_evidence'
    assert not operating(result)['checks']


@pytest.mark.parametrize('label', ('信用减值损失', '营业利润', '利润总额'))
@pytest.mark.parametrize('extra', ('0.00', '1.00', '1,,000', 'NaN', '无数据', '+123', '123.1.2'))
def test_extra_or_malformed_amount_cannot_end_row_silently(label, extra):
    text = table()
    original = '\n'.join(next(row for row in ROWS if row[0] == label))
    result = check(text.replace(original, original + '\n' + extra))
    assert not operating(result)['passed'] and operating(result)['checks'] == []


@pytest.mark.parametrize('unknown', ('新增经营收益\n0.00\n0.00', '新增经营收益\n20.00\n20.00',
    '其他收益（未经核实）\n1.00\n1.00', '其中：未识别损失\n1.00\n1.00'))
def test_unknown_rows_even_zero_or_apparent_subtotals_are_not_discarded(unknown):
    assert operating(check(table().replace('营业利润\n', unknown + '\n营业利润\n')))['status'] == 'missing_evidence'
    assert operating(check(table().replace('减：所得税费用\n', unknown + '\n减：所得税费用\n')))['status'] == 'missing_evidence'


def test_nested_detail_cannot_be_moved_out_of_its_parent_section():
    rows = [row for row in ROWS if row[0] != '利息收入']
    rows.insert(15, next(row for row in ROWS if row[0] == '利息收入'))
    assert operating(check(table(rows)))['status'] == 'missing_evidence'


def test_subdetail_amount_is_not_a_second_parent_contribution():
    # Subdetails have their own provenance, but are not extra income/costs.
    result = check(table(change_row('利息收入', current='120.00', previous='120.00')))
    assert result['passed'] and operating(result)['passed']
    assert operating(result)['evidence']['interest_income_detail']['values'] == ['120.00', '120.00']


@pytest.mark.parametrize('code', ('000651', '000333', '002475', '000858'))
def test_total_revenue_and_four_column_layouts_retain_explicit_older_scope(code):
    sample = next(sample for sample in SAMPLES if sample['code'] == code)
    result = check_general_income_reconciliation(sample['pages'], sample['income'], report_year=sample['year'])
    assert result['passed'] and operating(result)['status'] == 'unsupported_layout'
    assert operating(result)['checks'] == []
    assert '未执行' in result['note']
    assert not any(item['key'] == 'operating_profit_components' for item in result['checks'])


@pytest.mark.parametrize('field', ('current_revenue', 'previous_revenue'))
def test_output_revenue_must_be_the_exact_reconciled_row(field):
    figures = income(); figures[field] = '1001.00'
    result = check(figures=figures)
    assert result['status'] == 'mismatch'
    assert operating(result)['checks'][-1]['key'] == 'selected_operating_revenue'
    assert not operating(result)['checks'][-1]['passed']


def test_parent_income_table_is_not_borrowed_to_complete_operating_rows():
    without_cost = table([row for row in ROWS if row[0] != '减：营业成本'])
    parent = '\n母公司利润表\n减：营业成本\n500.00\n400.00\n'
    assert operating(check(without_cost + parent))['status'] == 'missing_evidence'


def test_scaled_unit_tolerance_is_inherited_without_widening():
    figures = income(); figures['unit'] = '人民币千元'
    text = table().replace('人民币元', '人民币千元').replace('.00', '')
    figures.update(current_revenue='1000', previous_revenue='900', current_net_profit='280', previous_net_profit='270')
    result = check(text, figures)
    assert result['tolerance'] == operating(result)['tolerance'] == '1'
    # The older explicitly disclosed integer-unit allowance remains one unit.
    assert operating(check(text.replace('营业利润\n381\n', '营业利润\n382\n'), figures))['passed']
    assert operating(check(text.replace('营业利润\n381\n', '营业利润\n383\n'), figures))['status'] == 'mismatch'


def test_integer_note_reference_requires_note_header_and_never_applies_to_subtotal():
    text = table().replace('减：营业成本\n', '减：营业成本\n47\n')
    assert operating(check(text))['status'] == 'missing_evidence'
    assert operating(check(text.replace('项目\n', '项目 附注\n')))['passed']
    text = table().replace('项目\n', '项目 附注\n').replace('营业利润\n', '营业利润\n47\n')
    assert operating(check(text))['status'] == 'missing_evidence'


def test_real_powerchina_tax_note_preserves_official_two_year_amounts():
    sample = json.loads((Path(__file__).parent / 'fixtures/powerchina_income_note_2025.json').read_text())
    result = check_general_income_reconciliation(sample['pages'], sample['income'], report_year=sample['year'])
    assert result['passed'] and operating(result)['status'] == 'unsupported_layout'
    row = result['evidence']['income_tax']
    assert row['values'] == ['4137137002.31', '3706302910.11']
    assert row['pages'] == {'start': 123, 'end': 123}
    assert '五、（八十）' in row['excerpt'] and len(sample['pdf_sha256']) == 64
    assert sample['source_url'] == 'https://static.cninfo.com.cn/finalpage/2026-04-24/1225174689.PDF'


def test_display_export_and_candidate_gate_use_actual_extended_relationships():
    from src.china_stock import build_company_identity
    from src.on_demand_financial_snapshot import (build_on_demand_financial_snapshot,
        build_financial_snapshot_report_html, income_reconciliation_rows)
    from test_income_reconciliation_integration import candidate, SAMPLES as FULL_SAMPLES

    sample = deepcopy(next(s for s in FULL_SAMPLES if s['code'] == '000725'))
    result = candidate(sample)
    snapshot = build_on_demand_financial_snapshot(build_company_identity(sample['code'], sample['name']), result)
    assert result['status'] == 'ready_for_human_review' and operating(result['income_reconciliation'])['passed']
    assert len(income_reconciliation_rows(snapshot)) == 6
    assert '营业收入减成本费用加各项收益等于营业利润' in build_financial_snapshot_report_html(snapshot)
    # Keep extracted revenue, attributable profit and the entire bottom half
    # unchanged. Previously this wrong cost could still pass those two checks.
    for page in sample['pages']:
        page['text'] = page['text'].replace('172,602,044,011', '172,602,044,111')
    altered = candidate(sample)
    assert altered['status'] == 'needs_review'
    assert altered['statement_checks']['income_statement_reconciled'] is False
    blocked = build_on_demand_financial_snapshot(build_company_identity(sample['code'], sample['name']), altered)
    assert blocked['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in blocked['metrics'])


@pytest.mark.parametrize('note', ('五、（八十）', '五、(八十)', '五、（八\n十）'))
def test_powerchina_chinese_note_with_separator_and_parentheses_is_not_an_amount(note):
    text = table().replace('项目\n', '项目 附注\n').replace('减：所得税费用\n', '减：所得税费用\n' + note + '\n')
    result = check(text)
    assert result['passed']
    assert result['evidence']['income_tax']['values'] == ['80.00', '72.00']


@pytest.mark.parametrize('note', ('五、、（八十）', '五、（八十', '五、八十）', '五、（八十.5）', '五、（八十）1.00', '五、（A）'))
def test_damaged_powerchina_note_does_not_become_a_valid_reference(note):
    text = table().replace('项目\n', '项目 附注\n').replace('减：所得税费用\n', '减：所得税费用\n' + note + '\n')
    result = check(text)
    assert not result['passed'] and result['status'] == 'missing_evidence'
