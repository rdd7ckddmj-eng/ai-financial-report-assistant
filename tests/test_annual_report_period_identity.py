"""Bounded native identity with source-bound fixtures; never an amount fallback."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import pytest
from src.annual_report_period_identity import (
    recover_annual_report_period_identity, validate_annual_identity_evidence,
    has_disallowed_report_title,
)
from src.china_stock import build_company_identity
from src.audited_company_onboarding import build_candidate_report_result
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.financial_report_reading_evidence import validated_reading_evidence

FIXTURE=json.loads((Path(__file__).parent/'fixtures/annual_report_period_identity_2025.json').read_text())
COMPANY=build_company_identity('601111','中国国航')
FINGERPRINT=FIXTURE['pdf_sha256']


def pages():
    selected={p['page_number']:p['text'] for p in FIXTURE['pages']}
    return [(n,selected.get(n,'')) for n in range(1,FIXTURE['physical_page_count']+1)]


def recover(sample=None, **kw):
    return recover_annual_report_period_identity(COMPANY,pages() if sample is None else sample,
        2025,pdf_fingerprint=kw.get('pdf_fingerprint',FINGERPRINT))


def replace_page(number, old, new):
    sample=pages();text=sample[number-1][1]
    assert old in text
    sample[number-1]=(number,text.replace(old,new))
    return sample


def manual_args():
    return dict(report_year=2025,source_url=FIXTURE['source_url'],published_date=FIXTURE['published_date'],
        identity_confirmed=True,today=date(2026,9,25))


def test_original_native_identity_binds_exact_slices_company_year_and_pdf():
    evidence=recover()
    assert evidence and evidence['pdf_fingerprint_sha256']==FINGERPRINT
    assert evidence['financial_cover_page']==70
    assert [s['page_number'] for s in evidence['sources']]==[3,5,6,7,7,70,77,80,84,72]
    assert evidence['human_verification']=='not_performed' and evidence['no_ocr'] is True
    assert validate_annual_identity_evidence(evidence,company=COMPANY,report_year=2025,
        pages=pages(),pdf_fingerprint=FINGERPRINT)
    assert validate_annual_identity_evidence(evidence,company=COMPANY,report_year=2025,pdf_fingerprint=FINGERPRINT)
    for p in FIXTURE['pages']:
        assert sha256(p['text'].encode()).hexdigest()==p['native_page_sha256']
    native=dict(pages())
    for source in evidence['sources']:
        assert native[source['page_number']][source['char_start']:source['char_end']]==source['excerpt']


def test_pdf_fingerprint_mismatch_is_rejected_by_helper_and_downstream():
    evidence=recover()
    assert not validate_annual_identity_evidence(evidence,pdf_fingerprint='0'*64)
    with pytest.raises(ValueError):
        validated_reading_evidence({'report_year':2025,'annual_identity_evidence':evidence},
            fingerprint='0'*64,company=COMPANY)
    assert validated_reading_evidence({'report_year':2025,'annual_identity_evidence':evidence},
        fingerprint=FINGERPRINT,company=COMPANY)['annual_identity_evidence']==evidence
    for bad in (None,'','123','G'*64):
        assert recover(pdf_fingerprint=bad) is None
    evidence.pop('pdf_fingerprint_sha256')
    assert not validate_annual_identity_evidence(evidence)


@pytest.mark.parametrize('page,old,new',[
    (6,'二〇二五年一月一日','二〇二四年一月一日'),
    (6,'二〇二五年十二月三十一日','二〇二五年六月三十日'),
    (6,'报告期\n指','报告期\n指\n报告期\n指'),
    (6,'报告期末','未知期间'),
    (7,'601111','601112'),
    (7,'中国国际航空股份有限公司','其他股份有限公司'),
    (7,'上海证券交易所','深圳证券交易所'),
    (70,'自2025','自2024'),
    (70,'中国国际航空股份有限公司','其他股份有限公司'),
    (77,'2025年12月31日','2024年12月31日'),
    (80,'2025年度','2024年度'),
    (80,'2024年','2025年'),
    (84,'2025年度','2025年半年度'),
    (78,'2025年12月31日','2024年12月31日'),
    (81,'中国国际航空股份有限公司','其他股份有限公司'),
    (85,'2024年','2025年'),
    (80,'171,484,646','171,,484,646'),
    (80,'166,698,880','166,698,880\n999'),
    (72,'包括2025年','包括2024年'),
])
def test_conflicting_missing_duplicate_or_broken_identity_is_rejected(page,old,new):
    assert recover(replace_page(page,old,new)) is None


@pytest.mark.parametrize('title',[
    '2025年度报告摘要','2025年年度报告摘要','2025年年报摘要','2025年年度报告（英文版）',
    '2025年半年度报告','2025年第三季度报告','2025年中期报告','2025 Annual Report English Version',
    '2025年度报告(摘要)','2025年度报告摘要(修订版)','中国国航2025年度报告摘要',
])
def test_front_ten_explicit_non_full_year_titles_cannot_bypass_manual_gate(monkeypatch,title):
    sample=pages();sample[2]=(3,title+'\n'+sample[2][1])
    assert has_disallowed_report_title(sample,company=COMPANY)
    assert recover(sample) is None
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *a,**kw:
        [dict(page_number=n,text=t) for n,t in sample])
    with pytest.raises(ValueError,match='中文完整年度报告'):
        build_manual_financial_snapshot(COMPANY,b'%PDF-test',**manual_args())


def test_prose_mentions_of_interim_report_are_not_titles():
    sample=pages();sample[2]=(3,sample[2][1]+'\n请参阅本公司半年度报告及其他公告。\n')
    assert not has_disallowed_report_title(sample)
    assert recover(sample)


def test_optional_image_audit_and_catalog_do_not_replace_native_statements():
    sample=pages();sample[71]=(72,'')
    evidence=recover(sample)
    assert evidence and len(evidence['sources'])==9
    sample[79]=(80,'')
    assert recover(sample) is None


def test_wrong_company_and_year_or_missing_full_page_sequence_do_not_recover():
    assert recover_annual_report_period_identity(build_company_identity('601112','其他公司'),pages(),
        2025,pdf_fingerprint=FINGERPRINT) is None
    assert recover_annual_report_period_identity(COMPANY,pages(),2024,pdf_fingerprint=FINGERPRINT) is None
    assert recover(pages()[1:]) is None
    assert recover(pages()[:80]) is None


def test_candidate_and_snapshot_keep_pdf_bound_identity_without_overriding_review_status(monkeypatch):
    pdf=b'%PDF-dedicated-unit-fixture'
    sample=[dict(page_number=n,text=t) for n,t in pages()]
    report=dict(report_year=2025,url=FIXTURE['source_url'],published_date=FIXTURE['published_date'],title='中国国航2025年年度报告')
    candidate=build_candidate_report_result(COMPANY,report,pdf,sample)
    evidence=candidate['annual_identity_evidence']
    assert evidence['pdf_fingerprint_sha256']==sha256(pdf).hexdigest()
    snapshot=build_on_demand_financial_snapshot(COMPANY,candidate)
    assert snapshot['report']['annual_identity_evidence']==evidence
    sample[1]['text']+='\n有关年度报告摘要的披露情况见后文。\n'
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *a,**kw:sample)
    manual=build_manual_financial_snapshot(COMPANY,pdf,**manual_args())
    assert manual['report']['annual_identity_evidence']==evidence
    assert manual['status']==snapshot['status']


@pytest.mark.parametrize('field,value',[('report_year',2024),('company_code','601112'),
    ('human_verification','approved'),('no_ocr',False),('financial_cover_page',71)])
def test_evidence_metadata_tampering_is_rejected(field,value):
    evidence=deepcopy(recover());evidence[field]=value
    assert not validate_annual_identity_evidence(evidence,company=COMPANY,report_year=2025,pdf_fingerprint=FINGERPRINT)
