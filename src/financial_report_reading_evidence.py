"""Keep PDF reading evidence bound to the original and reporting period."""
from copy import deepcopy
from hashlib import sha256
import json
from src.pdf_actualtext_recovery import validate_native_text_recoveries


def validated_reading_evidence(report, *, fingerprint, company=None):
    result = {}
    if 'pdf_native_text_recoveries' in report:
        records = validate_native_text_recoveries(report['pdf_native_text_recoveries'],
            pdf_fingerprint=fingerprint, report_year=report['report_year'])
        if records:
            result['pdf_native_text_recoveries'] = records
    if report.get('annual_identity_evidence'):
        from src.annual_report_period_identity import validate_annual_identity_evidence
        evidence = report['annual_identity_evidence']
        if not validate_annual_identity_evidence(evidence, company=company, report_year=report['report_year'], pdf_fingerprint=fingerprint):
            raise ValueError('年报年度与主体交叉证据不完整，不能继续标准化。')
        result['annual_identity_evidence'] = deepcopy(evidence)
    return result


def compact_reading_evidence(report, *, fingerprint, company=None):
    """Reference full workpaper evidence without raising the 8KB case limit."""
    evidence = validated_reading_evidence(report, fingerprint=fingerprint, company=company)
    if not evidence:
        return {}
    raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    summary = dict(schema='financial-reading-evidence-reference.v1', evidence_sha256=sha256(raw).hexdigest(),
        source_fingerprint_sha256=fingerprint, report_year=report['report_year'],
        note='完整原文、读取结果及结构依据保留在原复核底稿；此处仅保存可核对的摘要与哈希，自动读取不代表人工确认。')
    records = evidence.get('pdf_native_text_recoveries', [])
    if records:
        summary['native_pages'] = [{k:r[k] for k in ('page_number','original_text_sha256','native_text_sha256')}
                                   for r in records]
        summary['method'] = 'pymupdf_ignore_actualtext'
    if evidence.get('annual_identity_evidence'):
        summary['annual_identity_cross_checked'] = True
    return {'reading_evidence_reference': summary}
