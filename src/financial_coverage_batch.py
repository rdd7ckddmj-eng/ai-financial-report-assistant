"""Explicit-manifest batch audit. No downloads or network activity on import.

Run with --manifest plan.json --output new-receipt.json --layer all/public/reports.
Public requests remain serial in groups of at most 20. Each result is flushed to
an exclusive JSONL journal before the final summary; existing files are refused.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from src.china_stock import build_company_identity
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.pdf_resource_policy import MANUAL_PDF_MAX_BYTES
from src.public_financial_coverage_audit import audit_public_financial_coverage

MAX_COMPANIES = 200
MAX_REPORTS = 40


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError('批次清单必须是对象。')
    codes, reports = manifest.get('codes', []), manifest.get('reports', [])
    if not isinstance(codes, list) or len(codes) > MAX_COMPANIES:
        raise ValueError('公开源批次最多200个明确指定的公司代码。')
    identities = [build_company_identity(code)['canonical_code'] for code in codes]
    if len(set(identities)) != len(identities):
        raise ValueError('公开源公司代码重复。')
    if not isinstance(reports, list) or len(reports) > MAX_REPORTS:
        raise ValueError('每批最多40份明确指定的本地年报。')
    seen = set()
    for report in reports:
        if not isinstance(report, dict) or not {'code','name','year','path','source_url','published_date','identity_confirmed'} <= report.keys():
            raise ValueError('年报条目缺少身份、来源或路径。')
        code = build_company_identity(report['code'])['canonical_code']
        if type(report['year']) is not int or not isinstance(report['path'], str):
            raise ValueError('年报年度或路径无效。')
        key = code, report['year'], str(Path(report['path']).resolve())
        if key in seen:
            raise ValueError('年报条目重复。')
        seen.add(key)
    if not codes and not reports:
        raise ValueError('批次清单不能为空。')
    return codes, reports


def audit_coverage_batch(manifest, *, layer='all', fetcher=None,
                         snapshot_builder=None, on_result=None):
    codes, reports = validate_manifest(manifest)
    if layer not in ('all', 'public', 'reports'):
        raise ValueError('未知检查层。')
    if (layer == 'public' and not codes) or (layer == 'reports' and not reports):
        raise ValueError('所选检查层没有样本，不能生成成功回执。')
    started = datetime.now(timezone.utc).isoformat()
    rows = []

    def emit(row):
        rows.append(row)
        if on_result:
            on_result(row)

    if layer in ('all', 'public'):
        for start in range(0, len(codes), 20):
            audit_public_financial_coverage(codes[start:start+20], fetcher=fetcher,
                on_result=lambda row: emit(dict(layer='public', **row)))
    if layer in ('all', 'reports'):
        builder = snapshot_builder or build_manual_financial_snapshot
        for entry in reports:
            company = build_company_identity(entry['code'], entry['name'])
            row = dict(layer='report', canonical_code=company['canonical_code'],
                       report_year=entry['year'], source_url=entry['source_url'],
                       path=entry['path'], human_verification='not_performed')
            try:
                path = Path(entry['path'])
                if path.stat().st_size > MANUAL_PDF_MAX_BYTES:
                    raise ValueError('文件超过32MB，本批未读取。')
                snapshot = builder(company, path.read_bytes(), report_year=entry['year'],
                    source_url=entry['source_url'], published_date=entry['published_date'],
                    identity_confirmed=entry['identity_confirmed'])
                row.update(status=snapshot['status'],
                    statement_template=snapshot['report'].get('statement_template', 'general'),
                    statement_checks=snapshot['statement_checks'],
                    income_reconciliation=snapshot.get('income_reconciliation'),
                    pdf_text_adjustments=snapshot['report'].get('text_adjustments', []),
                    cash_flow_layout_recoveries=snapshot['report'].get('cash_flow_layout_recoveries', []),
                    balance_sheet_layout_recoveries=snapshot['report'].get('balance_sheet_layout_recoveries', []),
                    income_layout_recoveries=snapshot['report'].get('income_layout_recoveries', []),
                    statement_reconciliation=snapshot.get('statement_reconciliation'),
                    failed_checks=[k for k,v in snapshot['statement_checks'].items() if not v],
                    fingerprint=snapshot['source_fingerprint_sha256'],
                    page_count=snapshot['report']['page_count'],
                    reason=snapshot.get('extraction_note',''),
                    unit_note=snapshot['unit_note'],
                    failure_categories=([] if snapshot['status']=='ready_for_human_review' else
                        (['statement_reconciliation'] if not all(snapshot['statement_checks'].values()) else [])
                        + (['unit_validation'] if not snapshot.get('unit') else [])),
                    metrics=snapshot['metrics'], ratios=snapshot['ratios'],
                    limitations=snapshot['limitations'])
            except (OSError, ValueError) as error:
                row.update(status='rejected', failure_type=type(error).__name__, reason=str(error)[:800])
            except Exception as error:
                # A parser bug must be visible and must not discard other receipts.
                row.update(status='unexpected_error', failure_type=type(error).__name__, reason=str(error)[:800])
            emit(row)
    counts = {kind:dict(Counter(r['status'] for r in rows if r['layer']==kind))
              for kind in ('public','report')}
    return dict(schema='financial-coverage-batch.v1', started_at=started,
        completed_at=datetime.now(timezone.utc).isoformat(), layer=layer, counts=counts,
        rows=rows, limitations=[
            '仅代表明确指定样本，不是全市场覆盖率。未检查的公司或年报不得推定成功。',
            '公开源可用不等于年报解析通过；解析通过仍待人工核验，不自动新增核验证据。',
            '报告文件与链接由清单对应；本工具不下载、不验证线上版本或执行部署。'])


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--layer', choices=('all','public','reports'), default='all')
    args = parser.parse_args(argv)
    journal = args.output.with_suffix(args.output.suffix+'.jsonl')
    if args.output.exists() or journal.exists():
        parser.error('输出或逐项日志已存在，请使用新批次路径。')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    validate_manifest(manifest)
    with journal.open('x', encoding='utf-8') as handle:
        def record(row):
            handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            handle.flush()
            print(row['layer'], row['canonical_code'], row['status'], flush=True)
        result = audit_coverage_batch(manifest,layer=args.layer,on_result=record)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(result['counts'],ensure_ascii=False))
    return int(any(r['status'] in ('unavailable','rejected','unexpected_error','needs_review','partial')
                   for r in result['rows']))


if __name__ == '__main__':
    raise SystemExit(main())
