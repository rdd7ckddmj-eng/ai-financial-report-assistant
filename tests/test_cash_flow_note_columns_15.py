"""Source-backed note columns cannot hide missing, extra or borrowed amounts."""
import json
from pathlib import Path
import pytest
from src.cash_flow_extractor import find_cash_flow_figures
from src.statement_evidence_rules import extract_statement_unit

DATA=json.loads((Path(__file__).parent/'fixtures/cash_flow_note_columns_2025.json').read_text())
def pages(code):
    return [(p['page_number'],p['text']) for x in DATA if x['code']==code for p in x['pages']]
def changed(code,old,new):
    source=pages(code)
    assert sum(t.count(old) for _,t in source)==1
    return [(p,t.replace(old,new)) for p,t in source]

@pytest.mark.parametrize('code,expected,physical',[('600196',5213226878.35,[152,153]),('600332',-232460774.72,[165])])
def test_real_note_columns_preserve_original_values_and_evidence(code,expected,physical):
    source=pages(code); result=find_cash_flow_figures(source)
    assert result['current_operating_cash_flow']==expected
    assert result['unit']=='人民币元'
    assert result['page_number']==physical[0] and result['end_page_number']==physical[-1]
    for item in result['layout_recoveries']:
        for span in item['source_spans']:
            assert span['original_text'] in dict(source)[span['page_number']]
    assert result['current_exchange_effect']==(-176810748.88 if code=='600196' else 3852075.65)

@pytest.mark.parametrize('replacement', ['', '未知科目\n', '母公司现金流量表\n', '65\n64\n', 'NaN\n', '64.5\n'])
def test_numeric_note_requires_one_integer_cell_and_explicit_column(replacement):
    source=changed('600196','净额 \n64 \n 5,213,226,878.35','净额 \n'+replacement+' 5,213,226,878.35')
    # No note is valid: an empty note cell leaves exactly the printed two amounts.
    assert (find_cash_flow_figures(source) is not None)==(replacement=='')

@pytest.mark.parametrize('replacement',['', 'NaN', '1.00\n16,302,938,963.14'])
def test_chinese_note_cannot_fill_or_drop_current_amount(replacement):
    assert find_cash_flow_figures(changed('600332','16,302,938,963.14\n19,823,543,794.72',replacement+'\n19,823,543,794.72')) is None

@pytest.mark.parametrize('replacement',['五、（六十四）\n未知科目','五、（六十四）\n母公司现金流量表','五、（六十四）\n五、（六十五）'])
def test_chinese_note_cannot_cross_account_boundary(replacement):
    assert find_cash_flow_figures(changed('600332','加：期初现金及现金等价物余额\n五、（六十四）','加：期初现金及现金等价物余额\n'+replacement)) is None

@pytest.mark.parametrize('header',['2025年\n2025年','2024年\n2025年','2025年\n2023年'])
def test_numeric_note_header_requires_ordered_adjacent_years(header):
    source=[(p,t.replace('2025年 \n2024年',header)) for p,t in pages('600196')]
    assert find_cash_flow_figures(source) is None

@pytest.mark.parametrize('suffix',['币万元','币千元','币百万元','币元'])
def test_only_complete_adjacent_currency_unit_is_joined(suffix):
    assert extract_statement_unit(['单位：人民',suffix])=='人民'+suffix
    assert extract_statement_unit(['单位：人民','其他说明',suffix])==''
    assert extract_statement_unit(['单位：人民',suffix,'币种：美元'])==''
    conflict='单位：万元' if suffix=='币元' else '单位：元'
    assert extract_statement_unit(['单位：人民',suffix,conflict])==''

@pytest.mark.parametrize('second',['五、64','（五）64','附注五、64'])
def test_qualified_note_cannot_then_skip_a_second_legacy_note(second):
    assert find_cash_flow_figures(changed('600196','净额 \n64 \n 5,213,226,878.35','净额 \n64\n'+second+'\n 5,213,226,878.35')) is None
