"""Read-only publication of complete-PDF test results, never a review gate.

This catalogue describes exact source versions tested before a release. It
cannot make an uploaded report pass, identify a current issuer, or approve a
financial value. It performs no network requests and contains no local paths.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from src.china_stock import build_company_identity, is_allowed_disclosure_url

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data/reference/annual_report_coverage.json'
SCHEMA = 'complete-annual-report-test-catalog.v1'
MAX_BYTES = 1_000_000
MAX_REPORTS = 1000
CHECKS = frozenset(('income_statement_reconciled', 'balance_sheet_reconciled', 'cash_flow_statement_reconciled'))
METRICS = frozenset(('revenue', 'net_profit', 'operating_cash_flow', 'total_assets', 'total_liabilities'))
STATUSES = {'ready_for_human_review': '自动检查通过，待人工复核', 'needs_review': '暂未通过自动检查'}
_HASH = re.compile(r'[a-f0-9]{64}')


def _text(value, maximum):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= maximum
            and not any(ord(c) < 32 for c in value))


def validate_coverage_catalog(catalog):
    """Reject a misleading or damaged register instead of publishing part of it."""
    error = '完整年报测试范围记录不完整或不一致。'
    if (not isinstance(catalog, dict) or catalog.get('schema') != SCHEMA
            or catalog.get('scope') != 'exact_complete_pdf_versions'
            or catalog.get('human_verification') != 'not_performed'
            or not isinstance(catalog.get('receipt_sha256'), str)
            or not _HASH.fullmatch(catalog['receipt_sha256'])):
        raise ValueError(error)
    try:
        tested = datetime.fromisoformat(catalog['tested_at'])
        if tested.tzinfo is None or tested > datetime.now(timezone.utc):
            raise ValueError(error)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    reports = catalog.get('reports')
    if not isinstance(reports, list) or not 1 <= len(reports) <= MAX_REPORTS:
        raise ValueError(error)
    seen = set()
    for row in reports:
        if not isinstance(row, dict):
            raise ValueError(error)
        code = row.get('canonical_code')
        try:
            if not isinstance(code, str) or build_company_identity(code[:6])['canonical_code'] != code:
                raise ValueError(error)
            published = date.fromisoformat(row['published_date'])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(error) from exc
        year, fingerprint = row.get('report_year'), row.get('source_sha256')
        if (type(year) is not int or not 1990 <= year < tested.year
                or not date(year, 12, 31) < published <= tested.date()
                or not _text(row.get('company_name'), 80)
                or not _text(row.get('reason'), 800)
                or not isinstance(fingerprint, str) or not _HASH.fullmatch(fingerprint)
                or fingerprint in seen or not isinstance(row.get('status'), str) or row['status'] not in STATUSES
                or type(row.get('page_count')) is not int or not 1 <= row['page_count'] <= 1000
                or not _text(row.get('source_url'), 800) or not is_allowed_disclosure_url(row['source_url'])
                or row.get('human_verification') != 'not_performed'
                or not isinstance(row.get('statement_template'), str)
                or not re.fullmatch(r'[a-z][a-z0-9_]{0,100}', row['statement_template'])):
            raise ValueError(error)
        checks = row.get('statement_checks')
        if (not isinstance(checks, dict) or set(checks) != CHECKS
                or any(type(v) is not bool for v in checks.values())
                or (row['status'] == 'ready_for_human_review' and not all(checks.values()))):
            raise ValueError(error)
        if set(row) != {'canonical_code', 'company_name', 'report_year', 'published_date', 'source_url',
                        'source_sha256', 'page_count', 'status', 'statement_template', 'statement_checks',
                        'reason', 'human_verification'}:
            raise ValueError(error)
        seen.add(fingerprint)
    return deepcopy(catalog)


def load_coverage_catalog(path=None):
    """Load a bounded local release artifact; entering the UI never fetches PDFs."""
    try:
        with Path(path or CATALOG_PATH).open('rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('完整年报测试范围记录超过读取上限。')
        return validate_coverage_catalog(json.loads(data))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('完整年报测试范围暂时无法读取。') from exc


def coverage_summary(catalog):
    reports = catalog['reports']
    counts = Counter(r['status'] for r in reports)
    return dict(report_versions=len(reports), companies=len({r['canonical_code'] for r in reports}),
                candidates=counts['ready_for_human_review'], needs_review=counts['needs_review'])


def reports_for_company(catalog, company):
    expected = build_company_identity(str(company.get('code', '')))['canonical_code']
    if company.get('canonical_code') != expected:
        raise ValueError('当前公司代码与交易所不一致。')
    return deepcopy(sorted((r for r in catalog['reports'] if r['canonical_code'] == expected),
                           key=lambda r: (r['report_year'], r['published_date'], r['source_sha256']), reverse=True))


def sample_company_identity(company, catalog):
    """Fill only an unknown display name, from uniquely named historical samples.

    The UI labels this as a historical name; all actual report identity checks
    still run. Never replace a name supplied by the user or a live directory.
    """
    reports = reports_for_company(catalog, company)
    names = {r['company_name'] for r in reports}
    if company.get('name') == '待核验公司' and len(names) == 1:
        return build_company_identity(company['code'], names.pop())
    return dict(company)


def build_coverage_catalog(manifest, receipt):
    """Compile matching full-run receipts; no summaries, dropped failures or paths."""
    entries, rows = manifest.get('reports'), receipt.get('rows')
    if (receipt.get('schema') != 'financial-coverage-multibatch-receipt.v1'
            or not isinstance(entries, list) or not isinstance(rows, list)
            or not 1 <= len(entries) == len(rows) <= MAX_REPORTS
            or receipt.get('human_verified_new') != 0):
        raise ValueError('只能登记有逐份结果的完整年报批次。')
    by_path = {e['path']: e for e in entries}
    if len(by_path) != len(entries):
        raise ValueError('原件清单包含重复路径。')
    seen_paths, reports = set(), []
    for row in rows:
        path = row.get('path')
        entry = by_path.get(path)
        if (not entry or path in seen_paths or entry.get('identity_confirmed') is not True
                or row.get('layer') != 'report' or row.get('human_verification') != 'not_performed'
                or row.get('canonical_code') != build_company_identity(entry['code'])['canonical_code']
                or row.get('report_year') != entry['year'] or row.get('source_url') != entry['source_url']):
            raise ValueError('批次结果与原件清单的身份、年度或来源不一致。')
        if row.get('status') == 'ready_for_human_review':
            metrics = row.get('metrics', [])
            if (not isinstance(metrics, list) or len(metrics) != 5 or {m.get('key') for m in metrics} != METRICS
                    or any(type(m.get(period)) not in (int, float) or not math.isfinite(m[period])
                           for m in metrics for period in ('current_yuan', 'previous_yuan'))):
                raise ValueError('候选缺少完整的两期五项金额，不能登记通过。')
        reports.append(dict(canonical_code=row['canonical_code'], company_name=entry['name'],
            report_year=entry['year'], published_date=entry['published_date'], source_url=entry['source_url'],
            source_sha256=row.get('fingerprint'), page_count=row.get('page_count'), status=row.get('status'),
            statement_template=row.get('statement_template'), statement_checks=row.get('statement_checks'),
            reason=('该原件通过本次自动检查，财务金额仍需逐项人工复核。' if row['status']=='ready_for_human_review'
                    else row.get('reason') or '金额或单位证据不足，请保留缺口并查看原文。'),
            human_verification='not_performed'))
        seen_paths.add(path)
    payload = dict(schema=SCHEMA, scope='exact_complete_pdf_versions', tested_at=receipt['completed_at'],
                   human_verification='not_performed', reports=reports,
                   receipt_sha256=sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest())
    return validate_coverage_catalog(payload)
