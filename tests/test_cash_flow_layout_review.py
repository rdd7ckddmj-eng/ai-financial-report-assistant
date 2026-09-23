"""Independent counterexamples for cash-flow layout recovery boundaries."""
import json
from pathlib import Path

import pytest

from src.cash_flow_extractor import find_cash_flow_figures


SOURCES = json.loads((Path(__file__).parent / 'fixtures/cash_flow_layout_coverage11.json').read_text())


def replace_source(code, old, new):
    item = next(source for source in SOURCES if source['code'] == code)
    pages = [(page['page_number'], page['text']) for page in item['pages']]
    assert sum(text.count(old) for _, text in pages) == 1
    return [(number, text.replace(old, new)) for number, text in pages]


@pytest.mark.parametrize('invalid', ('NaN', '123.1.2', '+123', '无数据'))
def test_note_recovery_cannot_ignore_invalid_third_cell(invalid):
    pages = replace_source('601669',
        '89,770,896,423.47\n六、期末',
        '89,770,896,423.47\n' + invalid + '\n六、期末')
    assert find_cash_flow_figures(pages) is None


@pytest.mark.parametrize('invalid', ('NaN', '123.1.2', '+123', '无数据'))
def test_interleaved_recovery_cannot_ignore_invalid_cell_after_label_tail(invalid):
    pages = replace_source('600406',
        '135 / 306\n量净额', '135 / 306\n量净额\n' + invalid)
    assert find_cash_flow_figures(pages) is None


def test_conflicting_duplicate_opening_balance_is_not_hidden_by_first_recovery():
    pages = replace_source('601669',
        '89,770,896,423.47\n六、期末',
        '89,770,896,423.47\n加：期初现金及现金等价物余额\n1.00\n2.00\n六、期末')
    assert find_cash_flow_figures(pages) is None


def test_conflicting_duplicate_financing_total_is_not_hidden_by_interleaved_recovery():
    pages = replace_source('600406',
        '135 / 306\n量净额',
        '135 / 306\n量净额\n筹资活动产生的现金流量净额\n1.00\n2.00')
    assert find_cash_flow_figures(pages) is None


def test_unknown_line_before_note_must_not_fall_back_to_borrowing_legacy_amounts():
    pages = replace_source('601669',
        '五、（八十四）107,147,560,745.56',
        '无关科目\n五、（八十四）\n107,147,560,745.56')
    assert find_cash_flow_figures(pages) is None


@pytest.mark.parametrize('boundary', ('无关科目', '母公司现金流量表'))
def test_note_before_unknown_line_or_parent_boundary_is_also_rejected(boundary):
    pages = replace_source('601669',
        '五、（八十四）107,147,560,745.56',
        '五、（八十四）\n' + boundary + '\n107,147,560,745.56')
    assert find_cash_flow_figures(pages) is None
