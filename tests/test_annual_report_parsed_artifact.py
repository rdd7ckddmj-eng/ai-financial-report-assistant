"""Regression checks for the bounded, company-scoped annual-report cache."""

from __future__ import annotations

from hashlib import sha256

import pytest
from streamlit.testing.v1 import AppTest

from src.app import _normalise_annual_report_parsed_artifact


CANONICAL_CODE = "600519.SH"
OTHER_CANONICAL_CODE = "000333.SZ"
PDF_BYTES = b"%PDF-test"
PDF_FINGERPRINT = sha256(PDF_BYTES).hexdigest()


def _artifact(
    *,
    canonical_code: object = CANONICAL_CODE,
    fingerprint: object = PDF_FINGERPRINT,
) -> dict[str, object]:
    return {
        "canonical_code": canonical_code,
        "source_fingerprint_sha256": fingerprint,
        "source_key": "official:https://example.test/report.pdf",
        "name": "report.pdf",
        "pages": [
            {"page_number": 1, "text": "Revenue evidence"},
            {"page_number": 2, "text": "Cash-flow evidence"},
        ],
    }


def _contains_binary(value: object) -> bool:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return True
    if isinstance(value, dict):
        return any(
            _contains_binary(key) or _contains_binary(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_binary(item) for item in value)
    return False


def test_parsed_artifact_requires_company_fingerprint_and_page_text() -> None:
    artifact = _artifact()

    normalised = _normalise_annual_report_parsed_artifact(
        artifact,
        expected_canonical_code=CANONICAL_CODE,
    )

    assert normalised == artifact
    assert normalised["canonical_code"] == CANONICAL_CODE
    assert normalised["source_fingerprint_sha256"] == PDF_FINGERPRINT
    assert not _contains_binary(normalised)


@pytest.mark.parametrize(
    ("canonical_code", "fingerprint"),
    [
        (None, PDF_FINGERPRINT),
        ("", PDF_FINGERPRINT),
        (CANONICAL_CODE, None),
        (CANONICAL_CODE, ""),
        (CANONICAL_CODE, "a" * 63),
        (CANONICAL_CODE, "A" * 64),
        (CANONICAL_CODE, "g" * 64),
    ],
)
def test_parsed_artifact_rejects_missing_or_invalid_identity(
    canonical_code: object,
    fingerprint: object,
) -> None:
    assert (
        _normalise_annual_report_parsed_artifact(
            _artifact(
                canonical_code=canonical_code,
                fingerprint=fingerprint,
            ),
            expected_canonical_code=CANONICAL_CODE,
        )
        is None
    )


def test_parsed_artifact_rejects_cross_company_reuse() -> None:
    assert (
        _normalise_annual_report_parsed_artifact(
            _artifact(),
            expected_canonical_code=OTHER_CANONICAL_CODE,
        )
        is None
    )


@pytest.mark.parametrize(
    "missing_key",
    ["canonical_code", "source_fingerprint_sha256"],
)
def test_parsed_artifact_rejects_missing_identity_key(
    missing_key: str,
) -> None:
    artifact = _artifact()
    artifact.pop(missing_key)

    assert (
        _normalise_annual_report_parsed_artifact(
            artifact,
            expected_canonical_code=CANONICAL_CODE,
        )
        is None
    )


def test_parsed_artifact_rejects_binary_or_non_sequential_payloads() -> None:
    binary = _artifact()
    binary["pages"] = b"%PDF-binary-must-not-be-persisted"
    non_sequential = _artifact()
    non_sequential["pages"] = [
        {"page_number": 2, "text": "wrong first page"}
    ]

    assert (
        _normalise_annual_report_parsed_artifact(
            binary,
            expected_canonical_code=CANONICAL_CODE,
        )
        is None
    )
    assert (
        _normalise_annual_report_parsed_artifact(
            non_sequential,
            expected_canonical_code=CANONICAL_CODE,
        )
        is None
    )


def test_annual_report_cache_is_text_only_reused_and_company_scoped() -> None:
    """Same-company reruns reuse text; a company switch must parse anew."""
    script = '''
from src import app

COMPANIES = {
    "600519.SH": {
        "code": "600519",
        "name": "贵州茅台",
        "exchange": "SH",
        "exchange_name": "上海证券交易所",
        "canonical_code": "600519.SH",
    },
    "000333.SZ": {
        "code": "000333",
        "name": "美的集团",
        "exchange": "SZ",
        "exchange_name": "深圳证券交易所",
        "canonical_code": "000333.SZ",
    },
}

class FakeUpload:
    name = "bounded-report.pdf"
    def getbuffer(self):
        return memoryview(b"%PDF-test")
    def getvalue(self):
        return b"%PDF-test"

originals = {
    "_selected_company": app._selected_company,
    "_show_company_banner": app._show_company_banner,
    "apply_product_theme": app.apply_product_theme,
    "show_compact_page_header": app.show_compact_page_header,
    "show_chinese_user_guide": app.show_chinese_user_guide,
    "show_product_footer": app.show_product_footer,
    "verified_financial_history_codes": app.verified_financial_history_codes,
    "load_company_announcements": app.load_company_announcements,
    "select_latest_annual_report": app.select_latest_annual_report,
    "file_uploader": app.st.file_uploader,
    "read_uploaded_pdf": app.read_uploaded_pdf,
    "find_income_statement_figures": app.find_income_statement_figures,
    "find_balance_sheet_figures": app.find_balance_sheet_figures,
    "find_cash_flow_figures": app.find_cash_flow_figures,
}
for optional_name in (
    "_sync_research_case_store",
    "_render_research_case_storage_notice",
):
    if hasattr(app, optional_name):
        originals[optional_name] = getattr(app, optional_name)

def selected_company():
    selected = app.st.session_state.get(
        "annual_test_company_code",
        "600519.SH",
    )
    return COMPANIES[selected]

def parse_once(_pdf_bytes, _max_bytes):
    app.st.session_state["annual_parse_count"] = (
        app.st.session_state.get("annual_parse_count", 0) + 1
    )
    return [{"page_number": 1, "text": "Revenue evidence"}]

try:
    app._selected_company = selected_company
    app._show_company_banner = lambda *args, **kwargs: None
    app.apply_product_theme = lambda: None
    app.show_compact_page_header = lambda *args, **kwargs: None
    app.show_chinese_user_guide = lambda: None
    app.show_product_footer = lambda: None
    app.verified_financial_history_codes = lambda: frozenset()
    app.load_company_announcements = lambda *args, **kwargs: []
    app.select_latest_annual_report = lambda *args, **kwargs: None
    if hasattr(app, "_sync_research_case_store"):
        app._sync_research_case_store = lambda: None
    if hasattr(app, "_render_research_case_storage_notice"):
        app._render_research_case_storage_notice = lambda: None
    app.st.file_uploader = lambda *args, **kwargs: FakeUpload()
    app.read_uploaded_pdf = parse_once
    app.find_income_statement_figures = lambda *args, **kwargs: None
    app.find_balance_sheet_figures = lambda *args, **kwargs: None
    app.find_cash_flow_figures = lambda *args, **kwargs: None
    app.render_annual_report_page()
finally:
    for name, value in originals.items():
        if name == "file_uploader":
            app.st.file_uploader = value
        else:
            setattr(app, name, value)
'''
    app_test = AppTest.from_string(script).run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["annual_parse_count"] == 1

    first_artifact = app_test.session_state["_wfz_annual_report_parsed"]
    assert first_artifact["canonical_code"] == CANONICAL_CODE
    assert first_artifact["source_fingerprint_sha256"] == PDF_FINGERPRINT
    assert not _contains_binary(first_artifact)

    app_test.run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["annual_parse_count"] == 1
    assert not _contains_binary(
        app_test.session_state["_wfz_annual_report_parsed"]
    )

    app_test.session_state["annual_test_company_code"] = (
        OTHER_CANONICAL_CODE
    )
    app_test.run(timeout=10)
    assert not app_test.exception
    assert app_test.session_state["annual_parse_count"] == 2
    switched_artifact = app_test.session_state["_wfz_annual_report_parsed"]
    assert switched_artifact["canonical_code"] == OTHER_CANONICAL_CODE
    assert switched_artifact["source_fingerprint_sha256"] == PDF_FINGERPRINT
    assert not _contains_binary(switched_artifact)
