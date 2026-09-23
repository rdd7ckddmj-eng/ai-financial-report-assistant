from datetime import date
from hashlib import sha256
import json
import pytest
from streamlit.testing.v1 import AppTest
from src.china_stock import build_company_identity
from src.manual_financial_snapshot import build_manual_financial_snapshot
from src.financial_snapshot_review import build_financial_snapshot_review
from test_financial_statement_extractor import CHINESE_INCOME_STATEMENT_TEXT
from test_balance_sheet_extractor import CHINESE_BALANCE_SHEET_TEXT
from test_cash_flow_extractor import CHINESE_CASH_FLOW_TEXT

COMPANY=build_company_identity('600519','贵州茅台')


def arguments():
    return dict(report_year=2025,source_url='https://static.cninfo.com.cn/example.pdf',
                published_date='2026-04-20',identity_confirmed=True,today=date(2026,9,21))


def pages():
    return [dict(page_number=i+1,text=text) for i,text in enumerate([
        '合成测试文档，非实际财务数据\n贵州茅台 600519\n2025年年度报告',
        CHINESE_INCOME_STATEMENT_TEXT.replace('贵州茅台酒股份有限公司2025年度合并利润表', '合并利润表').replace('五、净利润',
            '四、利润总额 92,330,000,000.00 97,240,000,000.00\n'
            '减：所得税费用 10,000,000,000.00 11,000,000,000.00\n五、净利润'),
        CHINESE_BALANCE_SHEET_TEXT,CHINESE_CASH_FLOW_TEXT])]


def test_manual_fallback_reuses_extractors_and_keeps_human_gate(monkeypatch):
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda data,**kw:pages())
    result=build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())
    assert result['source_fingerprint_sha256']==sha256(b'%PDF-test').hexdigest()
    assert result['status']=='ready_for_human_review'
    assert result['metrics'][0]['current_yuan']==168838102514.79
    assert result['metrics'][0]['source']['pages']['start']==2
    assert '未联网比对' in result['limitations'][-1]
    review=build_financial_snapshot_review(result)
    assert all(m['decision']=='pending' for m in review['metrics'])
    assert '%PDF' not in json.dumps(result)


def test_note_number_does_not_replace_revenue_with_total_revenue(monkeypatch):
    sample=pages()
    sample[1]['text']='''合并利润表
单位：人民币元
项目 附注 2025年度 2024年度
一、营业总收入
1100
950
其中：营业收入
五、54
1000
900
利息收入
五、55
100
50
利润总额 120 110
减：所得税费用 20 20
净利润 100 90
归属于母公司股东的净利润
100
90
少数股东损益 0 0
'''
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda data,**kw:sample)
    result=build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())
    revenue=next(m for m in result['metrics'] if m['key']=='revenue')
    assert revenue['current_yuan']==1000
    assert revenue['previous_yuan']==900
    assert revenue['source']['raw_current_value']==1000
    assert revenue['source']['excerpt'].startswith('其中：营业收入')
    assert build_financial_snapshot_review(result)['metrics'][0]['decision']=='pending'


@pytest.mark.parametrize('key,value',[
    ('identity_confirmed',False),('report_year',2026),('report_year',True),
    ('source_url','https://example.com/report.pdf'),('published_date','2025-12-31'),
    ('published_date','2027-01-01'),('published_date',None)])
def test_metadata_failures_stop_before_pdf_parse(monkeypatch,key,value):
    def forbidden(*args,**kw): raise AssertionError('must not parse')
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',forbidden)
    args=arguments();args[key]=value
    with pytest.raises(ValueError): build_manual_financial_snapshot(COMPANY,b'%PDF-test',**args)


@pytest.mark.parametrize('text',[
    '贵州茅台600519 2024年年度报告',
    '其他公司000651 2025年年度报告',
    '贵州茅台600519 2025年年度报告摘要',
    '',
])
def test_wrong_company_year_summary_or_scan_is_not_accepted(monkeypatch,text):
    monkeypatch.setattr('src.manual_financial_snapshot.extract_pdf_pages',lambda *a,**kw:[dict(page_number=1,text=text)])
    with pytest.raises(ValueError): build_manual_financial_snapshot(COMPANY,b'%PDF-test',**arguments())


def test_real_pdf_pipeline_preserves_page_provenance():
    import fitz
    doc=fitz.open()
    for p in pages():
        page=doc.new_page()
        page.insert_text((30,40),p['text'],fontname='china-s',fontsize=10)
    pdf=doc.tobytes();doc.close()
    result=build_manual_financial_snapshot(COMPANY,pdf,**arguments())
    assert result['report']['page_count']==4
    assert result['status']=='ready_for_human_review'
    assert result['metrics'][0]['pages']['start']==2


def test_form_entry_has_no_network_or_parse_and_clears_old_result_on_failure(monkeypatch):
    from src import app
    def forbidden(*a,**kw): raise AssertionError('unexpected work')
    monkeypatch.setattr(app,'build_manual_financial_snapshot',forbidden)
    at=AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\napp._render_manual_snapshot_input(build_company_identity('600519','贵州茅台'))")
    at.session_state['on_demand_financial_snapshot']={'old':True}
    at.run()
    assert not at.exception
    at.button[0].click().run()
    assert not at.exception
    assert any('请先选择' in e.value for e in at.error)
    assert 'on_demand_financial_snapshot' not in at.session_state


@pytest.mark.parametrize('declared_size,data,error', [
    (9, b'%PDF-test', None),
    (13, None, '超过32 MB'),
    (1, b'%PDF-too-large', '超过32 MB'),
    ('9', None, '无法确认'),
    (True, None, '无法确认'),
    (-1, None, '无法确认'),
    (1, bytearray(b'%PDF'), '无法读取'),
])
def test_upload_size_checks_avoid_writable_copy_and_reject_actual_oversize(
    monkeypatch, declared_size, data, error
):
    from src import app
    class Upload:
        size = declared_size
        def getbuffer(self):
            raise AssertionError('must not request a writable copy of uploaded bytes')
        def getvalue(self):
            assert data is not None, 'oversized/invalid metadata must stop before reading bytes'
            return data
    calls = []
    def build(company, payload, **kwargs):
        calls.append(payload)
        assert payload is data
        return {'status': 'test-result'}
    monkeypatch.setattr(app.st, 'file_uploader', lambda *args, **kwargs: Upload())
    monkeypatch.setattr(app, 'MANUAL_PDF_MAX_BYTES', 12)
    monkeypatch.setattr(app, 'build_manual_financial_snapshot', build)
    at = AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\napp._render_manual_snapshot_input(build_company_identity('600519','贵州茅台'))")
    at.session_state['on_demand_financial_snapshot'] = {'old': True}
    at.run()
    assert not at.exception and not calls
    at.button[0].click().run()
    assert not at.exception
    if error is None:
        assert calls == [data] and not at.error
        assert at.session_state['on_demand_financial_snapshot'] == {'status': 'test-result'}
    else:
        assert not calls
        assert any(error in item.value for item in at.error)
        assert 'on_demand_financial_snapshot' not in at.session_state
