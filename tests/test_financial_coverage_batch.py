import json
import pytest
from src.financial_coverage_batch import audit_coverage_batch, validate_manifest, main
from test_public_financial_ui import fixture_history


def test_large_explicit_public_batch_is_serial_and_keeps_layer_separate():
    calls=[]
    codes=[f'600{i:03}' for i in range(25)]
    def fetch(company):
        calls.append(company['code'])
        return fixture_history(company['code'])
    result=audit_coverage_batch(dict(codes=codes,reports=[]),fetcher=fetch)
    assert calls==codes
    assert result['counts']=={'public':{'available':25},'report':{}}
    assert len(result['rows'])==25


def entry(path,code='000001'):
    return dict(code=code,name='测试公司',year=2025,path=str(path),
        source_url='https://static.cninfo.com.cn/test.pdf',published_date='2026-03-21',identity_confirmed=True)


def test_report_failures_are_preserved_without_stopping_batch(tmp_path):
    p=tmp_path/'sample.pdf';p.write_bytes(b'%PDF-test')
    def builder(company,*args,**kwargs):
        if company['code']=='000001':raise ValueError('wrong year')
        raise RuntimeError('parser defect')
    result=audit_coverage_batch(dict(codes=[],reports=[entry(p),entry(p,'000002'),entry(tmp_path/'missing')]),
        snapshot_builder=builder)
    assert [r['status'] for r in result['rows']]==['rejected','unexpected_error','rejected']
    assert all(r['human_verification']=='not_performed' for r in result['rows'])


def test_oversized_report_not_read_or_parsed(tmp_path):
    p=tmp_path/'big.pdf'
    with p.open('wb') as f:f.truncate(32*1024*1024+1)
    def forbidden(*args,**kwargs):raise AssertionError('should not parse')
    result=audit_coverage_batch(dict(reports=[entry(p)]),snapshot_builder=forbidden)
    assert result['rows'][0]['status']=='rejected'
    assert '32MB' in result['rows'][0]['reason']


@pytest.mark.parametrize('manifest',[{}, {'codes':['000001','000001']},
    {'codes':['bad']}, {'codes':[f'600{i:03}' for i in range(201)]}, {'reports':[{}]}])
def test_bad_manifest_rejects_before_network(manifest):
    with pytest.raises(ValueError):validate_manifest(manifest)


def test_cli_preserves_existing_receipt_and_writes_individual_failures(tmp_path):
    plan=tmp_path/'plan.json';out=tmp_path/'out.json'
    plan.write_text(json.dumps(dict(reports=[entry(tmp_path/'missing.pdf')])))
    assert main(['--manifest',str(plan),'--output',str(out),'--layer','reports'])==1
    assert json.loads(out.read_text())['counts']['report']=={'rejected':1}
    assert len(out.with_suffix('.json.jsonl').read_text().splitlines())==1
    original=out.read_bytes()
    with pytest.raises(SystemExit):main(['--manifest',str(plan),'--output',str(out)])
    assert out.read_bytes()==original


def test_empty_selected_layer_cannot_report_success():
    with pytest.raises(ValueError,match='没有样本'):
        audit_coverage_batch(dict(codes=['000001'],reports=[]),layer='reports')
