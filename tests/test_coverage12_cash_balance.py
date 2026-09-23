"""Original 2025 statement layouts and bounded corruption regressions."""
import json
from pathlib import Path

import pytest

from src.balance_sheet_extractor import find_balance_sheet_figures, extract_balance_sheet_figures
from src.cash_flow_extractor import find_cash_flow_figures, extract_cash_flow_figures


SAMPLES = json.loads((Path(__file__).parent / 'fixtures/coverage12_cash_balance.json').read_text())


def pages(code, start, end):
    sample = next(s for s in SAMPLES if s['code'] == code)
    return [(p['page_number'], p['text']) for p in sample['pages']
            if start <= p['page_number'] <= end]


def replace(rows, old, new):
    assert sum(text.count(old) for _, text in rows) == 1
    return [(n, t.replace(old, new)) for n, t in rows]


def test_conch_sign_caption_keeps_original_signed_amount_and_provenance():
    rows = pages('600585', 98, 100)
    cash = find_cash_flow_figures(rows)
    assert cash['current_operating_cash_flow'] == 16643907685
    assert cash['previous_operating_cash_flow'] == 18476252523
    assert cash['current_net_cash_change'] == -5661029214
    assert cash['previous_net_cash_change'] == 4765130821
    assert cash['end_page_number'] == 99
    recovery, = cash['layout_recoveries']
    assert recovery['kind'] == 'wrapped_net_change_sign_caption'
    span, = recovery['source_spans']
    assert span['page_number'] == 99
    assert span['original_text'] in dict(rows)[99]
    assert '（净减少以“-”号填列）' in span['original_text']


@pytest.mark.parametrize('old,new', [
    ('（净减少以“-”号填列）', '（其他未知说明）'),
    ('-5,661,029,214', '-5,661,029,215'),
    ('五、59（1） \n-5,661,029,214', '五、59（1） \n999 \n-5,661,029,214'),
    ('五、59（1） \n-5,661,029,214', '五、59（1） \n'),
])
def test_conch_rejects_unknown_caption_imbalance_extra_or_missing_cell(old, new):
    assert find_cash_flow_figures(replace(pages('600585', 98, 100), old, new)) is None


def test_gwm_physical_footer_and_exact_financing_alias():
    cash = find_cash_flow_figures(pages('601633', 148, 149))
    assert cash['current_operating_cash_flow'] == 40355401297.93
    assert cash['previous_operating_cash_flow'] == 27771483801.77
    assert cash['current_financing_cash_flow'] == -13445031000.84
    assert cash['previous_financing_cash_flow'] == -12009066516.68
    assert cash['current_ending_cash'] == 25280701698
    assert cash['previous_ending_cash'] == 27233274462.30
    assert cash['page_number'] == cash['end_page_number'] == 148
    balance = find_balance_sheet_figures(pages('601633', 142, 144))
    assert balance['current_total_assets'] == 225287872883.05
    assert balance['previous_total_assets'] == 217720295344.69
    assert balance['current_total_liabilities'] == 137395831405.82
    assert balance['previous_total_liabilities'] == 138727125825.55
    assert balance['page_number'] == 142 and balance['end_page_number'] == 143


@pytest.mark.parametrize('old,new', [
    ('\n148\n', '\n147\n'),
    ('\n \n \n148\n', '\n148\n'),
    ('25,280,701,698.00', '25,280,701,699.00'),
    ('筹资活动(使用)产生的现金流量净额', '筹资活动未知的现金流量净额'),
])
def test_gwm_cash_rejects_unmatched_footer_or_modified_evidence(old, new):
    assert find_cash_flow_figures(replace(pages('601633', 148, 149), old, new)) is None


@pytest.mark.parametrize('old,new', [
    ('\n142\n', '\n141\n'),
    ('225,287,872,883.05  \n217,720,295,344.69', '225,287,872,884.05  \n217,720,295,344.69'),
    ('225,287,872,883.05  \n217,720,295,344.69', '225,287,872,883.05'),
])
def test_gwm_balance_requires_both_original_cells_and_matching_footer(old, new):
    assert find_balance_sheet_figures(replace(pages('601633', 142, 144), old, new)) is None


@pytest.mark.parametrize('extractor,start,end', [
    (extract_balance_sheet_figures, 142, 143),
    (extract_cash_flow_figures, 148, 148),
])
def test_source_page_evidence_cannot_silently_replace_mismatched_input(extractor, start, end):
    rows = pages('601633', start, end)
    assert extractor(start, 'not the source text', source_pages=rows) is None


@pytest.mark.parametrize('value', ['-5,,661,029,214', '-56,61,029,214', '(-5661029214',
    '-5,661,029,214)', 'NaN', '+5661029214'])
def test_sign_caption_recovery_requires_strict_original_number_tokens(value):
    rows = replace(pages('600585', 98, 100), '-5,661,029,214', value)
    assert find_cash_flow_figures(rows) is None


@pytest.mark.parametrize('kind,code,start,end,original', [
    ('cash', '601633', 148, 149, '25,280,701,698.00 \n27,233,274,462.30'),
    ('balance', '601633', 142, 144, '225,287,872,883.05  \n217,720,295,344.69'),
])
@pytest.mark.parametrize('damage', ['before', 'after', 'duplicate', 'malformed_before',
    'malformed_after', 'bad_comma', 'unknown_before', 'blank', 'one_column'])
def test_footer_recovery_never_selects_two_from_an_ambiguous_row(kind, code, start, end, original, damage):
    first, second = original.split('\n')
    replacement = {
        'before': '999\n' + original,
        'after': original + '\n999',
        'duplicate': original + '\n' + original,
        'malformed_before': '+999\n' + original,
        'malformed_after': original + '\nNaN',
        'bad_comma': original.replace(',', ',,', 1),
        'unknown_before': '未知科目\n' + original,
        'blank': '',
        'one_column': first,
    }[damage]
    extractor = find_cash_flow_figures if kind == 'cash' else find_balance_sheet_figures
    assert extractor(replace(pages(code, start, end), original, replacement)) is None


@pytest.mark.parametrize('prefix', ['', '3、', '三、', '（三）', '(3)', '3.'])
@pytest.mark.parametrize('kind', ['cash', 'balance'])
def test_new_footer_layout_stops_at_every_explicit_parent_title(prefix, kind):
    if kind == 'cash':
        rows = pages('601633', 148, 149)
        value = '25,280,701,698.00'
        title = '母公司现金流量表'
        extractor = find_cash_flow_figures
    else:
        rows = pages('601633', 142, 144)
        value = '225,287,872,883.05  \n217,720,295,344.69'
        title = '母公司资产负债表'
        extractor = find_balance_sheet_figures
    assert extractor(replace(rows, value, prefix + title + '\n' + value)) is None


@pytest.mark.parametrize('kind,label', [
    ('cash', '六、年末现金及现金等价物余额'), ('balance', '资产总计'),
])
def test_footer_recovery_rejects_duplicate_target_labels(kind, label):
    rows = pages('601633', 148, 148) if kind == 'cash' else pages('601633', 142, 143)
    extractor = find_cash_flow_figures if kind == 'cash' else find_balance_sheet_figures
    assert extractor(replace(rows, label, label + '\n' + label)) is None
