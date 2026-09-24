"""Match a small local register of official restatement explanations.

A match adds provenance only. It never changes a comparison status, replaces
an annual-report amount, or records a human verification. No network is used.
"""
from copy import deepcopy
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from src.china_stock import build_company_identity


REGISTRY_PATH = Path(__file__).resolve().parents[1] / 'data/reference/official_restatement_evidence.json'
REGISTRY_SCHEMA = 'official-restatement-evidence.v1'
EVIDENCE_STATUS = 'registered_official_restatement_explanation'
DUAL_SOURCE_BASIS = 'annual_original_to_subsequent_restated'
_SHA = re.compile(r'[0-9a-f]{64}')
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?')
_OFFICIAL_HOSTS = frozenset({
    'static.cninfo.com.cn', 'www.sse.com.cn', 'static.sse.com.cn',
    'www.szse.cn', 'www.bse.cn',
})
_UNITS = {'人民币元': Decimal(1), '人民币千元': Decimal(1000),
          '人民币万元': Decimal(10000), '人民币百万元': Decimal(1000000)}


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('金额必须是明确的有限十进制数。')
    if isinstance(value, str) and (len(value) > 64 or not _NUMBER.fullmatch(value)):
        raise ValueError('金额字符串不能含分隔符、空白或其他说明。')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError('金额格式无效。') from error
    if not result.is_finite() or result.copy_abs() > Decimal('1e24'):
        raise ValueError('金额不是支持范围内的有限数。')
    return result


def _canonical(code):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}\.(SH|SZ|BJ)', code):
        return False
    try:
        return build_company_identity(code[:6])['canonical_code'] == code
    except ValueError:
        return False


def _required_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError('登记文字字段不完整。')


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('登记日期必须为YYYY-MM-DD。')
    return date.fromisoformat(value)


def _pages(value, page_count):
    if (not isinstance(value, list) or not value
            or any(type(n) is not int or not 1 <= n <= page_count for n in value)
            or value != sorted(set(value))):
        raise ValueError('原文物理页码必须完整、唯一且在全文范围内。')


def _report(report, *, subsequent, dual_source=False):
    if not isinstance(report, dict):
        raise ValueError('缺少原文报告信息。')
    _required_text(report.get('title'))
    published = _date(report.get('published_date'))
    sha = report.get('sha256')
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError('缺少完整的原文SHA-256。')
    url = report.get('source_url')
    if not isinstance(url, str) or len(url) > 800 or any(c.isspace() for c in url):
        raise ValueError('官方PDF地址无效。')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc not in _OFFICIAL_HOSTS
            or not parsed.path.lower().endswith('.pdf') or parsed.query or parsed.fragment):
        raise ValueError('只允许登记受支持官方站点的HTTPS PDF原文地址。')
    count = report.get('page_count')
    if type(count) is not int or not 1 <= count <= 5000:
        raise ValueError('原文全文页数无效。')
    _pages(report.get('amount_pages'), count)
    if subsequent:
        _pages(report.get('explanation_pages'), count)
    unit = report.get('amount_unit')
    if not isinstance(unit, str) or unit not in _UNITS:
        raise ValueError('原始金额单位不受支持。')
    if subsequent and dual_source:
        # The original amount belongs to the annual PDF, not to a later page
        # that only discloses the restated comparative. Reject even null here.
        if 'before_value' in report:
            raise ValueError('双源证据不得将原年报金额记为后续报告的调整前值。')
        amount_keys = ('after_value',)
    else:
        amount_keys = ('before_value', 'after_value') if subsequent else ('amount_value',)
    for key in amount_keys:
        if not isinstance(report.get(key), str):
            raise ValueError('登记金额必须使用十进制字符串。')
        _amount(report[key])
    return published


def _dual_source_context(entry, annual, subsequent):
    """Bind each balance to its own company, year-end, row and table column."""
    labels = {
        'total_assets': ('资产总计', '资产总额', '总资产'),
        'total_liabilities': ('负债合计', '负债总计', '总负债'),
    }
    if entry['metric_key'] not in labels:
        raise ValueError('双源证据目前仅支持年末合并资产与负债。')
    for report, column in ((annual, 'annual_current'), (subsequent, 'restated_comparative')):
        if (report.get('company_code') != entry['company_code']
                or report.get('amount_period_end') != entry['period_end']
                or report.get('amount_label') not in labels[entry['metric_key']]
                or report.get('amount_column') != column
                or report.get('statement_scope') != 'consolidated'
                or report.get('accounting_basis') != 'china_accounting_standards'):
            raise ValueError('双源金额的公司、时点、指标或合并比较列口径不一致。')
    if annual['sha256'] == subsequent['sha256'] or annual['source_url'] == subsequent['source_url']:
        raise ValueError('双源证据必须分别指向原年报和后续披露原件。')


def validate_official_restatement_registry(data):
    """Validate every record; a damaged register must not yield partial matches."""
    if not isinstance(data, dict) or data.get('schema') != REGISTRY_SCHEMA:
        raise ValueError('重述证据登记版本无效。')
    entries = data.get('entries')
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError('重述证据登记条目无效。')
    ids, keys = set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('重述证据条目不是对象。')
        identifier = entry.get('evidence_id')
        _required_text(identifier)
        if identifier in ids or not _canonical(entry.get('company_code')):
            raise ValueError('证据ID重复或公司代码与交易所不一致。')
        ids.add(identifier)
        _required_text(entry.get('company_name'))
        year = entry.get('report_year')
        if type(year) is not int or not 1990 <= year <= 2100:
            raise ValueError('原年度报告年份无效。')
        period_end = _date(entry.get('period_end'))
        if period_end != date(year, 12, 31):
            raise ValueError('重述比较时点与原年报年度不一致。')
        if entry.get('metric_key') not in ('total_assets', 'total_liabilities', 'revenue'):
            raise ValueError('当前登记只支持已查证的资产、负债与营业收入指标。')
        if (entry.get('status') != EVIDENCE_STATUS or entry.get('effect') != 'explanation_only'
                or entry.get('human_verification') != 'not_performed'):
            raise ValueError('重述线索不能转换为金额一致或人工确认。')
        _required_text(entry.get('explanation'))
        limitations = entry.get('limitations')
        if not isinstance(limitations, list) or not limitations:
            raise ValueError('缺少重述证据的使用边界。')
        for item in limitations:
            _required_text(item)
        basis = entry.get('evidence_basis')
        if 'evidence_basis' in entry and basis != DUAL_SOURCE_BASIS:
            raise ValueError('重述金额来源模式无效。')
        dual_source = basis == DUAL_SOURCE_BASIS
        annual, subsequent = entry.get('annual_report'), entry.get('subsequent_report')
        annual_date = _report(annual, subsequent=False)
        subsequent_date = _report(subsequent, subsequent=True, dual_source=dual_source)
        if annual_date <= period_end or subsequent_date < annual_date:
            raise ValueError('后续披露与原年报的日期顺序无效。')
        if dual_source:
            _dual_source_context(entry, annual, subsequent)
        for field in ('annual_yuan', 'restated_yuan', 'difference_yuan'):
            if not isinstance(entry.get(field), str):
                raise ValueError('人民币金额必须使用十进制字符串。')
        with localcontext() as context:
            context.prec = 80
            before, after = _amount(entry['annual_yuan']), _amount(entry['restated_yuan'])
            if (before == after or _amount(entry['difference_yuan']) != after - before
                    or _amount(annual['amount_value']) * _UNITS[annual['amount_unit']] != before
                    or (not dual_source and _amount(subsequent['before_value']) * _UNITS[subsequent['amount_unit']] != before)
                    or _amount(subsequent['after_value']) * _UNITS[subsequent['amount_unit']] != after):
                raise ValueError('原值、重述前后值、单位换算或差额不一致。')
        key = (entry['company_code'], year, annual['sha256'], entry['metric_key'])
        if key in keys:
            raise ValueError('同一原文指标存在歧义登记。')
        keys.add(key)
    return deepcopy(entries)


def _registry():
    raw = REGISTRY_PATH.read_text(encoding='utf-8')
    if len(raw) > 256000:
        raise ValueError('本地证据登记超过支持大小。')
    return validate_official_restatement_registry(json.loads(raw))


def match_official_restatement_evidence(company_code, report_year, annual_fingerprint,
                                       metric_key, annual_yuan, public_yuan):
    """Return an independent evidence dict only for an exact six-field match.

    Amounts are compared with Decimal, without rounding or tolerance. Float
    inputs use their decimal string representation, matching production JSON
    numbers. Missing/malformed inputs or an unavailable register return None.
    """
    if (not _canonical(company_code) or type(report_year) is not int
            or not isinstance(annual_fingerprint, str) or not _SHA.fullmatch(annual_fingerprint)
            or metric_key not in ('total_assets', 'total_liabilities', 'revenue')):
        return None
    try:
        annual_amount, public_amount = _amount(annual_yuan), _amount(public_yuan)
        entries = _registry()
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation):
        return None
    for entry in entries:
        if (entry['company_code'] == company_code and entry['report_year'] == report_year
                and entry['annual_report']['sha256'] == annual_fingerprint
                and entry['metric_key'] == metric_key
                and _amount(entry['annual_yuan']) == annual_amount
                and _amount(entry['restated_yuan']) == public_amount):
            return entry
    return None


def validated_stored_restatement_evidence(comparison, row):
    """Validate an explanation against its stored receipt, without any lookup.

    This checks internal consistency, not authenticity or human verification.
    It never loads the current register, updates historical evidence, or fetches
    a report. Missing or damaged stored fields return None.
    """
    if (not isinstance(comparison, Mapping) or not isinstance(row, Mapping)
            or comparison.get('schema') not in (
                'public-financial-reconciliation.v1',
                'public-financial-reconciliation-artifact.v1')
            or row.get('status') != 'amount_difference'):
        return None
    company = comparison.get('company')
    evidence = row.get('official_restatement_evidence')
    if not isinstance(company, Mapping) or not isinstance(evidence, dict):
        return None
    try:
        # Use only the evidence saved with this receipt. Do not call _registry
        # or match_official_restatement_evidence when displaying old records.
        saved = validate_official_restatement_registry({
            'schema': REGISTRY_SCHEMA, 'entries': [evidence],
        })[0]
        annual = saved['annual_report']
        if (company.get('canonical_code') != saved['company_code']
                or type(comparison.get('report_year')) is not int
                or comparison['report_year'] != saved['report_year']
                or comparison.get('annual_pdf_fingerprint') != annual['sha256']
                or comparison.get('annual_source_url') != annual['source_url']
                or comparison.get('annual_published_date') != annual['published_date']
                or row.get('key') != saved['metric_key']):
            return None
        with localcontext() as context:
            context.prec = 80
            candidate = _amount(row.get('annual_candidate_yuan'))
            public = _amount(row.get('public_yuan'))
            difference = _amount(row.get('difference_yuan'))
            if (candidate != _amount(saved['annual_yuan'])
                    or public != _amount(saved['restated_yuan'])
                    or difference != candidate - public
                    or difference != -_amount(saved['difference_yuan'])):
                return None
        return saved
    except (ValueError, TypeError, KeyError, InvalidOperation):
        return None
