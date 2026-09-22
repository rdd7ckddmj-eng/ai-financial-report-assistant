"""Bounded fallback from a user-supplied public annual report to a snapshot."""
from datetime import date, datetime, timezone
import re

from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import build_company_identity, is_allowed_disclosure_url
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.pdf_extractor import extract_pdf_pages
from src.pdf_resource_policy import MANUAL_PDF_MAX_BYTES


def build_manual_financial_snapshot(company, pdf_bytes, *, report_year, source_url,
                                    published_date, identity_confirmed, today=None):
    today = today or datetime.now(timezone.utc).date()
    canonical = build_company_identity(str(company.get('code', '')))['canonical_code']
    if company.get('canonical_code') != canonical:
        raise ValueError('公司代码与交易所不一致。')
    if identity_confirmed is not True:
        raise ValueError('请先核对并确认上传报告、公司、年度及官方来源对应。')
    if type(report_year) is not int or not 1990 <= report_year < today.year:
        raise ValueError('请选择已经结束的完整财务年度。')
    if not isinstance(source_url, str) or len(source_url.strip()) > 800 or not is_allowed_disclosure_url(source_url.strip()):
        raise ValueError('请填写受支持的交易所或巨潮资讯HTTPS官方原文链接。')
    try:
        published = date.fromisoformat(str(published_date))
    except ValueError as error:
        raise ValueError('请填写报告的真实公告日期。') from error
    if not date(report_year, 12, 31) < published <= today:
        raise ValueError('公告日期必须晚于报告年度结束，且不能晚于今天。')
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b'%PDF'):
        raise ValueError('请上传有效的公开年度报告PDF。')
    if len(pdf_bytes) > MANUAL_PDF_MAX_BYTES:
        raise ValueError('手工年报不能超过32 MB。')
    pages = extract_pdf_pages(pdf_bytes, max_bytes=MANUAL_PDF_MAX_BYTES)
    front = re.sub(r'\s+', '', '\n'.join(p['text'] for p in pages[:10]))
    heading = re.sub(r'\s+', '', '\n'.join(p['text'] for p in pages[:2]))
    if '年度报告摘要' in heading or '年度报告英文' in heading:
        raise ValueError('请上传中文完整年度报告，摘要或英文版本不能替代完整年报。')
    chinese_year = ''.join('零一二三四五六七八九'[int(d)] for d in str(report_year))
    chinese_title = re.search(rf'{chinese_year}年(?:年报|年度报告)', front)
    if '年报摘要' in heading or '年报英文' in heading:
        raise ValueError('请上传中文完整年度报告，摘要或英文版本不能替代完整年报。')
    if not re.search(rf'{report_year}年?年度报告', front) and not chinese_title:
        raise ValueError('前十页未识别到所选年度的完整年报标题，不能仅凭文件名确定年度。')
    code_found = re.search(rf'(?<!\d){re.escape(str(company["code"]))}(?!\d)', front)
    name = str(company.get('name', '')).strip()
    name_found = len(name) >= 3 and name != '待核验公司' and name in front
    if not code_found and not name_found:
        raise ValueError('前十页未找到当前公司代码或名称，请检查是否选错公司或报告。')
    report = dict(report_year=report_year, published_date=published.isoformat(),
                  title=f'{name}{report_year}年年度报告（手工上传候选）',url=source_url.strip())
    candidate = build_candidate_report_result(company, report, pdf_bytes, pages)
    snapshot = build_on_demand_financial_snapshot(company, candidate)
    snapshot['limitations'].append('手工上传：官方链接和公告日期由用户提供，未联网比对该链接的PDF与上传文件；公司及年度仍需人工复核。')
    snapshot['input_provenance'] = 'user_uploaded_official_report_candidate'
    return snapshot
