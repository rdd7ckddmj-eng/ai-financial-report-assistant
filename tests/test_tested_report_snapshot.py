from copy import deepcopy
from hashlib import sha256
import json

import pytest
from streamlit.testing.v1 import AppTest

import src.tested_report_snapshot as module
from src.annual_report_coverage import load_coverage_catalog
from src.china_stock import DataSourceError, build_company_identity
from test_on_demand_financial_snapshot import _candidate_result


@pytest.fixture
def source(monkeypatch):
    catalog = load_coverage_catalog()
    row = deepcopy(catalog['reports'][0])
    pdf = b'%PDF-test exact downloaded version'
    row.update(source_sha256=sha256(pdf).hexdigest(), page_count=2)
    catalog['reports'] = [row]
    company = build_company_identity(row['canonical_code'][:6], row['company_name'])
    calls = []
    def download(selected):
        calls.append((selected['source_url'], {'max_bytes': module.SNAPSHOT_PDF_MAX_BYTES}))
        return pdf
    monkeypatch.setattr(module, '_download_tested_original', download)
    monkeypatch.setattr(module, 'extract_pdf_pages', lambda *a, **kw: [dict(page_number=n, text='original') for n in (1, 2)])
    candidate = _candidate_result()
    candidate.update(report_year=row['report_year'], published_date=row['published_date'],
        title=f"{row['company_name']}{row['report_year']}年年度报告（已测试原件，重新读取）",
        source_url=row['source_url'], evidence_fingerprint_sha256=row['source_sha256'], page_count=2)
    monkeypatch.setattr(module, 'build_candidate_report_result', lambda *a: deepcopy(candidate))
    monkeypatch.setattr(module, 'load_coverage_catalog', lambda: deepcopy(catalog))
    return company, catalog, row, pdf, candidate, calls


def test_listing_is_local_and_each_generation_downloads_and_parses_again(source, monkeypatch):
    company, catalog, row, pdf, candidate, calls = source
    assert module.tested_report_options(company)[0]['source_sha256'] == row['source_sha256']
    assert calls == []
    parsed = []
    def parse(content, **kwargs):
        parsed.append((content, kwargs))
        return [dict(page_number=n, text='original') for n in (1, 2)]
    monkeypatch.setattr(module, 'extract_pdf_pages', parse)
    first = module.load_tested_report_snapshot(company, row['source_sha256'])
    second = module.load_tested_report_snapshot(company, row['source_sha256'])
    assert len(calls) == len(parsed) == 2
    assert calls[0] == (row['source_url'], {'max_bytes': module.SNAPSHOT_PDF_MAX_BYTES})
    assert parsed[0] == (pdf, dict(max_bytes=module.SNAPSHOT_PDF_MAX_BYTES,
        include_financial_geometry=True, financial_report_year=row['report_year']))
    assert first['source_fingerprint_sha256'] == second['source_fingerprint_sha256'] == row['source_sha256']
    assert first['input_provenance'] == 'redownloaded_exact_tested_official_report'
    assert first['tested_source_selection']['downloaded_sha256_matched'] is True
    assert any('不保证是最新披露' in s for s in first['limitations'])
    assert not any('从最新完整年度报告' in s for s in first['limitations'])
    json.dumps(first, allow_nan=False)  # Retained result must contain no PDF bytes.


@pytest.mark.parametrize('damage', ['issuer', 'exchange', 'hash', 'catalog_url', 'catalog_sha'])
def test_invalid_selection_cannot_download_a_different_issuers_report(source, damage):
    company, catalog, row, pdf, candidate, calls = source
    company = deepcopy(company); fingerprint = row['source_sha256']
    if damage == 'issuer': company = build_company_identity('600777')
    if damage == 'exchange': company['canonical_code'] = company['code'] + '.BJ'
    if damage == 'hash': fingerprint = '0' * 64
    if damage == 'catalog_url': catalog['reports'][0]['source_url'] = 'https://attacker.invalid/report.pdf'
    if damage == 'catalog_sha': catalog['reports'][0]['source_sha256'] = []
    with pytest.raises(ValueError):
        module.load_tested_report_snapshot(company, fingerprint, catalog=catalog)
    assert calls == []


@pytest.mark.parametrize('damage', ['replacement', 'html', 'nonbytes', 'oversize', 'pages'])
def test_changed_or_invalid_original_is_rejected_before_financial_generation(source, monkeypatch, damage):
    company, catalog, row, pdf, candidate, calls = source
    if damage == 'replacement': pdf = b'%PDF-replaced newer file'
    if damage == 'html': pdf = b'<html>unavailable</html>'
    if damage == 'nonbytes': pdf = '%PDF-text'
    if damage == 'oversize': monkeypatch.setattr(module, 'SNAPSHOT_PDF_MAX_BYTES', 10)
    monkeypatch.setattr(module, '_download_tested_original', lambda *a, **k: pdf)
    if damage == 'pages': monkeypatch.setattr(module, 'extract_pdf_pages', lambda *a, **k: [dict(page_number=1, text='only one')])
    def forbidden(*a, **k):
        raise AssertionError('A different or incomplete source must not reach financial generation')
    monkeypatch.setattr(module, 'build_candidate_report_result', forbidden)
    with pytest.raises(ValueError): module.load_tested_report_snapshot(company, row['source_sha256'])


def test_old_pass_does_not_grant_current_parser_a_pass(source):
    company, catalog, row, pdf, candidate, calls = source
    assert row['status'] == 'ready_for_human_review'
    candidate['status'] = 'needs_review'
    candidate['statement_checks']['income_statement_reconciled'] = False
    snapshot = module.load_tested_report_snapshot(company, row['source_sha256'])
    assert snapshot['status'] == 'needs_review'
    assert all(m['current_yuan'] is None and m['previous_yuan'] is None for m in snapshot['metrics'])
    assert snapshot['tested_source_selection']['prior_test_status'] == 'ready_for_human_review'


def test_previously_failed_source_remains_selectable_but_is_not_renamed_a_pass(source):
    company, catalog, row, pdf, candidate, calls = source
    catalog['reports'][0]['status'] = 'needs_review'
    catalog['reports'][0]['statement_checks']['income_statement_reconciled'] = False
    candidate['status'] = 'needs_review'
    candidate['statement_checks']['income_statement_reconciled'] = False
    assert module.tested_report_options(company)[0]['status'] == 'needs_review'
    assert module.load_tested_report_snapshot(company, row['source_sha256'])['status'] == 'needs_review'


def test_ui_never_downloads_on_view_or_selection_and_clears_old_review_on_failure(source, monkeypatch):
    company, catalog, row, pdf, candidate, calls = source
    from src import app
    script = f"""
import streamlit as st
from src import app
from src.china_stock import build_company_identity
app._render_tested_snapshot_input(build_company_identity({company['code']!r}, {company['name']!r}))
"""
    at = AppTest.from_string(script).run()
    assert not at.exception and calls == []
    assert any('不保证是最新披露' in x.value for x in at.caption)
    at.selectbox[0].select(row['source_sha256']).run()
    assert not at.exception and calls == []
    at.session_state['on_demand_financial_snapshot'] = {'stale': True}
    at.session_state[app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY] = {'stale': True}
    def unavailable(*a, **k): raise DataSourceError('下载失败')
    monkeypatch.setattr(module, '_download_tested_original', unavailable)
    at.button[0].click().run()
    assert not at.exception and any('下载失败' in x.value for x in at.error)
    assert 'on_demand_financial_snapshot' not in at.session_state
    assert app.FINANCIAL_SNAPSHOT_REVIEW_SESSION_KEY not in at.session_state


def test_ui_saves_only_a_fresh_candidate_and_unknown_company_has_no_action(source):
    company, catalog, row, pdf, candidate, calls = source
    at = AppTest.from_string(f"from src import app\nfrom src.china_stock import build_company_identity\napp._render_tested_snapshot_input(build_company_identity({company['code']!r}, {company['name']!r}))").run()
    at.button[0].click().run()
    assert not at.exception and len(calls) == 1
    assert at.session_state['on_demand_financial_snapshot']['source_fingerprint_sha256'] == row['source_sha256']
    unknown = AppTest.from_string("from src import app\nfrom src.china_stock import build_company_identity\napp._render_tested_snapshot_input(build_company_identity('600777'))").run()
    assert not unknown.exception and not unknown.button and not unknown.selectbox
    assert len(calls) == 1


class _Response:
    def __init__(self, body=b'%PDF-test', *, status=200, headers=None):
        from io import BytesIO
        self.body = BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []
        self.closed = False

    def getheader(self, name):
        return self.headers.get(name)

    def read1(self, size):
        self.read_sizes.append(size)
        return self.body.read(size)

    def isclosed(self):
        return self.body.tell() == len(self.body.getbuffer())

    def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    """Fake only the network boundary; keep real URL and streaming dispatch."""
    import socket
    from types import SimpleNamespace
    state = SimpleNamespace(responses=[], connections=[], resolved=[])

    def resolve(host, port, **kwargs):
        state.resolved.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', port))]

    class Connection:
        def __init__(self, hostname, public_ip, *, timeout):
            self.hostname, self.public_ip, self.timeout = hostname, public_ip, timeout
            self.timeouts = []
            self.sock = SimpleNamespace(settimeout=self.timeouts.append)
            self.closed = False
            state.connections.append(self)

        def request(self, method, path, *, headers):
            self.requested = method, path, headers

        def getresponse(self):
            # Exercise HTTPConnection's Connection: close behavior too.
            self.sock = None
            return state.responses.pop(0)

        def close(self):
            self.closed = True

    monkeypatch.setattr(module.socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(module, '_PinnedOfficialHTTPSConnection', Connection)
    return state


@pytest.mark.parametrize('row', load_coverage_catalog()['reports'],
                         ids=lambda r: r['canonical_code'] + '-' + str(r['report_year']) + '-' + r['source_sha256'][:8])
def test_every_registered_real_url_uses_direct_official_pdf_transport(transport, row):
    """Includes SZSE, HKEX and exact issuer links rejected by CNINFO dispatch."""
    from urllib.parse import urlsplit
    response = _Response()
    transport.responses.append(response)
    assert module._download_tested_original(row) == b'%PDF-test'
    parsed = urlsplit(row['source_url'])
    connection, = transport.connections
    assert connection.hostname == parsed.hostname
    assert connection.public_ip == '93.184.216.34'
    assert connection.requested[0:2] == ('GET', parsed.path + ('?' + parsed.query if parsed.query else ''))
    assert connection.requested[2]['Accept-Encoding'] == 'identity'
    assert 0 < connection.timeout <= module._DOWNLOAD_TIMEOUT_SECONDS
    assert all(0 < timeout <= module._DOWNLOAD_TIMEOUT_SECONDS for timeout in connection.timeouts)
    assert connection.closed and response.closed


@pytest.mark.parametrize('url', [
    'http://static.cninfo.com.cn/report.pdf',
    'https://static.cninfo.com.cn:8443/report.pdf',
    'https://user:password@static.cninfo.com.cn/report.pdf',
    'https://static.cninfo.com.cn/report.html',
    'https://static.cninfo.com.cn/report.pdf#fragment',
    'https://static.cninfo.com.cn/report.pdf\n',
    'https://static.cninfo.com.cn.attacker.invalid/report.pdf',
    'https://127.0.0.1/report.pdf',
    'https://169.254.169.254/report.pdf',
    'https://[::1]/report.pdf',
    'https://www.cpic.com.cn/unverified-report.pdf',
    'https://www.hkexnews.hk/unverified-report.pdf',
])
def test_untrusted_redirect_is_rejected_before_second_connection(transport, url):
    response = _Response(status=302, headers={'Location': url})
    transport.responses.append(response)
    with pytest.raises(ValueError):
        module._download_tested_original({'source_url': load_coverage_catalog()['reports'][0]['source_url']})
    assert len(transport.connections) == 1
    assert response.closed and transport.connections[0].closed


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '192.168.0.1',
                                     '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1', '224.0.0.1'])
def test_private_or_mixed_dns_answers_cannot_connect(transport, monkeypatch, address):
    import socket
    monkeypatch.setattr(module.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (address, 443)),
    ])
    with pytest.raises(ValueError, match='非公网'):
        module._download_tested_original(load_coverage_catalog()['reports'][0])
    assert not transport.connections


def test_relative_official_redirect_is_revalidated_and_downloaded(transport):
    first = _Response(status=307, headers={'Location': '/another-verified.pdf'})
    second = _Response()
    transport.responses.extend([first, second])
    assert module._download_tested_original({'source_url': 'https://static.cninfo.com.cn/original.pdf'}) == b'%PDF-test'
    assert len(transport.connections) == len(transport.resolved) == 2
    assert transport.connections[1].requested[1] == '/another-verified.pdf'
    assert all(c.closed for c in transport.connections)
    assert first.closed and second.closed


@pytest.mark.parametrize('case', ['loop', 'too_many', 'missing_location'])
def test_redirects_are_bounded_and_close_each_response(transport, case):
    original = 'https://static.cninfo.com.cn/original.pdf'
    if case == 'loop':
        transport.responses = [_Response(status=302, headers={'Location': original})]
    elif case == 'missing_location':
        transport.responses = [_Response(status=302)]
    else:
        transport.responses = [_Response(status=302, headers={'Location': f'/redirect-{n}.pdf'}) for n in range(4)]
    responses = list(transport.responses)
    with pytest.raises(ValueError):
        module._download_tested_original({'source_url': original})
    assert len(transport.connections) <= 4
    assert all(c.closed for c in transport.connections)
    assert all(r.closed for r in responses)


@pytest.mark.parametrize('headers,body', [
    ({'Content-Type': 'text/html'}, b'%PDF-disguised-html'),
    ({'Content-Type': 'application/pdf'}, b'<html>missing</html>'),
    ({'Content-Encoding': 'gzip'}, b'%PDF-compressed'),
    ({'Content-Length': '-1'}, b'%PDF-test'),
    ({'Content-Length': '10, 10'}, b'%PDF-test'),
    ({'Content-Length': '100'}, b'%PDF-truncated'),
    ({}, b'%PD'),
])
def test_non_pdf_encoded_or_incomplete_responses_reject(transport, headers, body):
    response = _Response(body, headers=headers)
    transport.responses.append(response)
    with pytest.raises(ValueError):
        module._download_tested_original(load_coverage_catalog()['reports'][0])
    assert response.closed and transport.connections[0].closed


@pytest.mark.parametrize('declared_length', [True, False])
def test_size_cap_applies_before_read_and_during_streaming(transport, monkeypatch, declared_length):
    monkeypatch.setattr(module, 'SNAPSHOT_PDF_MAX_BYTES', 16)
    response = _Response(b'%PDF-' + b'x' * 40, headers={'Content-Length': '45'} if declared_length else {})
    transport.responses.append(response)
    with pytest.raises(ValueError, match='MiB'):
        module._download_tested_original(load_coverage_catalog()['reports'][0])
    assert response.closed and transport.connections[0].closed
    assert response.read_sizes == ([] if declared_length else [17])


def test_stream_chunk_limit_and_exact_size_are_preserved(transport, monkeypatch):
    monkeypatch.setattr(module, 'SNAPSHOT_PDF_MAX_BYTES', 12)
    monkeypatch.setattr(module, '_READ_CHUNK_BYTES', 5)
    body = b'%PDF-1234567'
    response = _Response(body, headers={'Content-Length': '12', 'Content-Type': 'application/pdf; charset=binary'})
    transport.responses.append(response)
    assert module._download_tested_original(load_coverage_catalog()['reports'][0]) == body
    assert max(response.read_sizes) <= 5


def test_elapsed_budget_stops_before_connect(transport, monkeypatch):
    ticks = iter([0, 36])
    monkeypatch.setattr(module, 'monotonic', lambda: next(ticks))
    with pytest.raises(DataSourceError, match='超时'):
        module._download_tested_original(load_coverage_catalog()['reports'][0])
    assert not transport.connections


def test_tls_uses_checked_ip_and_official_hostname_without_second_dns(monkeypatch):
    from types import SimpleNamespace
    connected, wrapped = [], []
    raw = SimpleNamespace(close=lambda: None)
    def connect(address, timeout):
        connected.append((address, timeout))
        return raw
    def wrap(sock, *, server_hostname):
        wrapped.append((sock, server_hostname))
        return 'verified TLS socket'
    monkeypatch.setattr(module.socket, 'create_connection', connect)
    connection = module._PinnedOfficialHTTPSConnection('static.cninfo.com.cn', '93.184.216.34', timeout=12)
    monkeypatch.setattr(connection._context, 'wrap_socket', wrap)
    connection.connect()
    assert connected == [(('93.184.216.34', 443), 12)]
    assert wrapped == [(raw, 'static.cninfo.com.cn')]
    assert connection.sock == 'verified TLS socket'


@pytest.mark.parametrize('wire_body', [
    b'HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nContent-Length: 9\r\nConnection: close\r\n\r\n%PDF-test',
    b'HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n4\r\n%PDF\r\n5\r\n-test\r\n0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nConnection: close\r\n\r\n%PDF-test',
])
def test_real_http_response_handles_close_and_chunked_eof_without_touching_closed_fd(monkeypatch, wire_body):
    from http.client import HTTPResponse
    from io import BytesIO
    import socket
    state = {'socket_closed': False, 'timeouts': []}

    class BodyFile(BytesIO):
        def close(self):
            state['socket_closed'] = True
            super().close()

    class Socket:
        def makefile(self, mode):
            return BodyFile(wire_body)

        def settimeout(self, seconds):
            if state['socket_closed']:
                raise OSError('Bad file descriptor: production must not touch an already consumed response')
            state['timeouts'].append(seconds)

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = Socket()

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            response = HTTPResponse(self.sock)
            response.begin()
            assert response.will_close
            self.sock = None
            return response

        def close(self):
            pass

    monkeypatch.setattr(module.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 443))])
    monkeypatch.setattr(module, '_PinnedOfficialHTTPSConnection', Connection)
    assert module._download_tested_original(load_coverage_catalog()['reports'][0]) == b'%PDF-test'
    assert state['socket_closed'] and state['timeouts']
