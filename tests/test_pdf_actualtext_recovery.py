"""Native structure corruption must be proved independently of amounts."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.pdf_actualtext_recovery import (
    derive_native_text_recovery, validate_native_text_recoveries,
    compact_native_text_recoveries, replay_native_text_recovery,
)
from src.audited_company_onboarding import build_candidate_report_result

FIXTURE = json.loads((Path(__file__).parent/'fixtures/coverage15_unicom_actualtext.json').read_text())
RECORDS = [p['native_text_recovery'] for p in FIXTURE['pages'] if 'native_text_recovery' in p]


class StructureDocument:
    """Minimal explicit PDF structure; native text is from the real physical p79."""
    page_count = 2
    def __init__(self):
        self.record = deepcopy(RECORDS[-1])
        self.calls = []
        self.pages = [SimpleNamespace(xref=47, number=0), SimpleNamespace(xref=40928, number=1)]
        self.pages[1].get_text = self.get_text
        self.keys = {
            (47, 'StructParents'): ('int', '3'), (40928, 'StructParents'): ('int', '3'),
            (1, 'StructTreeRoot'): ('xref', '497 0 R'), (497, 'ParentTree'): ('xref', '499 0 R'),
            (499, 'Nums'): ('array', '[3 614 0 R]'),
            (618, 'ActualText'): ('string', '第一节'), (618, 'Pg'): ('xref', '47 0 R'),
            (618, 'K'): ('array', '[0]'),
        }
        self.array = '[618 0 R]'
    def __getitem__(self, index): return self.pages[index]
    def pdf_catalog(self): return 1
    def xref_get_key(self, xref, key): return self.keys.get((xref,key), ('null','null'))
    def xref_object(self, xref): assert xref == 614; return self.array
    def get_text(self, mode, *, flags):
        self.calls.append(flags)
        return self.record['native_text']


ENGINE = SimpleNamespace(TEXTFLAGS_TEXT=195, TEXT_IGNORE_ACTUALTEXT=2048, VersionBind='1.28.2')


def derive(document):
    return derive_native_text_recovery(document, document.pages[1],
        original_text=document.record['original_text'], report_year=2025,
        pdf_fingerprint=FIXTURE['source']['sha256'], module=ENGINE)


def test_structural_collision_selects_native_before_financial_calculation():
    doc = StructureDocument()
    result = derive(doc)
    assert result['foreign_replacements'][0]['actual_text'] == '第一节'
    assert result['colliding_pages'] == [{'page_number':1,'page_xref':47},{'page_number':2,'page_xref':40928}]
    assert result['page_number'] == 2
    assert result['native_text'] == doc.record['native_text']
    assert doc.calls == [2243]
    # A changed amount does not control detection; downstream checks own amounts.
    doc.record['native_text'] = doc.record['native_text'].replace('392,222,880,560', '392,222,880,561')
    assert derive(doc) is not None


@pytest.mark.parametrize('change', [
    lambda d: d.keys.update({(47,'StructParents'):('int','99')}),
    lambda d: d.keys.update({(618,'Pg'):('xref','40928 0 R')}),
    lambda d: d.keys.update({(618,'Pg'):('xref','99 0 R')}),
    lambda d: d.keys.update({(618,'Pg'):('null','null')}),
    lambda d: d.keys.update({(618,'K'):('array','[1]')}),
    lambda d: d.keys.update({(499,'Nums'):('null','null')}),
    lambda d: d.keys.update({(499,'Nums'):('array','[3 614 0 R 3 615 0 R]')}),
    lambda d: d.keys.update({(618,'ActualText'):('string','unseen replacement')}),
    lambda d: setattr(d,'array','[618 0 R null]'),
    lambda d: d.record.update(original_text=d.record['original_text'].replace('合并及公司利润表','母公司利润表')),
    lambda d: d.record.update(native_text=d.record['native_text'].replace('2024年度','2023年度')),
    lambda d: d.record.update(native_text=d.record['native_text'].replace('金额单位为人民币元','金额单位未知')),
    lambda d: d.record.update(native_text=d.record['native_text'].replace('一、营业收入','未知科目')),
    lambda d: d.record.update(native_text=d.record['original_text']),
    lambda d: d.record.update(native_text=d.record['native_text'] + 'x'*16000),
])
def test_missing_or_ambiguous_structure_never_enables_alternate_text(change):
    doc = StructureDocument(); change(doc)
    assert derive(doc) is None


def test_real_three_page_evidence_retains_default_native_and_source_hash():
    records = validate_native_text_recoveries(RECORDS, pdf_fingerprint=FIXTURE['source']['sha256'], report_year=2025)
    assert [r['page_number'] for r in records] == [77,78,79]
    assert [len(r['foreign_replacements']) for r in records] == [31,10,76]
    assert '第一节' in records[-1]['original_text']
    assert '392,222,880,560' in records[-1]['native_text']
    copied = compact_native_text_recoveries(records)
    copied[-1]['foreign_replacements'].clear()
    assert len(records[-1]['foreign_replacements']) == 76


@pytest.mark.parametrize('key,value', [
    ('schema','unknown'), ('method','ocr'), ('reason','balances'), ('report_year',2024),
    ('pdf_fingerprint_sha256','0'*64), ('page_number',True), ('page_xref',0),
    ('default_flags',2048), ('native_flags',195), ('original_text_sha256','0'*64),
    ('native_text_sha256','0'*64), ('native_excerpt','x'), ('header_excerpt',''),
    ('header_years',[2024,2025]), ('foreign_replacements',[]), ('colliding_pages',[]),
])
def test_corrupt_or_cross_document_record_rejected_at_downstream_boundary(key,value):
    records=deepcopy(RECORDS); records[0][key]=value
    with pytest.raises(ValueError):
        validate_native_text_recoveries(records, pdf_fingerprint=FIXTURE['source']['sha256'], report_year=2025)


def test_foreign_actualtext_cannot_point_to_current_page_or_duplicate_mcid():
    for mutate in [
        lambda r: r['foreign_replacements'][0].update(referenced_page_xref=r['page_xref'],referenced_page_number=r['page_number']),
        lambda r: r['foreign_replacements'][1].update(marked_content_ids=r['foreign_replacements'][0]['marked_content_ids']),
    ]:
        records=deepcopy(RECORDS);mutate(records[0])
        with pytest.raises(ValueError):validate_native_text_recoveries(records)


def test_duplicate_and_excessive_page_records_fail_closed():
    for records in [RECORDS+[RECORDS[0]],RECORDS*3]:
        with pytest.raises(ValueError):validate_native_text_recoveries(records)


@pytest.mark.parametrize('mutate', [
    lambda p:p.update(text=p['text']+'x'),
    lambda p:p.update(page_number=p['page_number']+1),
    lambda p:p.update(financial_geometry={'adjustments':[{'fake':True}]}),
])
def test_page_binding_and_other_text_derivation_conflicts_rejected(mutate):
    page=deepcopy(next(p for p in FIXTURE['pages'] if p['page_number']==79));mutate(page)
    with pytest.raises(ValueError):replay_native_text_recovery(page,pdf_fingerprint=FIXTURE['source']['sha256'],report_year=2025)


def test_candidate_does_not_fall_back_if_recovery_identity_is_invalid():
    # Synthetic PDF envelope intentionally differs from exact fixture's source.
    company={'code':'600050','name':'中国联通','exchange':'SSE','canonical_code':'600050.SH'}
    report={'report_year':2025,'published_date':'2026-03-20','title':'中国联通2025年年度报告','url':FIXTURE['source']['url']}
    candidate=build_candidate_report_result(company,report,b'%PDF-different-document',deepcopy(FIXTURE['pages']))
    assert candidate['status']=='needs_review'
    assert not any(candidate['statement_checks'].values())
    assert not any(value is not None for value in candidate['values'].values())
    assert candidate['pdf_native_text_recoveries']==[]
    assert candidate['extraction_note']

@pytest.mark.parametrize('date', ['2025 年6 月30 日止年度', '2025 年1 月1 日至6 月30 日',
    '2025 年9 月30 日止年度', '2025 年12 月30 日止年度', '2024 年12 月31 日止年度'])
def test_real_income_header_requires_complete_selected_annual_period(date):
    doc=StructureDocument()
    assert '2025 年12 月31 日止年度' in doc.record['native_text']
    doc.record['native_text']=doc.record['native_text'].replace('2025 年12 月31 日止年度', date, 1)
    assert derive(doc) is None


@pytest.mark.parametrize('changed_date', ['2025年6月30日', '2025年12月30日', '2024年12月31日'])
def test_real_balance_header_dates_cannot_be_inferred_from_year_alone(changed_date):
    from src.pdf_actualtext_recovery import _header
    record=RECORDS[0]
    assert '2025年12月31日' in record['native_text']
    damaged=record['native_text'].replace('2025年12月31日',changed_date,1)
    assert _header(damaged,2025) is None


@pytest.mark.parametrize('title,roles,valid', [
    ('合并利润表',[],True), ('合并利润表',['合并','合并'],True),
    ('合并利润表',['公司','公司'],False), ('合并利润表',['母公司','母公司'],False),
    ('合并利润表',['合并','公司'],False), ('合并及公司利润表',[],False),
    ('合并及公司利润表',['合并','合并'],False),
])
def test_two_column_roles_cannot_substitute_company_for_consolidated(title,roles,valid):
    from src.pdf_actualtext_recovery import _header
    rows=[title,'2025年12月31日止年度','(除特别注明外，金额单位为人民币元)','项目','附注','2025年度']
    if roles:rows.append(roles[0])
    rows.append('2024年度')
    if roles:rows.append(roles[1])
    rows.append('一、营业收入')
    assert (_header('\n'.join(rows),2025) is not None)==valid


@pytest.mark.parametrize('kid', ['['+'0 '*4097+']', '['+'9'*100001+']', '[4096]', '[00000]'])
def test_mcid_array_is_bounded_before_integer_construction(kid):
    doc=StructureDocument();doc.keys[(618,'K')]=('array',kid)
    assert derive(doc) is None
    assert doc.calls==[]


def test_foreign_text_budget_stops_before_more_structure_is_read():
    doc=StructureDocument();refs=list(range(618,629));doc.array='['+' '.join(f'{r} 0 R' for r in refs)+']'
    for i,r in enumerate(refs):
        doc.keys[(r,'ActualText')]=('string','x'*2000)
        doc.keys[(r,'Pg')]=('xref','47 0 R')
        doc.keys[(r,'K')]=('array',f'[{i}]')
    original=doc.xref_get_key
    visited=[]
    def tracking(x,key):visited.append(x);return original(x,key)
    doc.xref_get_key=tracking
    assert derive(doc) is None
    assert 627 not in visited and 628 not in visited
    assert doc.calls==[]
