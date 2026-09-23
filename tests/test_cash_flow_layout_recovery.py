"""Actual full-table layouts plus unsafe reconnection counterexamples."""
import json
from pathlib import Path
import pytest
from src.cash_flow_extractor import find_cash_flow_figures

FIXTURE = json.loads((Path(__file__).parent/'fixtures/cash_flow_layout_coverage11.json').read_text())


def pages(code):
    item = next(x for x in FIXTURE if x['code'] == code)
    return [(p['page_number'], p['text']) for p in item['pages']]


def changed(code, old, new):
    source = pages(code)
    assert sum(t.count(old) for _, t in source) == 1
    return [(n,t.replace(old,new)) for n,t in source]


@pytest.mark.parametrize('code,expected', [('601669',30696651139.00),('600406',12768702125.04)])
def test_real_cash_layout_preserves_amounts_and_original_spans(code,expected):
    source=pages(code)
    result=find_cash_flow_figures(source)
    assert result is not None
    assert result['current_operating_cash_flow']==expected
    assert result['page_number']==source[0][0]
    assert result['end_page_number']==source[-1][0]
    recoveries=result['layout_recoveries']
    assert len(recoveries)==(2 if code=='601669' else 1)
    for recovery in recoveries:
        for span in recovery['source_spans']:
            assert span['original_text'] in dict(source)[span['page_number']]
    if code=='601669':
        assert result['current_opening_cash']==107147560745.56
        assert result['current_ending_cash']==117675051582.34
        assert [r['source_spans'][0]['page_number'] for r in recoveries]==[127,127]
    else:
        assert result['current_financing_cash_flow']==-5587321861.87
        assert result['previous_financing_cash_flow']==-5948579176.21
        assert [s['page_number'] for s in recoveries[0]['source_spans']]==[134,135]


@pytest.mark.parametrize('code',['601669','600406'])
@pytest.mark.parametrize('old,new', [('附注\n2025年度\n2024年度','2025年度\n2024年度'),
                                     ('附注\n2025年度\n2024年度','附注\n2024年度\n2025年度'),
                                     ('附注\n2025年度\n2024年度','附注\n2025年度\n2024年度\n2023年度')])
def test_new_recoveries_require_note_and_ordered_two_column_header(code,old,new):
    # Chinese Power also has a later mother-company header on page 127.
    source=pages(code)
    n,t=source[0]
    assert old in t
    source[0]=(n,t.replace(old,new,1))
    assert find_cash_flow_figures(source) is None


@pytest.mark.parametrize('old,new',[
 ('-5,587,321,861.87\n-5,948,579,176.21','-5,587,321,861.87\n99\n-5,948,579,176.21'),
 ('-5,587,321,861.87\n-5,948,579,176.21','-5,587,321,861.87\n无关科目\n-5,948,579,176.21'),
 ('135 / 306\n量净额','135 / 306\n无关科目\n量净额'),
 ('135 / 306\n量净额','135 / 306\n量净额\n100'),
 ('135 / 306\n量净额','135 / 306\n净额'),
 ('135 / 306\n量净额','135 / 306\n量净额其他'),
 ('135 / 306\n量净额','135 / 306\n母公司现金流量表\n量净额'),
 ('-5,948,579,176.21','-5,948,579,186.21'),
 ('-5,948,579,176.21','-59,48,579,176.21'),
 ('-5,948,579,176.21','-' + '9'*400),
])
def test_interleaved_label_rejects_unrelated_missing_extra_parent_or_mismatch(old,new):
    assert find_cash_flow_figures(changed('600406',old,new)) is None


def test_interleaved_label_rejects_reversed_tail():
    source=pages('600406')
    source=[(n,t.replace('筹资活动产生的现金流\n-5,587','量净额\n-5,587')
             .replace('135 / 306\n量净额','135 / 306\n筹资活动产生的现金流')) for n,t in source]
    assert find_cash_flow_figures(source) is None


def test_interleaved_label_rejects_nonconsecutive_pages():
    source=pages('600406');source[-1]=(136,source[-1][1])
    assert find_cash_flow_figures(source) is None


@pytest.mark.parametrize('old,new',[
 ('五、（八十四）107,147,560,745.56','五、（八十四）107,147,560,745.56 123'),
 ('五、（八十四）107,147,560,745.56','五、（八十四）107,147,560,755.56'),
 ('五、（八十四）107,147,560,745.56','五、（八十四）无关科目 107,147,560,745.56'),
 ('五、（八十四）107,147,560,745.56','五、（八十四）'),
 ('五、（八十四）107,147,560,745.56','无关科目\n五、（八十四）107,147,560,745.56'),
 ('五、（八十四）107,147,560,745.56','五、（八十四）10,7147,560,745.56'),
 ('五、（八十四）107,147,560,745.56','五、（八十四）' + '9'*400),
 ('五、（八十四）107,147,560,745.56','母公司现金流量表\n五、（八十四）107,147,560,745.56'),
])
def test_adjacent_note_does_not_borrow_or_hide_bad_cells(old,new):
    assert find_cash_flow_figures(changed('601669',old,new)) is None


@pytest.mark.parametrize('prefix',['（六）','(6)','六、','6.'])
def test_numbered_parent_boundary_never_supplies_missing_group_evidence(prefix):
    source=changed('600406','135 / 306\n量净额',f'135 / 306\n{prefix}母公司现金流量表\n量净额')
    assert find_cash_flow_figures(source) is None


LEGACY = json.loads((Path(__file__).parent/'fixtures/industry_expansion_10.json').read_text())


@pytest.mark.parametrize('code,current,previous',[
    ('600276',11235378130.63,7422753038.71),
    ('600309',33105189455.82,30053435178.33),
    ('601985',37408396868.53,40720532971.06),
])
def test_existing_cash_rows_accept_complete_compact_and_nested_notes(code,current,previous):
    source=next(x for x in LEGACY if x['code']==code)
    result=find_cash_flow_figures([(p['page_number'],p['text']) for p in source['pages']])
    assert result is not None
    assert result['current_operating_cash_flow']==current
    assert result['previous_operating_cash_flow']==previous


@pytest.mark.parametrize('code,note,bad',[
    ('600276','七、79（4）','七、79（4）其他科目'),
    ('600276','七、79（4）','七、79（4）1.00'),
    ('600309','七79','其他科目七79'),
    ('600309','七79','七79.00'),
    ('601985','七79','七79无数据'),
])
def test_expanded_note_syntax_does_not_swallow_other_accounts_or_cells(code,note,bad):
    source=next(x for x in LEGACY if x['code']==code)
    assert any(note in p['text'] for p in source['pages'])
    pages=[(p['page_number'],p['text'].replace(note,bad)) for p in source['pages']]
    assert find_cash_flow_figures(pages) is None
