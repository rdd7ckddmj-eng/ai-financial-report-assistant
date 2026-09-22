"""Explicit, bounded public-source sampling; never a full-market coverage claim.

Run: python -m src.public_financial_coverage_audit --codes 000651 600036
No network request occurs on import. Individual failures remain in the receipt.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from src.bse_code_migrations import current_bse_code
from src.china_stock import build_company_identity, DataSourceError
from src.public_financial_history import fetch_public_financial_history, validate_public_financial_history

MAX_SAMPLE_COMPANIES = 20
CORE_FIELDS = ('revenue', 'net_profit', 'operating_cash_flow', 'total_assets', 'total_liabilities')


def audit_public_financial_coverage(codes, *, fetcher=None, on_result=None):
    if not isinstance(codes, (list, tuple)) or not 1 <= len(codes) <= MAX_SAMPLE_COMPANIES:
        raise ValueError('每次抽查需要1至20个不同代码，不能默认遍历全市场。')
    companies = [build_company_identity(code) for code in codes]
    if len({c['canonical_code'] for c in companies}) != len(companies):
        raise ValueError('抽查公司代码不能重复。')
    fetcher = fetcher or fetch_public_financial_history
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    rows = []
    for company in companies:
        receipt = dict(canonical_code=company['canonical_code'], exchange=company['exchange'])
        try:
            history = validate_public_financial_history(fetcher(company))
            if history['company']['canonical_code'] != company['canonical_code']:
                raise ValueError('返回的数据属于其他公司。')
            latest = history['points'][-1]
            field_gaps = [dict(year=p['period_year'], fields=[k for k in CORE_FIELDS if p[k] is None])
                          for p in history['points'] if any(p[k] is None for k in CORE_FIELDS)]
            balance_failures = [p['period_year'] for p in history['points'] if p['balance_check']=='failed']
            stale = latest['period_year'] < datetime.fromisoformat(history['fetched_at']).year - 1
            receipt.update(status='partial' if field_gaps or balance_failures or stale else 'available',
                source_name=history['source_rows'][-1]['SECURITY_NAME_ABBR'],
                org_type=latest['org_type'], years=[p['period_year'] for p in history['points']],
                core_field_gaps=field_gaps, balance_failures=balance_failures,
                latest_year_lag=stale, fetched_at=history['fetched_at'],
                public_fingerprint=history['fingerprint'], source_url=history['source_url'],
                generic_cash_rule_enabled=latest['org_type']=='通用',
                sector_fields_present=[k for k,v in latest['sector_metrics_percent'].items() if v is not None],
                issues=history['issues'])
        except (DataSourceError, ValueError, TypeError, KeyError) as error:
            receipt.update(status='unavailable', reason=str(error)[:800])
            migrated = current_bse_code(company['code'])
            if migrated != company['code']:
                receipt['suggested_current_code'] = migrated
                receipt['code_mapping_source'] = 'https://www.bse.cn/service/code_mapping.html'
        rows.append(receipt)
        if on_result is not None:
            on_result(dict(receipt))
    counts = Counter(row['status'] for row in rows)
    return dict(schema='public-financial-coverage-sample.v1', started_at=started,
        completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        requested_count=len(companies), counts={k:counts[k] for k in ('available','partial','unavailable')},
        rows=rows, limitation='仅代表本次指定代码与当前公开接口的抽样可用性；available不是官方核验或全市场覆盖率。少于六年不自动认定缺失，因为上市前历史和披露范围需要另查。')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codes', nargs='+', required=True, help='1至20个不同的六位A股代码')
    parser.add_argument('--output', type=Path, help='可选的新JSON文件；拒绝覆盖已有文件')
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        parser.error('输出文件已经存在；请选择新文件名。')
    try:
        result = audit_public_financial_coverage(args.codes)
    except ValueError as error:
        parser.error(str(error))
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        with args.output.open('x', encoding='utf-8') as handle:
            handle.write(text+'\n')
    print(text)
    return 1 if result['counts']['unavailable'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
