"""Re-read one exact official PDF from the published test register.

The register selects a source, never supplies financial values or grants a
pass. Every click downloads, fingerprints and parses the original again.
"""
from hashlib import sha256
from http.client import HTTPSConnection
from ipaddress import ip_address
import socket
from time import monotonic
from urllib.parse import urljoin, urlsplit

from src.annual_report_coverage import (
    load_coverage_catalog, reports_for_company, validate_coverage_catalog,
)
from src.audited_company_onboarding import build_candidate_report_result
from src.china_stock import DataSourceError, is_allowed_disclosure_url
from src.on_demand_financial_snapshot import build_on_demand_financial_snapshot
from src.pdf_extractor import extract_pdf_pages
from src.pdf_resource_policy import MEBIBYTE, SNAPSHOT_PDF_MAX_BYTES


_DOWNLOAD_TIMEOUT_SECONDS = 35
_MAX_REDIRECTS = 3
_READ_CHUNK_BYTES = 64 * 1024


def _size_limit_message():
    return f'所选年报超过{SNAPSHOT_PDF_MAX_BYTES / MEBIBYTE:g} MiB读取上限。'


def _official_pdf_target(url):
    """Check every hop, including issuer links whose whitelist is exact-path."""
    parsed = urlsplit(url)
    if (len(url) > 2048 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)
            or parsed.scheme != 'https' or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment
            or not parsed.path.lower().endswith('.pdf')
            or not is_allowed_disclosure_url(url)):
        raise ValueError('所选原件及其跳转必须是受信任官方地址的HTTPS PDF直链。')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError('官方原件地址无法解析。')
    # Reject mixed public/private DNS answers too; never connect first and
    # inspect afterwards. Pin this checked address to prevent a second lookup.
    for address in addresses:
        ip = ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError('官方原件地址解析到了非公网地址，已停止下载。')
    return parsed, addresses[0][4][0]


class _PinnedOfficialHTTPSConnection(HTTPSConnection):
    def __init__(self, hostname, public_ip, *, timeout):
        super().__init__(hostname, timeout=timeout)
        self._public_ip = public_ip

    def connect(self):
        # Connect to the validated IP while TLS still verifies the official
        # hostname. No proxies, CONNECT tunnels or second DNS resolution.
        raw_socket = socket.create_connection((self._public_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _download_tested_original(selected):
    """Download only the row already selected from the validated register."""
    url = selected['source_url']
    deadline = monotonic() + _DOWNLOAD_TIMEOUT_SECONDS
    visited = set()

    def remaining():
        seconds = deadline - monotonic()
        if seconds <= 0:
            raise DataSourceError('官方原件下载超时，请稍后重试或手工上传。')
        return seconds

    try:
        for redirect_count in range(_MAX_REDIRECTS + 1):
            remaining()
            if url in visited:
                raise ValueError('官方原件跳转形成循环，已停止下载。')
            visited.add(url)
            parsed, public_ip = _official_pdf_target(url)
            connection = _PinnedOfficialHTTPSConnection(parsed.hostname, public_ip, timeout=remaining())
            response = None
            try:
                path = parsed.path + (f'?{parsed.query}' if parsed.query else '')
                connection.request('GET', path, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; WFZ-Financial-Research/1.0)',
                    'Accept': 'application/pdf', 'Accept-Encoding': 'identity',
                })
                request_socket = connection.sock
                request_socket.settimeout(remaining())
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if (not location or len(location) > 2048
                            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in location)
                            or redirect_count == _MAX_REDIRECTS):
                        raise ValueError('官方原件跳转缺少地址或次数过多，已停止下载。')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise DataSourceError('官方原件暂时无法下载，请稍后重试或手工上传。')
                content_type = (response.getheader('Content-Type') or '').split(';', 1)[0].strip().lower()
                if content_type not in ('', 'application/pdf', 'application/octet-stream', 'binary/octet-stream'):
                    raise ValueError('官方地址没有返回PDF内容，已停止读取。')
                if (response.getheader('Content-Encoding') or 'identity').lower() != 'identity':
                    raise ValueError('官方原件返回了非原始编码，已停止读取。')
                length = response.getheader('Content-Length')
                if length is not None and (not length.isascii() or not length.isdecimal()):
                    raise ValueError('官方原件返回了无效文件大小，已停止读取。')
                if length is not None and int(length) > SNAPSHOT_PDF_MAX_BYTES:
                    raise ValueError(_size_limit_message())
                content = bytearray()
                while not response.isclosed():
                    # HTTPConnection may release its reference after headers
                    # when the server sends Connection: close; response still
                    # owns this same socket until its body is consumed.
                    request_socket.settimeout(remaining())
                    chunk = response.read1(min(_READ_CHUNK_BYTES, SNAPSHOT_PDF_MAX_BYTES + 1 - len(content)))
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > SNAPSHOT_PDF_MAX_BYTES:
                        raise ValueError(_size_limit_message())
                    if len(content) >= 4 and not content.startswith(b'%PDF'):
                        raise ValueError('官方地址没有返回有效PDF，已停止读取。')
                if not content.startswith(b'%PDF') or (length is not None and len(content) != int(length)):
                    raise ValueError('官方原件内容无效或下载不完整，已停止读取。')
                remaining()
                return bytes(content)
            finally:
                if response is not None:
                    response.close()
                connection.close()
    except (DataSourceError, ValueError):
        raise
    except Exception as error:
        raise DataSourceError('官方原件暂时无法下载，请稍后重试或手工上传。') from error


def tested_report_options(company, *, catalog=None):
    """List source versions for this issuer without making a network request."""
    register = load_coverage_catalog() if catalog is None else validate_coverage_catalog(catalog)
    rows = reports_for_company(register, company)
    # Start with the newest financial year; within it prefer a previously
    # readable version. Still show failures and other years explicitly.
    return sorted(rows, key=lambda r: (
        r['report_year'], r['status'] == 'ready_for_human_review',
        r['published_date'], r['source_sha256'],
    ), reverse=True)


def load_tested_report_snapshot(company, source_sha256, *, catalog=None):
    """Bind the request to an issuer and exact source, then run today's parser."""
    register = load_coverage_catalog() if catalog is None else validate_coverage_catalog(catalog)
    rows = reports_for_company(register, company)
    selected = next((r for r in rows if r['source_sha256'] == source_sha256), None)
    if selected is None:
        raise ValueError('所选原件不在这家公司的已测试范围内，请重新选择。')
    pdf_bytes = _download_tested_original(selected)
    # Recheck the download contract before a parser sees the bytes, including
    # when a downloader implementation is changed later.
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b'%PDF'):
        raise ValueError('官方地址没有返回有效PDF，已停止读取。')
    if len(pdf_bytes) > SNAPSHOT_PDF_MAX_BYTES:
        raise ValueError(_size_limit_message())
    if sha256(pdf_bytes).hexdigest() != selected['source_sha256']:
        raise ValueError('官方链接返回的文件与已测试原件不同，已停止；请核对新版本后手工上传。')
    pages = extract_pdf_pages(pdf_bytes, max_bytes=SNAPSHOT_PDF_MAX_BYTES,
        include_financial_geometry=True, financial_report_year=selected['report_year'])
    if len(pages) != selected['page_count']:
        raise ValueError('本次读取的页数与已测试原件不一致，已停止生成快照。')
    report = dict(report_year=selected['report_year'], published_date=selected['published_date'],
        title=f"{selected['company_name']}{selected['report_year']}年年度报告（已测试原件，重新读取）",
        url=selected['source_url'])
    candidate = build_candidate_report_result(company, report, pdf_bytes, pages)
    snapshot = build_on_demand_financial_snapshot(company, candidate)
    snapshot['input_provenance'] = 'redownloaded_exact_tested_official_report'
    snapshot['tested_source_selection'] = dict(
        catalog_tested_at=register['tested_at'],
        prior_test_status=selected['status'],
        source_sha256=selected['source_sha256'],
        downloaded_sha256_matched=True,
        selection_scope='exact_historical_version_not_latest_disclosure',
    )
    snapshot['limitations'].append(
        '本次从官方链接重新下载并核对了所选原件的文件指纹与页数；'
        '报告年度和版本由本次选择决定，不保证是最新披露。历史测试不代替本次检查或人工复核。'
    )
    return snapshot
