"""Bridge one verified annual-report Q&A run into a ResearchCase patch.

The deterministic verifier proves citation integrity, not economic truth.
Accordingly, the AI conclusion is stored only inside an ``analysis_output``
artifact.  Case evidence contains source-record excerpts only: exact PDF
pages, official provenance and no generated claim.  The bridge copies a small
allow-list of text and page references; PDF bytes, parsed pages, retrieval
chunks and arbitrary workflow extras never enter the case.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any

from src.answer_verifier import verify_answer
from src.research_case import (
    MAX_ARTIFACTS,
    MAX_CONTRADICTIONS,
    MAX_EVIDENCE,
    ResearchCaseCapacityError,
    ResearchCaseValidationError,
    apply_case_patch,
    is_allowed_evidence_url,
    validate_research_case,
)


ANNUAL_QA_ARTIFACT_PAYLOAD_BYTES = 12_000
MAX_ANSWER_EVIDENCE = 5
MAX_CHALLENGE_EVIDENCE = 3
MAX_EVIDENCE_EXCERPT_CHARS = 480

_APPROVED_VERIFIER_STATUSES = {"approved", "approved_with_caveats"}
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _error(message: str) -> ResearchCaseValidationError:
    return ResearchCaseValidationError(message)


def _required_text(value: object, *, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{field}必须是非空文本。")
    cleaned = _WHITESPACE_PATTERN.sub(" ", value).strip()
    if len(cleaned) > limit:
        raise _error(f"{field}超过{limit}个字符。")
    return cleaned


def _compact_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_PATTERN.sub(" ", value).strip()[:limit]


def _iso_date(value: object, *, field: str) -> str:
    text = _required_text(value, field=field, limit=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。") from exc
    if parsed.isoformat() != text:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。")
    return text


def _iso_datetime(value: object, *, field: str) -> str:
    text = _required_text(value, field=field, limit=50)
    if "T" not in text:
        raise _error(f"{field}必须是ISO日期时间。")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(f"{field}必须是ISO日期时间。") from exc
    return text


def _reject_binary_or_non_json(value: object, path: str) -> None:
    """Fail closed on binary bodies and caller-owned Python objects."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise _error(f"{path}不得包含PDF或其他二进制本体。")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _error(f"{path}不得包含NaN或Infinity。")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise _error(f"{path}的对象键必须是文本。")
            _reject_binary_or_non_json(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_binary_or_non_json(child, f"{path}[{index}]")
        return
    raise _error(f"{path}只能包含标准JSON值。")


def _payload_size(value: object) -> int:
    _reject_binary_or_non_json(value, "artifact.payload")
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _identifier(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:24]}"


def _positive_page(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _error(f"{field}必须是正整数PDF页码。")
    return value


def _normalised_source_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_PATTERN.sub(" ", value).strip().lower()


def _source_contains(
    excerpt: str,
    page_number: int,
    results: list[Mapping[str, object]],
) -> bool:
    needle = _normalised_source_text(excerpt).rstrip("…")
    if not needle:
        return False
    for result in results:
        if result.get("page_number") != page_number:
            continue
        haystack = _normalised_source_text(result.get("text"))
        if needle in haystack:
            return True
    return False


def _selected_answer(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _error("final_run.answer必须是对象。")
    evidence = value.get("evidence")
    key_points = value.get("key_points")
    if not isinstance(evidence, list) or not isinstance(key_points, list):
        raise _error("final_run.answer缺少结构化证据。")
    return {
        "is_supported": value.get("is_supported"),
        "conclusion": value.get("conclusion"),
        "answer": value.get("answer"),
        "key_points": key_points,
        "evidence": evidence,
        "concepts": value.get("concepts"),
        "limitation": value.get("limitation"),
    }


def _selected_skeptic(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _error("final_run.skeptical_review必须是对象。")
    challenges = value.get("challenges")
    if not isinstance(challenges, list):
        raise _error("final_run.skeptical_review.challenges必须是数组。")
    return {
        "status": value.get("status"),
        "summary": value.get("summary"),
        "challenges": challenges,
        "limitation": value.get("limitation"),
    }


def _selected_verification(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _error("final_run.verification必须是对象。")
    checks = value.get("checks")
    if not isinstance(checks, list):
        raise _error("final_run.verification.checks必须是数组。")
    return {
        "status": value.get("status"),
        "summary": value.get("summary"),
        "checks": checks,
        "limitation": value.get("limitation"),
    }


def _normalise_verified_run(
    *,
    question: str,
    report_name: str,
    final_run: object,
    audit_record: object,
) -> dict[str, Any]:
    _reject_binary_or_non_json(final_run, "final_run")
    _reject_binary_or_non_json(audit_record, "audit_record")
    if not isinstance(final_run, Mapping):
        raise _error("final_run必须是对象。")
    if not isinstance(audit_record, Mapping):
        raise _error("audit_record必须是对象。")
    run_query = _required_text(
        final_run.get("query"), field="final_run.query", limit=1_000
    )
    if run_query != question:
        raise _error("年报问题与最终工作流查询不一致。")

    answer = _selected_answer(final_run.get("answer"))
    skeptic = _selected_skeptic(final_run.get("skeptical_review"))
    verification = _selected_verification(final_run.get("verification"))
    results = final_run.get("results")
    if not isinstance(results, list) or not results:
        raise _error("工作流没有可核验的年报检索证据。")
    result_maps = [item for item in results if isinstance(item, Mapping)]
    if len(result_maps) != len(results):
        raise _error("final_run.results包含无效检索结果。")

    try:
        recomputed = verify_answer(
            query=question,
            answer=answer,  # type: ignore[arg-type]
            skeptical_review=skeptic,  # type: ignore[arg-type]
            results=result_maps,  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("年报问答无法通过独立引用复核。") from exc

    provided_status = verification.get("status")
    if (
        provided_status not in _APPROVED_VERIFIER_STATUSES
        or recomputed["status"] != provided_status
        or not verification["checks"]
        or not all(
            isinstance(check, Mapping) and check.get("passed") is True
            for check in verification["checks"]
        )
    ):
        raise _error("Verifier未明确通过，年报问答不得写入案件。")
    if answer.get("is_supported") is not True:
        raise _error("年报问答证据不足，不得写入案件。")

    raw_answer_evidence = answer["evidence"]
    if not raw_answer_evidence or len(raw_answer_evidence) > MAX_ANSWER_EVIDENCE:
        raise _error("年报问答必须保留1至5条带页码证据。")
    answer_evidence: list[dict[str, object]] = []
    answer_pages: set[int] = set()
    for index, raw in enumerate(raw_answer_evidence):
        if not isinstance(raw, Mapping):
            raise _error("年报问答证据结构无效。")
        page = _positive_page(
            raw.get("page_number"), field=f"answer.evidence[{index}].page_number"
        )
        excerpt = _required_text(
            raw.get("excerpt"),
            field=f"answer.evidence[{index}].excerpt",
            limit=2_000,
        )
        if not _source_contains(excerpt, page, result_maps):
            raise _error("答案证据摘录无法在同页检索原文中复核。")
        answer_evidence.append(
            {
                "kind": "answer",
                "page_number": page,
                "excerpt": _compact_text(
                    excerpt, limit=MAX_EVIDENCE_EXCERPT_CHARS
                ),
            }
        )
        answer_pages.add(page)

    raw_points = answer["key_points"]
    if not raw_points:
        raise _error("年报问答缺少带页码的结论要点。")
    for index, raw in enumerate(raw_points):
        if not isinstance(raw, Mapping):
            raise _error("年报问答结论要点结构无效。")
        page = _positive_page(
            raw.get("page_number"), field=f"answer.key_points[{index}].page_number"
        )
        if page not in answer_pages:
            raise _error("结论要点引用了未保存的证据页码。")

    raw_challenges = skeptic["challenges"]
    if len(raw_challenges) > MAX_CHALLENGE_EVIDENCE:
        raise _error("反方证据超过单次桥接容量3条。")
    challenge_evidence: list[dict[str, object]] = []
    for index, raw in enumerate(raw_challenges):
        if not isinstance(raw, Mapping):
            raise _error("反方证据结构无效。")
        page = _positive_page(
            raw.get("page_number"),
            field=f"skeptical_review.challenges[{index}].page_number",
        )
        excerpt = _required_text(
            raw.get("excerpt"),
            field=f"skeptical_review.challenges[{index}].excerpt",
            limit=2_000,
        )
        if not _source_contains(excerpt, page, result_maps):
            raise _error("反方证据摘录无法在同页检索原文中复核。")
        challenge_evidence.append(
            {
                "kind": "challenge",
                "page_number": page,
                "excerpt": _compact_text(
                    excerpt, limit=MAX_EVIDENCE_EXCERPT_CHARS
                ),
                "trigger": _compact_text(raw.get("trigger"), limit=80),
            }
        )

    if audit_record.get("schema_version") != "1.0":
        raise _error("Agent审计记录schema版本不受支持。")
    if _compact_text(audit_record.get("report_name"), limit=300) != report_name:
        raise _error("Agent审计记录与年报名称不一致。")
    if _compact_text(audit_record.get("query"), limit=1_000) != question:
        raise _error("Agent审计记录与年报问题不一致。")
    if (
        audit_record.get("answer") != final_run.get("answer")
        or audit_record.get("skeptical_review")
        != final_run.get("skeptical_review")
        or audit_record.get("verification") != final_run.get("verification")
    ):
        raise _error("Agent审计记录与最终工作流输出不一致。")

    cited_pages = audit_record.get("cited_pdf_pages")
    if not isinstance(cited_pages, list):
        raise _error("Agent审计记录缺少PDF页码。")
    audit_pages = {
        _positive_page(page, field="audit_record.cited_pdf_pages")
        for page in cited_pages
    }
    selected_pages = {
        int(item["page_number"])
        for item in [*answer_evidence, *challenge_evidence]
    }
    if not selected_pages or not selected_pages.issubset(audit_pages):
        raise _error("Agent审计记录没有覆盖全部问答证据页码。")
    trace = audit_record.get("final_agent_trace")
    if not isinstance(trace, list) or not any(
        isinstance(step, Mapping)
        and step.get("role") == "Verifier"
        and step.get("status") == provided_status
        for step in trace
    ):
        raise _error("Agent审计记录没有保留通过状态的Verifier步骤。")

    route = final_run.get("route")
    route_map = route if isinstance(route, Mapping) else {}
    return {
        "answer_evidence": answer_evidence,
        "challenge_evidence": challenge_evidence,
        "conclusion": _required_text(
            answer.get("conclusion"), field="answer.conclusion", limit=1_000
        ),
        "answer_limitation": _compact_text(
            answer.get("limitation"), limit=1_000
        ),
        "skeptic_status": _compact_text(skeptic.get("status"), limit=80),
        "skeptic_summary": _compact_text(skeptic.get("summary"), limit=1_000),
        "skeptic_limitation": _compact_text(
            skeptic.get("limitation"), limit=1_000
        ),
        "verifier_status": str(provided_status),
        "verifier_summary": _compact_text(
            verification.get("summary"), limit=1_000
        ),
        "verifier_limitation": _compact_text(
            verification.get("limitation"), limit=1_000
        ),
        "route_mode": _compact_text(route_map.get("mode"), limit=80),
        "route_label": _compact_text(route_map.get("label"), limit=160),
        "cited_pages": sorted(audit_pages),
    }


def _merge_ids(existing: object, incoming: list[str], *, limit: int) -> list[str]:
    result = (
        [item for item in existing if isinstance(item, str)]
        if isinstance(existing, list)
        else []
    )
    for identifier in incoming:
        if identifier not in result:
            result.append(identifier)
    if len(result) > limit:
        raise ResearchCaseCapacityError(
            f"案件引用容量不足，最多允许{limit}项。"
        )
    return result


def _merge_contradiction(
    case: Mapping[str, object],
    *,
    contradiction: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    existing = [deepcopy(dict(item)) for item in case["case_brief"]["contradictions"]]
    if contradiction is None:
        return existing
    result = [
        item
        for item in existing
        if item["contradiction_id"] != contradiction["contradiction_id"]
    ]
    if len(result) >= MAX_CONTRADICTIONS:
        raise ResearchCaseCapacityError(
            f"case_brief.contradictions已达到容量{MAX_CONTRADICTIONS}。"
        )
    result.append(deepcopy(dict(contradiction)))
    return result


def build_annual_report_qa_case_patch(
    case: object,
    *,
    report_name: object,
    source_url: object,
    source_fingerprint_sha256: object,
    report_published_date: object,
    question: object,
    final_run: object,
    audit_record: object,
    emitted_at: object,
) -> dict[str, Any]:
    """Return a deterministic, preflighted annual-report Q&A CasePatch.

    Source-record excerpts use ``not_required`` because the Verifier has
    already rechecked their page-level provenance.  This does *not* promote
    the AI conclusion: it remains isolated in the analysis artifact and is
    explicitly marked as not being a fact.  Human numeric decisions continue
    to belong exclusively to the financial-snapshot review workflow.
    """
    validate_research_case(case)
    if not isinstance(case, Mapping):  # Static narrowing after validation.
        raise _error("研究案件必须是对象。")
    clean_report_name = _required_text(
        report_name, field="report_name", limit=300
    )
    clean_source_url = _required_text(
        source_url, field="source_url", limit=800
    )
    if not is_allowed_evidence_url(
        clean_source_url,
        source_tier="official_disclosure",
        company=case["company"],
    ):
        raise _error("年报来源必须是通过白名单校验的官方披露链接。")
    fingerprint = _required_text(
        source_fingerprint_sha256,
        field="source_fingerprint_sha256",
        limit=64,
    ).lower()
    if not _SHA256_PATTERN.fullmatch(fingerprint):
        raise _error("文件指纹必须是64位SHA-256十六进制文本。")
    published_date = _iso_date(
        report_published_date, field="report_published_date"
    )
    clean_emitted_at = _iso_datetime(emitted_at, field="emitted_at")
    emitted_date = datetime.fromisoformat(
        clean_emitted_at.replace("Z", "+00:00")
    ).date().isoformat()
    if published_date > emitted_date:
        raise _error("年报发布日期不能晚于补丁生成日。")
    if (
        case["scope"]["mode"] == "historical"
        and published_date > str(case["scope"]["as_of_date"])
    ):
        raise _error("历史案件不能写入截止日之后发布的年报问答。")
    clean_question = _required_text(question, field="question", limit=1_000)
    clean = _normalise_verified_run(
        question=clean_question,
        report_name=clean_report_name,
        final_run=final_run,
        audit_record=audit_record,
    )

    run_material = {
        "report": clean_report_name,
        "fingerprint": fingerprint,
        "published_date": published_date,
        "question": clean_question,
        "conclusion": clean["conclusion"],
        "verifier_status": clean["verifier_status"],
        "answer_evidence": clean["answer_evidence"],
        "challenge_evidence": clean["challenge_evidence"],
    }
    run_digest = hashlib.sha256(
        json.dumps(
            run_material,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    artifact_id = _identifier(
        "artifact-annualqa", str(case["case_id"]), run_digest
    )
    patch_id = _identifier(
        "patch-annualqa", str(case["case_id"]), run_digest
    )

    evidence: list[dict[str, object]] = []
    answer_ids: list[str] = []
    challenge_ids: list[str] = []
    for item in [*clean["answer_evidence"], *clean["challenge_evidence"]]:
        kind = str(item["kind"])
        page = int(item["page_number"])
        excerpt = str(item["excerpt"])
        evidence_id = _identifier(
            "ev-annualqa", artifact_id, kind, str(page), excerpt
        )
        evidence_item: dict[str, object] = {
            "evidence_id": evidence_id,
            "source_module": "annual_report",
            "source_tier": "official_disclosure",
            "title": _compact_text(
                f"{clean_report_name}｜"
                f"{'原文记录（主证据组）' if kind == 'answer' else '原文记录（限制组）'}"
                f"｜PDF第{page}页",
                limit=400,
            ),
            "source_url": clean_source_url,
            "published_date": published_date,
            "page_start": page,
            "page_end": page,
            "excerpt": excerpt,
            "review_status": "not_required",
            "basis": (
                "Verifier已将该短摘录与同一PDF页的检索原文重新比对；"
                "本条只记录官方原文，不包含AI结论或推断。"
            ),
        }
        evidence.append(evidence_item)
        (answer_ids if kind == "answer" else challenge_ids).append(evidence_id)

    evidence_ids = [*answer_ids, *challenge_ids]
    payload: dict[str, object] = {
        "schema": "annual-report-qa-analysis.v1",
        "report": {
            "name": clean_report_name,
            "source_url": clean_source_url,
            "published_date": published_date,
            "source_fingerprint_sha256": fingerprint,
        },
        "question": clean_question,
        "analysis_output": {
            "conclusion": clean["conclusion"],
            "answer_limitation": clean["answer_limitation"],
            "skeptic_status": clean["skeptic_status"],
            "skeptic_summary": clean["skeptic_summary"],
            "skeptic_limitation": clean["skeptic_limitation"],
            "verifier_status": clean["verifier_status"],
            "verifier_summary": clean["verifier_summary"],
            "verifier_limitation": clean["verifier_limitation"],
        },
        "workflow": {
            "route_mode": clean["route_mode"],
            "route_label": clean["route_label"],
            "cited_pdf_pages": clean["cited_pages"],
            "answer_evidence_ids": answer_ids,
            "challenge_evidence_ids": challenge_ids,
        },
        "controls": {
            "verifier_passed": True,
            "page_citations_required": True,
            "analysis_output_is_fact": False,
            "evidence_contains_generated_claim": False,
            "source_pdf_embedded": False,
            "retrieval_chunks_embedded": False,
        },
    }
    if _payload_size(payload) > ANNUAL_QA_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError(
            "年报问答artifact.payload超过桥接层12KB限制。"
        )

    prior_brief_evidence = case["case_brief"]["evidence"]
    brief_artifact_ids = _merge_ids(
        prior_brief_evidence["artifact_ids"],
        [artifact_id],
        limit=MAX_ARTIFACTS,
    )
    brief_evidence_ids = _merge_ids(
        prior_brief_evidence["evidence_ids"],
        evidence_ids,
        limit=MAX_EVIDENCE,
    )
    lane = case["questions"]["financial_quality"]
    lane_artifact_ids = _merge_ids(
        lane["artifact_ids"], [artifact_id], limit=MAX_ARTIFACTS
    )
    lane_evidence_ids = _merge_ids(
        lane["evidence_ids"], evidence_ids, limit=MAX_EVIDENCE
    )

    challenge_contradiction: dict[str, object] | None = None
    if challenge_ids:
        challenge_contradiction = {
            "contradiction_id": _identifier(
                "contradiction-annualqa", artifact_id
            ),
            "summary": _compact_text(
                "该年报问答的主证据组同时存在反方或限制性原文；"
                "应将两组官方原文一同展示，并继续判断证据如何相互约束。",
                limit=1_800,
            ),
            "artifact_ids": [artifact_id],
            "evidence_ids": evidence_ids,
        }

    contradictions = _merge_contradiction(
        case, contradiction=challenge_contradiction
    )

    previous_summary = _compact_text(
        prior_brief_evidence.get("summary"), limit=1_600
    )
    evidence_summary = _compact_text(
        "年报问答已保留官方来源、文件指纹、问题及"
        f"{len(evidence_ids)}条经Verifier复核的PDF原文记录；"
        "生成式结论未写入案件证据。"
        + (f" 既有摘要：{previous_summary}" if previous_summary else ""),
        limit=3_000,
    )
    primary_question = _compact_text(
        case["case_brief"].get("primary_question"), limit=1_000
    ) or clean_question
    has_caveats = bool(challenge_ids) or (
        clean["verifier_status"] == "approved_with_caveats"
    )
    lane_status = "in_progress" if has_caveats else "answered"
    question_summary = (
        f"已核验{len(answer_ids)}条年报原文记录；另有"
        f"{len(challenge_ids)}条限制性原文需要交叉核验。"
        if has_caveats
        else f"已核验{len(answer_ids)}条带精确页码的年报原文记录。"
    )

    patch: dict[str, Any] = {
        "patch_id": patch_id,
        "case_id": case["case_id"],
        "base_revision": case["revision"],
        "canonical_code": case["company"]["canonical_code"],
        "mode": case["scope"]["mode"],
        "as_of_date": case["scope"]["as_of_date"],
        "emitted_at": clean_emitted_at,
        "source_module": "annual_report",
        "artifact": {
            "artifact_id": artifact_id,
            "module": "annual_report",
            "title": _compact_text(
                f"{case['company']['name']}｜年报证据问答分析输出",
                limit=300,
            ),
            "generated_at": clean_emitted_at,
            "payload": payload,
            "review_status": "not_required",
        },
        "evidence": evidence,
        "case_brief_update": {
            "primary_question": primary_question,
            "evidence": {
                "summary": evidence_summary,
                "artifact_ids": brief_artifact_ids,
                "evidence_ids": brief_evidence_ids,
            },
            "contradictions": contradictions,
            "next_action": {
                "module": "financial_trend",
                "action": "把单份年报原文与跨期及其他官方材料交叉核验",
                "reason": "单份年报问答只能提供可追溯线索，不能单独形成完整研究判断。",
            },
        },
        "question_updates": {
            "financial_quality": {
                "status": lane_status,
                "summary": question_summary,
                "next_action": (
                    "把主证据与限制性段落交叉核验，并保留不确定性。"
                    if has_caveats
                    else "如需形成研究判断，继续与其他期间和官方材料交叉核验。"
                ),
                "artifact_ids": lane_artifact_ids,
                "evidence_ids": lane_evidence_ids,
            }
        },
        "audit_message": (
            "年报证据问答已通过机器引用检查；案件证据仅保存官方原文短摘录，"
            "未保存PDF、解析页或检索chunks，AI结论仅存在analysis_output中。"
        ),
    }

    # Preflight the complete atomic mutation, including historical cut-off,
    # source allow-list, source-record semantics and all reference IDs.
    apply_case_patch(case, patch)
    return patch
