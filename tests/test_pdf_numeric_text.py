import pytest
from src.pdf_numeric_text import normalize_numeric_parentheses
from src.financial_statement_extractor import _normalise_lines, _extract_chinese_row_pair


@pytest.mark.parametrize('text,expected',[
    ('(54,592 )','(54,592)'),('（ 54，592 ）','（54，592）'),
    ('(1 2)','(1 2)'),('(1\n)','(1\n)'),('附注( 四 )','附注( 四 )'),
    ('(1 ) (2 )','(1) (2)'),('(-1.25 )','(-1.25)')])
def test_only_single_numeric_parentheses_normalize(text,expected):
    assert normalize_numeric_parentheses(text)==expected


def test_negative_pair_survives_pdf_spaces():
    assert _extract_chinese_row_pair(_normalise_lines('利息支出\n33\n(54,592 )\n(49,859)'),('利息支出',))==(-54592,-49859)
