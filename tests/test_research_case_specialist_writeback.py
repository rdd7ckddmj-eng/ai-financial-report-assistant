"""UI-helper regressions for specialist tools writing one ResearchCase."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src import app
from src.china_stock import build_company_identity
from src.research_case import empty_research_case_store


def _company(code: str, name: str):
    return build_company_identity(code, name)


def _fake_patch(case, *, module: str, emitted_at: str):
    patch_id = f"patch-{module}-stable"
    return {
        "patch_id": patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": emitted_at,
        "source_module": module,
        "artifact": {
            "artifact_id": f"artifact-{module}-stable",
            "module": module,
            "title": f"{module} test artifact",
            "generated_at": emitted_at,
            "payload": {"test_only": True},
            "review_status": "not_required",
        },
    }


@pytest.fixture
def specialist_state(monkeypatch):
    session_state = {
        app.RESEARCH_CASE_STORE_SESSION_KEY: empty_research_case_store(),
        app.RESEARCH_CASE_HYDRATED_KEY: True,
        app.RESEARCH_CASE_STORAGE_STATUS_KEY: "available",
    }
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))

    def annual_builder(case, **kwargs):
        return _fake_patch(
            case,
            module="annual_report",
            emitted_at=kwargs["emitted_at"],
        )

    def delta_builder(case, review, *, emitted_at):
        del review
        return _fake_patch(
            case,
            module="evidence_delta",
            emitted_at=emitted_at,
        )

    monkeypatch.setattr(
        app,
        "build_annual_report_qa_case_patch",
        annual_builder,
    )
    monkeypatch.setattr(
        app,
        "build_evidence_delta_research_case_patch",
        delta_builder,
    )
    return session_state


def _write_annual(company) -> None:
    app._write_annual_qa_to_research_case(
        company,
        report_name="report.pdf",
        source_url="https://static.cninfo.com.cn/report.pdf",
        source_fingerprint_sha256="a" * 64,
        report_published_date="2026-04-01",
        question="测试问题",
        final_run={},
        audit_record={},
    )


def _write_delta(company) -> None:
    app._write_evidence_delta_to_research_case(
        company,
        {"items": [{"title": "公告"}]},
    )


@pytest.mark.parametrize("writer", [_write_annual, _write_delta])
def test_specialist_writeback_creates_one_case_and_stages_it(
    specialist_state,
    writer,
) -> None:
    company = _company("600519", "贵州茅台")

    writer(company)

    store = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    assert len(store["cases"]) == 1
    case = next(iter(store["cases"].values()))
    assert case["company"]["canonical_code"] == company["canonical_code"]
    assert case["revision"] == 1
    assert specialist_state[app.RESEARCH_CASE_PENDING_SESSION_KEY] == store


@pytest.mark.parametrize("writer", [_write_annual, _write_delta])
def test_specialist_retry_is_idempotent_without_a_second_pending_write(
    specialist_state,
    writer,
) -> None:
    company = _company("600519", "贵州茅台")
    writer(company)
    first_store = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    first_revision = first_store["store_revision"]
    specialist_state.pop(app.RESEARCH_CASE_PENDING_SESSION_KEY)
    specialist_state.pop(app.RESEARCH_CASE_PENDING_BASE_KEY)

    writer(company)

    second_store = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    assert second_store["store_revision"] == first_revision
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in specialist_state
    assert len(second_store["cases"]) == 1


@pytest.mark.parametrize("writer", [_write_annual, _write_delta])
def test_specialist_writeback_never_mutates_the_other_company_case(
    specialist_state,
    writer,
) -> None:
    first_company = _company("600519", "贵州茅台")
    second_company = _company("000333", "美的集团")
    writer(first_company)
    first_store = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    first_case = next(iter(first_store["cases"].values()))
    first_case_id = first_case["case_id"]
    first_case_revision = first_case["revision"]
    specialist_state.pop(app.RESEARCH_CASE_PENDING_SESSION_KEY)
    specialist_state.pop(app.RESEARCH_CASE_PENDING_BASE_KEY)

    writer(second_company)

    second_store = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]
    assert len(second_store["cases"]) == 2
    assert second_store["cases"][first_case_id]["revision"] == first_case_revision
    active = second_store["cases"][second_store["active_case_id"]]
    assert active["company"]["canonical_code"] == second_company["canonical_code"]


@pytest.mark.parametrize("writer", [_write_annual, _write_delta])
def test_specialist_writeback_fails_closed_before_browser_hydration(
    specialist_state,
    writer,
) -> None:
    specialist_state[app.RESEARCH_CASE_HYDRATED_KEY] = False
    before = specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY]

    writer(_company("600519", "贵州茅台"))

    assert specialist_state[app.RESEARCH_CASE_STORE_SESSION_KEY] == before
    assert app.RESEARCH_CASE_PENDING_SESSION_KEY not in specialist_state
    error_keys = {
        "_wfz_annual_qa_case_writeback_error",
        "_wfz_evidence_delta_case_writeback_error",
    }
    assert error_keys.intersection(specialist_state)
