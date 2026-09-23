"""Compare vendor annual amounts with an official-PDF extraction candidate.

Neither source is promoted to a verified fact. Only the report's current-year
column is compared; prior columns may be restated and have a different vintage.
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from src.audited_company_onboarding import rmb_unit_multiplier
from src.china_stock import build_company_identity, is_allowed_disclosure_url
from src.financial_snapshot_review import CORE_METRIC_KEYS
from src.public_financial_history import AMOUNT_FIELDS, validate_public_financial_history
from src.insurance_group_statement_extractor import TOTAL_REVENUE_TEMPLATES
from src.financial_sector_policy import SECURITIES_REVENUE_TEMPLATES

LIMITATION = (
    "这是公开源与官方PDF自动提取候选的金额对照，不是人工核验。"
    "金额相近不能证明公司、报表口径或提取正确；差异也不能直接认定某个来源错误。"
    "公开源可能重述，归母利润与合并净利润、营业收入与营业总收入不能混用。"
)


def _number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("金额不能是布尔值。")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("金额格式不正确。") from error
    if not number.is_finite() or number.copy_abs() > Decimal('1e100'):
        raise ValueError("金额必须是合理范围内的有限数值。")
    return number


def build_public_financial_reconciliation(history, snapshot):
    history = validate_public_financial_history(history)
    if not isinstance(snapshot, Mapping):
        raise ValueError("缺少年报快照。")
    company = snapshot.get('company')
    if not isinstance(company, Mapping):
        raise ValueError("年报快照缺少公司身份。")
    canonical = build_company_identity(str(company.get('code', '')))['canonical_code']
    if canonical != company.get('canonical_code') or canonical != history['company']['canonical_code']:
        raise ValueError("只能对照同一家公司的资料。")
    report = snapshot.get('report')
    if not isinstance(report, Mapping) or not is_allowed_disclosure_url(str(report.get('source_url', ''))):
        raise ValueError("年报快照缺少可信官方来源。")
    year = report.get('report_year')
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValueError("年报年度无效。")
    point = next((p for p in history['points'] if p['period_year'] == year), None)
    if point is None:
        raise ValueError("公开数据没有该年报的同一年度，不能使用其他年度替代。")
    fingerprint = snapshot.get('source_fingerprint_sha256', '')
    if not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-fA-F]{64}', fingerprint):
        raise ValueError("缺少有效的年报PDF指纹，请重新生成快照。")
    page_count = report.get('page_count')
    if type(page_count) is not int or page_count <= 0:
        raise ValueError("年报PDF页数无效，请重新生成快照。")
    metrics = snapshot.get('metrics')
    if (not isinstance(metrics, list) or len(metrics) != len(CORE_METRIC_KEYS)
        or any(not isinstance(m, Mapping) for m in metrics)
        or {m.get('key') for m in metrics} != set(CORE_METRIC_KEYS)):
        raise ValueError("年报快照必须包含五个不同的核心指标。")
    checks = snapshot.get('statement_checks', {})
    checked = isinstance(checks, Mapping) and all(checks.get(k) is True for k in (
        'income_statement_reconciled', 'balance_sheet_reconciled', 'cash_flow_statement_reconciled'))
    rows = []
    for key in CORE_METRIC_KEYS:
        metric = next(m for m in metrics if m['key'] == key)
        source = metric.get('source')
        source = source if isinstance(source, Mapping) else {}
        public_key = ('total_operating_revenue' if key == 'revenue' and report.get('statement_template') in TOTAL_REVENUE_TEMPLATES | SECURITIES_REVENUE_TEMPLATES else key)
        public = _number(point[public_key])
        candidate = _number(metric.get('current_yuan'))
        raw = _number(source.get('raw_current_value'))
        reasons = []
        expected_org = "保险" if report.get("statement_template") in TOTAL_REVENUE_TEMPLATES else "证券"
        if public_key != key and point.get("org_type") != expected_org:
            reasons.append(expected_org+"年报与公开源机构类型不一致，需核验收入口径")
        multiplier = None
        try:
            multiplier = Decimal(str(rmb_unit_multiplier(source.get('original_unit'))))
        except ValueError:
            reasons.append('年报原始人民币单位缺失或不受支持')
        # Half of one hundredth of the statement's declared unit, minimum ¥1.
        # A percentage tolerance would conceal material differences at large scale.
        tolerance = max(Decimal('1'), multiplier * Decimal('0.005')) if multiplier else None
        if not checked or snapshot.get('status') != 'ready_for_human_review':
            reasons.append('快照三表或单位检查尚未通过')
        if public is None or candidate is None or raw is None:
            reasons.append('公开值、年报换算值或原始金额缺失')
        if raw is not None and candidate is not None and multiplier is not None:
            if abs(raw * multiplier - candidate) > Decimal('0.01'):
                reasons.append('年报原值与人民币换算值不一致')
        delta = candidate - public if not reasons else None
        status = 'not_comparable' if reasons else ('amount_close' if abs(delta) <= tolerance else 'amount_difference')
        pages = source.get('pages')
        if not (isinstance(pages, Mapping) and type(pages.get('start')) is int and type(pages.get('end')) is int
                and 1 <= pages['start'] <= pages['end'] <= page_count):
            pages = None
        basis = str(source.get('accounting_basis', '口径待确认'))[:160]
        excerpt = str(source.get('excerpt', ''))[:480]
        tasks = list(reasons)
        if pages is None or not excerpt:
            tasks.append('补充年报页码与对应原文摘录')
        tasks.append('核对合并/母公司、本期列、原始单位及更正版本')
        if key == 'net_profit':
            tasks.append('公开值为归母净利润；快照可能提取合并净利润，需核对具体行名')
        if key == 'revenue' and public_key == key:
            tasks.append('核对营业收入行，不能用营业总收入替代')
        if status == 'amount_difference':
            tasks.append('先查提取行列、口径及年报更正，再判断差异原因；不要自动覆盖任一来源')
        rows.append(dict(key=key, public_field=public_key, label=AMOUNT_FIELDS[public_key][1], status=status,
            public_yuan=float(public) if public is not None else None,
            annual_candidate_yuan=float(candidate) if candidate is not None else None,
            difference_yuan=float(delta) if delta is not None else None,
            tolerance_yuan=float(tolerance) if tolerance is not None else None,
            original_unit=str(source.get('original_unit', ''))[:40], pages=dict(pages) if pages else None,
            annual_basis=basis, excerpt=excerpt, verification_tasks=tasks))
    result = dict(schema='public-financial-reconciliation.v1', status='pending_human_review',
        company=history['company'], report_year=year, public_source_url=history['source_url'],
        public_fetched_at=history['fetched_at'], public_updated_date=point['updated_date'],
        public_fingerprint=history['fingerprint'], annual_source_url=report['source_url'],
        annual_published_date=report.get('published_date'), annual_pdf_fingerprint=fingerprint,
        rows=rows, limitation=LIMITATION,
        annual_input_provenance=('user_uploaded_official_report_candidate' if snapshot.get('input_provenance') == 'user_uploaded_official_report_candidate' else 'not_recorded'),
        tolerance_rule='允许差值为原始年报单位的0.005，最低1元；只描述金额接近，不确认报表口径。')
    result['fingerprint'] = sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return result
