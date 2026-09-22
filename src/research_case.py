"""Pure, bounded data contract for one traceable company research case.

The module deliberately has no Streamlit, pandas, network or filesystem
dependency.  Every public mutation returns a new JSON-serialisable object.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
import json
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
STORE_KEY = "wfz.research_cases.v1"

MAX_CASES = 5
MAX_STORE_COMMAND_IDS = 50
MAX_ARTIFACTS = 25
MAX_ARTIFACT_PAYLOAD_BYTES = 20_000
MAX_EVIDENCE = 50
MAX_HYPOTHESES = 10
MAX_AUDIT_LOG = 100
MAX_PATCH_IDS = 50
MAX_MIGRATION_IDS = 20
MAX_CONTRADICTIONS = 20
MAX_UNKNOWNS = 20
MAX_CASE_BYTES = 150_000
MAX_STORE_BYTES = 750_000

QUESTION_KEYS = (
    "recent_events",
    "market_change",
    "financial_quality",
    "point_in_time",
    "research_judgement",
)
QUESTION_STATUSES = {
    "not_started",
    "in_progress",
    "answered",
    "blocked",
    "needs_human_review",
}
SOURCE_MODULES = {
    "company_research",
    "comprehensive_research",
    "market_activity",
    "financial_snapshot",
    "annual_report",
    "financial_trend",
    "historical_lens",
    "evidence_delta",
    "research_thesis",
}
READINESS_STATES = {
    "draft",
    "in_progress",
    "needs_human_review",
    "ready_to_export",
}
REVIEW_STATUSES = {
    "not_required",
    "pending",
    "confirmed",
    "corrected",
    "rejected",
}
SOURCE_TIERS = {
    "official_disclosure",
    "official_company",
    "public_market_data",
    "user_provided",
}
HYPOTHESIS_STATUSES = {
    "待核验",
    "暂有证据支持",
    "出现反方证据",
    "已失效",
}

_OFFICIAL_DISCLOSURE_HOSTS = (
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
)
_PUBLIC_MARKET_DATA_HOSTS = (
    "eastmoney.com",
    "sina.com.cn",
    "qq.com",
    "gtimg.cn",
    "csindex.com.cn",
    "cnindex.com.cn",
)


class ResearchCaseValidationError(ValueError):
    """Raised when untrusted case data violates the v1 contract."""


class ResearchCaseConflictError(ValueError):
    """Raised when a command or patch was based on a stale revision."""


class ResearchCaseCapacityError(ValueError):
    """Raised instead of silently evicting user research data."""


def _error(message: str) -> ResearchCaseValidationError:
    return ResearchCaseValidationError(message)


def _required_text(value: object, field: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{field}必须是非空文本。")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise _error(f"{field}超过{limit}个字符。")
    return cleaned


def _optional_text(value: object, field: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise _error(f"{field}必须是文本。")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise _error(f"{field}超过{limit}个字符。")
    return cleaned


def _require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(f"{field}必须是非负整数。")
    return value


def _require_iso_date(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _error(f"{field}必须是ISO日期。")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _error(f"{field}必须是ISO日期。") from exc
    if parsed.isoformat() != value:
        raise _error(f"{field}必须使用YYYY-MM-DD格式。")
    return value


def _require_iso_datetime(value: object, field: str) -> str:
    if not isinstance(value, str) or "T" not in value:
        raise _error(f"{field}必须是ISO日期时间。")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(f"{field}必须是ISO日期时间。") from exc
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
    field: str,
) -> None:
    optional = optional or set()
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise _error(f"{field}缺少字段：{', '.join(sorted(missing))}。")
    if unknown:
        raise _error(f"{field}包含未知字段：{', '.join(sorted(unknown))}。")


def _validate_json_value(value: object, path: str = "payload") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        try:
            json.dumps(value, allow_nan=False)
        except ValueError as exc:
            raise _error(f"{path}不能包含NaN或Infinity。") from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error(f"{path}的对象键必须是文本。")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise _error(f"{path}只能包含标准JSON值。")


def _json_size(value: object, field: str) -> int:
    _validate_json_value(value, field)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return len(encoded)


def is_official_disclosure_url(value: object) -> bool:
    """Return True only for the four supported official disclosure domains."""
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and any(
        hostname == host or hostname.endswith(f".{host}")
        for host in _OFFICIAL_DISCLOSURE_HOSTS
    )


def _normalise_hostname(value: object, field: str) -> str:
    hostname = _required_text(value, field, limit=253).lower().rstrip(".")
    if (
        "://" in hostname
        or "/" in hostname
        or "." not in hostname
        or hostname.startswith(".")
        or hostname.endswith(".")
    ):
        raise _error(f"{field}必须是域名而不是完整URL。")
    return hostname


def _hostname_matches(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    return any(
        hostname == host or hostname.endswith(f".{host}")
        for host in allowed_hosts
    )


def is_allowed_evidence_url(
    value: object,
    *,
    source_tier: object,
    company: Mapping[str, object],
) -> bool:
    """Validate an evidence URL against its explicit provenance tier."""
    if not isinstance(value, str) or source_tier not in SOURCE_TIERS:
        return False
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not hostname:
        return False
    if source_tier == "official_disclosure":
        return _hostname_matches(hostname, _OFFICIAL_DISCLOSURE_HOSTS)
    if source_tier == "public_market_data":
        return _hostname_matches(hostname, _PUBLIC_MARKET_DATA_HOSTS)
    if source_tier == "official_company":
        allowed = tuple(company.get("official_domains", []))
        return bool(allowed) and _hostname_matches(hostname, allowed)
    # A user-provided source is allowed for research notes, but its tier makes
    # clear that the system has not promoted it to an official source.
    return source_tier == "user_provided"


def normalise_company_identity(value: object) -> dict[str, Any]:
    """Validate and copy the minimum public-company identity used by a case."""
    if not isinstance(value, Mapping):
        raise _error("company必须是对象。")
    _require_exact_keys(
        value,
        required={"code", "canonical_code", "name", "exchange"},
        optional={"exchange_name", "official_domains"},
        field="company",
    )
    code = _required_text(value.get("code"), "company.code", limit=6)
    name = _required_text(value.get("name"), "company.name", limit=120)
    exchange = _required_text(
        value.get("exchange"), "company.exchange", limit=2
    ).upper()
    canonical_code = _required_text(
        value.get("canonical_code"),
        "company.canonical_code",
        limit=16,
    ).upper()
    if len(code) != 6 or not code.isdigit():
        raise _error("company.code必须是6位股票代码。")
    if exchange not in {"SH", "SZ", "BJ"}:
        raise _error("company.exchange只支持SH、SZ或BJ。")
    if canonical_code != f"{code}.{exchange}":
        raise _error("company.canonical_code与股票代码、交易所不匹配。")
    result = {
        "code": code,
        "canonical_code": canonical_code,
        "name": name,
        "exchange": exchange,
    }
    if "exchange_name" in value:
        result["exchange_name"] = _optional_text(
            value.get("exchange_name"),
            "company.exchange_name",
            limit=80,
        )
    if "official_domains" in value:
        raw_domains = value.get("official_domains")
        if not isinstance(raw_domains, list) or len(raw_domains) > 10:
            raise _error("company.official_domains必须是最多10项的数组。")
        domains = [
            _normalise_hostname(item, "company.official_domains")
            for item in raw_domains
        ]
        if len(domains) != len(set(domains)):
            raise _error("company.official_domains包含重复域名。")
        result["official_domains"] = domains
    return result


def _normalise_scope(
    *,
    mode: object,
    as_of_date: object,
    effective_market_date: object,
) -> dict[str, str | None]:
    if mode not in {"current", "historical"}:
        raise _error("scope.mode只支持current或historical。")
    effective = _require_iso_date(
        effective_market_date, "scope.effective_market_date"
    )
    if mode == "current":
        if as_of_date is not None:
            raise _error("current案件的scope.as_of_date必须为null。")
        cutoff = None
    else:
        cutoff = _require_iso_date(as_of_date, "scope.as_of_date")
        if effective > cutoff:
            raise _error("历史案件的有效市场日不能晚于截止日。")
    return {
        "mode": str(mode),
        "as_of_date": cutoff,
        "effective_market_date": effective,
    }


def _new_questions() -> dict[str, dict[str, object]]:
    return {
        key: {
            "status": "not_started",
            "summary": "",
            "next_action": "",
            "updated_at": None,
            "source_modules": [],
            "artifact_ids": [],
            "evidence_ids": [],
        }
        for key in QUESTION_KEYS
    }


def _new_case_brief() -> dict[str, object]:
    return {
        "primary_question": "",
        "evidence": {
            "summary": "",
            "artifact_ids": [],
            "evidence_ids": [],
        },
        "contradictions": [],
        "unknowns": [],
        "next_action": {
            "module": None,
            "action": "",
            "reason": "",
        },
    }


def _validate_reference_ids(
    value: object,
    field: str,
    *,
    limit: int,
) -> None:
    if not isinstance(value, list) or len(value) > limit:
        raise _error(f"{field}必须是最多{limit}项的数组。")
    if len(value) != len(set(value)):
        raise _error(f"{field}包含重复编号。")
    for identifier in value:
        _required_text(identifier, field, limit=80)


def _validate_case_brief(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error("case_brief必须是对象。")
    _require_exact_keys(
        value,
        required={
            "primary_question",
            "evidence",
            "contradictions",
            "unknowns",
            "next_action",
        },
        field="case_brief",
    )
    _optional_text(
        value.get("primary_question"),
        "case_brief.primary_question",
        limit=1_000,
    )

    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise _error("case_brief.evidence必须是对象。")
    _require_exact_keys(
        evidence,
        required={"summary", "artifact_ids", "evidence_ids"},
        field="case_brief.evidence",
    )
    _optional_text(
        evidence.get("summary"),
        "case_brief.evidence.summary",
        limit=3_000,
    )
    _validate_reference_ids(
        evidence.get("artifact_ids"),
        "case_brief.evidence.artifact_ids",
        limit=MAX_ARTIFACTS,
    )
    _validate_reference_ids(
        evidence.get("evidence_ids"),
        "case_brief.evidence.evidence_ids",
        limit=MAX_EVIDENCE,
    )

    contradictions = value.get("contradictions")
    if not isinstance(contradictions, list) or len(contradictions) > MAX_CONTRADICTIONS:
        raise ResearchCaseCapacityError(
            f"case_brief.contradictions超过容量{MAX_CONTRADICTIONS}或格式错误。"
        )
    contradiction_ids: list[str] = []
    for item in contradictions:
        if not isinstance(item, Mapping):
            raise _error("case_brief.contradictions条目必须是对象。")
        _require_exact_keys(
            item,
            required={
                "contradiction_id",
                "summary",
                "artifact_ids",
                "evidence_ids",
            },
            field="case_brief.contradictions条目",
        )
        contradiction_ids.append(
            _required_text(
                item.get("contradiction_id"),
                "case_brief.contradiction_id",
                limit=80,
            )
        )
        _required_text(
            item.get("summary"),
            "case_brief.contradictions.summary",
            limit=2_000,
        )
        _validate_reference_ids(
            item.get("artifact_ids"),
            "case_brief.contradictions.artifact_ids",
            limit=MAX_ARTIFACTS,
        )
        _validate_reference_ids(
            item.get("evidence_ids"),
            "case_brief.contradictions.evidence_ids",
            limit=MAX_EVIDENCE,
        )
        if not item["artifact_ids"] and not item["evidence_ids"]:
            raise _error("每条contradiction至少必须引用一个artifact或evidence。")
    if len(contradiction_ids) != len(set(contradiction_ids)):
        raise _error("case_brief.contradictions包含重复编号。")

    unknowns = value.get("unknowns")
    if not isinstance(unknowns, list) or len(unknowns) > MAX_UNKNOWNS:
        raise ResearchCaseCapacityError(
            f"case_brief.unknowns超过容量{MAX_UNKNOWNS}或格式错误。"
        )
    unknown_ids: list[str] = []
    for item in unknowns:
        if not isinstance(item, Mapping):
            raise _error("case_brief.unknowns条目必须是对象。")
        _require_exact_keys(
            item,
            required={"unknown_id", "summary"},
            field="case_brief.unknowns条目",
        )
        unknown_ids.append(
            _required_text(
                item.get("unknown_id"),
                "case_brief.unknowns.unknown_id",
                limit=80,
            )
        )
        _required_text(
            item.get("summary"),
            "case_brief.unknowns.summary",
            limit=2_000,
        )
    if len(unknown_ids) != len(set(unknown_ids)):
        raise _error("case_brief.unknowns包含重复编号。")

    next_action = value.get("next_action")
    if not isinstance(next_action, Mapping):
        raise _error("case_brief.next_action必须是对象。")
    _require_exact_keys(
        next_action,
        required={"module", "action", "reason"},
        field="case_brief.next_action",
    )
    module = next_action.get("module")
    action = _optional_text(
        next_action.get("action"),
        "case_brief.next_action.action",
        limit=1_000,
    )
    reason = _optional_text(
        next_action.get("reason"),
        "case_brief.next_action.reason",
        limit=2_000,
    )
    if module is None:
        if action or reason:
            raise _error("next_action未指定module时action和reason必须为空。")
    elif module not in SOURCE_MODULES:
        raise _error("case_brief.next_action.module不在模块白名单。")
    elif not action or not reason:
        raise _error("next_action指定module后必须同时填写action和reason。")


def _validate_question(key: str, value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error(f"questions.{key}必须是对象。")
    _require_exact_keys(
        value,
        required={
            "status",
            "summary",
            "next_action",
            "updated_at",
            "source_modules",
            "artifact_ids",
            "evidence_ids",
        },
        field=f"questions.{key}",
    )
    if value.get("status") not in QUESTION_STATUSES:
        raise _error(f"questions.{key}.status不受支持。")
    _optional_text(
        value.get("summary"), f"questions.{key}.summary", limit=2_000
    )
    _optional_text(
        value.get("next_action"),
        f"questions.{key}.next_action",
        limit=1_000,
    )
    updated_at = value.get("updated_at")
    if updated_at is not None:
        _require_iso_datetime(updated_at, f"questions.{key}.updated_at")
    modules = value.get("source_modules")
    if not isinstance(modules, list) or len(modules) > len(SOURCE_MODULES):
        raise _error(f"questions.{key}.source_modules不合法。")
    if len(set(modules)) != len(modules) or any(
        module not in SOURCE_MODULES for module in modules
    ):
        raise _error(f"questions.{key}.source_modules不合法。")
    _validate_reference_ids(
        value.get("artifact_ids"),
        f"questions.{key}.artifact_ids",
        limit=MAX_ARTIFACTS,
    )
    _validate_reference_ids(
        value.get("evidence_ids"),
        f"questions.{key}.evidence_ids",
        limit=MAX_EVIDENCE,
    )


def _validate_artifact(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error("artifact必须是对象。")
    _require_exact_keys(
        value,
        required={
            "artifact_id",
            "module",
            "title",
            "generated_at",
            "payload",
            "review_status",
        },
        field="artifact",
    )
    _required_text(value.get("artifact_id"), "artifact.artifact_id", limit=80)
    if value.get("module") not in SOURCE_MODULES:
        raise _error("artifact.module不在白名单。")
    _required_text(value.get("title"), "artifact.title", limit=300)
    _require_iso_datetime(value.get("generated_at"), "artifact.generated_at")
    if _json_size(value.get("payload"), "artifact.payload") > MAX_ARTIFACT_PAYLOAD_BYTES:
        raise ResearchCaseCapacityError("单个artifact.payload超过20KB。")
    if value.get("review_status") not in REVIEW_STATUSES:
        raise _error("artifact.review_status不受支持。")


def _validate_evidence(value: object, *, case: Mapping[str, object]) -> None:
    if not isinstance(value, Mapping):
        raise _error("evidence必须是对象。")
    _require_exact_keys(
        value,
        required={
            "evidence_id",
            "source_module",
            "source_tier",
            "title",
            "source_url",
            "published_date",
            "review_status",
        },
        optional={
            "page_start",
            "page_end",
            "excerpt",
            "original_value",
            "unit",
            "basis",
        },
        field="evidence",
    )
    _required_text(value.get("evidence_id"), "evidence.evidence_id", limit=80)
    if value.get("source_module") not in SOURCE_MODULES:
        raise _error("evidence.source_module不在白名单。")
    if value.get("source_tier") not in SOURCE_TIERS:
        raise _error("evidence.source_tier不受支持。")
    _required_text(value.get("title"), "evidence.title", limit=400)
    url = _required_text(value.get("source_url"), "evidence.source_url", limit=800)
    if not is_allowed_evidence_url(
        url,
        source_tier=value.get("source_tier"),
        company=case["company"],
    ):
        raise _error("evidence.source_url与声明的source_tier或白名单不匹配。")
    published = _require_iso_date(
        value.get("published_date"), "evidence.published_date"
    )
    scope = case["scope"]
    if (
        scope["mode"] == "historical"
        and published > str(scope["as_of_date"])
    ):
        raise _error("历史案件不能写入截止日之后发布的证据。")
    has_page_start = "page_start" in value
    has_page_end = "page_end" in value
    if has_page_start != has_page_end:
        raise _error("evidence.page_start与page_end必须同时提供。")
    if has_page_start:
        page_start = value.get("page_start")
        page_end = value.get("page_end")
        if (
            isinstance(page_start, bool)
            or not isinstance(page_start, int)
            or page_start <= 0
            or isinstance(page_end, bool)
            or not isinstance(page_end, int)
            or page_end < page_start
        ):
            raise _error("evidence页码必须是有效的正整数区间。")
    if "excerpt" in value:
        _optional_text(value.get("excerpt"), "evidence.excerpt", limit=2_000)
    for field, limit in (
        ("original_value", 300),
        ("unit", 80),
        ("basis", 1_000),
    ):
        if field in value:
            _optional_text(value.get(field), f"evidence.{field}", limit=limit)
    if value.get("review_status") not in REVIEW_STATUSES:
        raise _error("evidence.review_status不受支持。")


def _validate_hypothesis(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error("hypothesis必须是对象。")
    _require_exact_keys(
        value,
        required={
            "hypothesis_id",
            "statement",
            "status",
            "updated_at",
            "source_module",
            "review_status",
        },
        optional={
            "topic",
            "confirmation_criteria",
            "invalidation_criteria",
            "review_note",
            "created_at",
        },
        field="hypothesis",
    )
    _required_text(
        value.get("hypothesis_id"), "hypothesis.hypothesis_id", limit=80
    )
    _required_text(value.get("statement"), "hypothesis.statement", limit=1_000)
    if value.get("status") not in HYPOTHESIS_STATUSES:
        raise _error("hypothesis.status不受支持。")
    if value.get("source_module") not in SOURCE_MODULES:
        raise _error("hypothesis.source_module不在白名单。")
    _require_iso_datetime(value.get("updated_at"), "hypothesis.updated_at")
    for field, limit in (
        ("topic", 80),
        ("confirmation_criteria", 1_000),
        ("invalidation_criteria", 1_000),
        ("review_note", 1_000),
    ):
        if field in value:
            _optional_text(value.get(field), f"hypothesis.{field}", limit=limit)
    if "created_at" in value:
        _require_iso_datetime(value.get("created_at"), "hypothesis.created_at")
    if value.get("review_status") not in REVIEW_STATUSES:
        raise _error("hypothesis.review_status不受支持。")


def _validate_tracking(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error("tracking必须是对象。")
    _require_exact_keys(
        value,
        required={"evidence_checked_at"},
        field="tracking",
    )
    if value.get("evidence_checked_at") is not None:
        _require_iso_datetime(
            value.get("evidence_checked_at"),
            "tracking.evidence_checked_at",
        )


def _validate_audit(value: object) -> None:
    if not isinstance(value, Mapping):
        raise _error("audit_log条目必须是对象。")
    _require_exact_keys(
        value,
        required={"at", "message"},
        optional={"source_module", "patch_id"},
        field="audit_log条目",
    )
    _require_iso_datetime(value.get("at"), "audit_log.at")
    _required_text(value.get("message"), "audit_log.message", limit=1_000)
    if "source_module" in value and value.get("source_module") not in SOURCE_MODULES:
        raise _error("audit_log.source_module不在白名单。")
    if "patch_id" in value:
        _required_text(value.get("patch_id"), "audit_log.patch_id", limit=80)


def _validate_case_references(case: Mapping[str, object]) -> None:
    artifact_ids = {item["artifact_id"] for item in case["artifacts"]}
    evidence_ids = {item["evidence_id"] for item in case["evidence"]}

    def require_existing(container: Mapping[str, object], field: str) -> None:
        missing_artifacts = set(container["artifact_ids"]) - artifact_ids
        missing_evidence = set(container["evidence_ids"]) - evidence_ids
        if missing_artifacts:
            raise _error(
                f"{field}.artifact_ids存在悬空引用："
                f"{', '.join(sorted(missing_artifacts))}。"
            )
        if missing_evidence:
            raise _error(
                f"{field}.evidence_ids存在悬空引用："
                f"{', '.join(sorted(missing_evidence))}。"
            )

    brief = case["case_brief"]
    require_existing(brief["evidence"], "case_brief.evidence")
    for item in brief["contradictions"]:
        require_existing(
            item,
            f"case_brief.contradictions[{item['contradiction_id']}]",
        )
    for key, question in case["questions"].items():
        require_existing(question, f"questions.{key}")


def _has_pending_review(case: Mapping[str, object]) -> bool:
    if any(
        question["status"] == "needs_human_review"
        for question in case["questions"].values()
    ):
        return True
    for collection_name in ("artifacts", "evidence"):
        for item in case[collection_name]:
            if item.get("review_status") == "pending":
                return True
    return any(
        item.get("review_status") == "pending"
        for item in case["hypotheses"]
    )


def has_formal_evidence_reference(case: Mapping[str, object]) -> bool:
    """Return whether the brief cites a real evidence record in this case.

    An artifact is an analysis output, not source evidence.  Checking the ID
    against ``case.evidence`` also prevents a summary or a dangling string from
    opening the formal-export gate.  Full contract validation remains the
    caller's responsibility and enforces the evidence provenance fields.
    """
    records = case.get("evidence", [])
    brief = case.get("case_brief", {})
    if not isinstance(records, list) or not isinstance(brief, Mapping):
        return False
    brief_evidence = brief.get("evidence", {})
    if not isinstance(brief_evidence, Mapping):
        return False
    referenced = brief_evidence.get("evidence_ids", [])
    if not isinstance(referenced, list):
        return False
    existing_ids = {
        item.get("evidence_id")
        for item in records
        if isinstance(item, Mapping)
        and isinstance(item.get("evidence_id"), str)
    }
    return any(
        isinstance(evidence_id, str) and evidence_id in existing_ids
        for evidence_id in referenced
    )


def calculate_readiness(case: Mapping[str, object]) -> str:
    """Derive readiness without an AI judgement or mutable hidden state."""
    if not case.get("artifacts"):
        return "draft"
    if _has_pending_review(case):
        return "needs_human_review"
    brief = case["case_brief"]
    evidence = brief["evidence"]
    next_action = brief["next_action"]
    questions = case["questions"]
    all_lanes_started = all(
        question["status"] != "not_started"
        for question in questions.values()
    )
    blocked_lanes_complete = all(
        question["status"] != "blocked"
        or (question["summary"].strip() and question["next_action"].strip())
        for question in questions.values()
    )
    has_substantive_lane = any(
        question["status"] in {"answered", "in_progress"}
        for question in questions.values()
    )
    has_evidence_reference = has_formal_evidence_reference(case)
    if (
        brief["primary_question"].strip()
        and evidence["summary"].strip()
        and has_evidence_reference
        and next_action["module"] in SOURCE_MODULES
        and next_action["action"].strip()
        and next_action["reason"].strip()
        and all_lanes_started
        and blocked_lanes_complete
        and has_substantive_lane
    ):
        return "ready_to_export"
    return "in_progress"


def new_research_case(
    case_id: object,
    company: object,
    *,
    mode: object,
    as_of_date: object,
    effective_market_date: object,
    created_at: object,
) -> dict[str, Any]:
    """Build a fresh bounded case with all five questions not started."""
    clean_case_id = _required_text(case_id, "case_id", limit=80)
    timestamp = _require_iso_datetime(created_at, "created_at")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "case_id": clean_case_id,
        "revision": 0,
        "company": normalise_company_identity(company),
        "scope": _normalise_scope(
            mode=mode,
            as_of_date=as_of_date,
            effective_market_date=effective_market_date,
        ),
        "lifecycle": "active",
        "readiness": "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
        "case_brief": _new_case_brief(),
        "questions": _new_questions(),
        "artifacts": [],
        "evidence": [],
        "hypotheses": [],
        "tracking": {"evidence_checked_at": None},
        "audit_log": [],
        "applied_patch_ids": [],
        "migration_ids": [],
    }
    validate_research_case(result)
    return result


def validate_research_case(value: object) -> None:
    """Raise a clear error if a case is not valid v1 JSON data."""
    if not isinstance(value, Mapping):
        raise _error("研究案件必须是对象。")
    required = {
        "schema_version",
        "case_id",
        "revision",
        "company",
        "scope",
        "lifecycle",
        "readiness",
        "created_at",
        "updated_at",
        "case_brief",
        "questions",
        "artifacts",
        "evidence",
        "hypotheses",
        "tracking",
        "audit_log",
        "applied_patch_ids",
        "migration_ids",
    }
    _require_exact_keys(value, required=required, field="研究案件")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise _error("研究案件schema_version不受支持。")
    _required_text(value.get("case_id"), "case_id", limit=80)
    _require_non_negative_int(value.get("revision"), "revision")
    normalise_company_identity(value.get("company"))
    scope = value.get("scope")
    if not isinstance(scope, Mapping):
        raise _error("scope必须是对象。")
    _require_exact_keys(
        scope,
        required={"mode", "as_of_date", "effective_market_date"},
        field="scope",
    )
    _normalise_scope(
        mode=scope.get("mode"),
        as_of_date=scope.get("as_of_date"),
        effective_market_date=scope.get("effective_market_date"),
    )
    if value.get("lifecycle") not in {"active", "archived"}:
        raise _error("lifecycle不受支持。")
    if value.get("readiness") not in READINESS_STATES:
        raise _error("readiness不受支持。")
    _require_iso_datetime(value.get("created_at"), "created_at")
    _require_iso_datetime(value.get("updated_at"), "updated_at")
    _validate_case_brief(value.get("case_brief"))

    questions = value.get("questions")
    if not isinstance(questions, Mapping) or set(questions) != set(QUESTION_KEYS):
        raise _error("questions必须且只能包含五条固定专题研究泳道。")
    for key in QUESTION_KEYS:
        _validate_question(key, questions[key])

    collections = (
        ("artifacts", MAX_ARTIFACTS, _validate_artifact),
        ("hypotheses", MAX_HYPOTHESES, _validate_hypothesis),
        ("audit_log", MAX_AUDIT_LOG, _validate_audit),
    )
    for field, limit, validator in collections:
        items = value.get(field)
        if not isinstance(items, list):
            raise _error(f"{field}必须是数组。")
        if len(items) > limit:
            raise ResearchCaseCapacityError(f"{field}超过容量{limit}。")
        for item in items:
            validator(item)

    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        raise _error("evidence必须是数组。")
    if len(evidence) > MAX_EVIDENCE:
        raise ResearchCaseCapacityError(f"evidence超过容量{MAX_EVIDENCE}。")
    for item in evidence:
        _validate_evidence(item, case=value)

    for field, id_field in (
        ("artifacts", "artifact_id"),
        ("evidence", "evidence_id"),
        ("hypotheses", "hypothesis_id"),
    ):
        identifiers = [item[id_field] for item in value[field]]
        if len(identifiers) != len(set(identifiers)):
            raise _error(f"{field}包含重复编号。")

    _validate_case_references(value)

    _validate_tracking(value.get("tracking"))
    for field, limit in (
        ("applied_patch_ids", MAX_PATCH_IDS),
        ("migration_ids", MAX_MIGRATION_IDS),
    ):
        identifiers = value.get(field)
        if not isinstance(identifiers, list) or len(identifiers) > limit:
            raise ResearchCaseCapacityError(f"{field}超过容量{limit}或格式错误。")
        if len(identifiers) != len(set(identifiers)):
            raise _error(f"{field}包含重复编号。")
        for identifier in identifiers:
            _required_text(identifier, field, limit=80)
    expected = calculate_readiness(value)
    if value.get("readiness") != expected:
        raise _error(f"readiness应由数据派生为{expected}。")
    if _json_size(dict(value), "研究案件") > MAX_CASE_BYTES:
        raise ResearchCaseCapacityError(
            f"研究案件JSON超过{MAX_CASE_BYTES}字节。"
        )


def _upsert_by_id(
    items: list[dict[str, Any]],
    incoming: dict[str, Any],
    id_field: str,
    *,
    limit: int,
    field: str,
) -> list[dict[str, Any]]:
    identifier = incoming[id_field]
    replaced = False
    result: list[dict[str, Any]] = []
    for item in items:
        if item[id_field] == identifier:
            result.append(deepcopy(incoming))
            replaced = True
        else:
            result.append(item)
    if not replaced:
        if len(result) >= limit:
            raise ResearchCaseCapacityError(f"{field}已达到容量{limit}。")
        result.append(deepcopy(incoming))
    return result


def _remember_recent_id(
    identifiers: list[str],
    identifier: str,
    *,
    limit: int,
) -> list[str]:
    """Keep a bounded retry window without blocking future valid commands.

    An identifier outside this window still carries an old base revision, so
    replay is rejected as stale rather than applied twice.
    """
    return [*identifiers[-(limit - 1) :], identifier]


def _validate_patch_envelope(patch: object) -> Mapping[str, object]:
    if not isinstance(patch, Mapping):
        raise _error("CasePatch必须是对象。")
    required = {
        "patch_id",
        "case_id",
        "base_revision",
        "canonical_code",
        "mode",
        "as_of_date",
        "emitted_at",
        "source_module",
    }
    optional = {
        "artifact",
        "evidence",
        "case_brief_update",
        "question_updates",
        "hypothesis_upserts",
        "hypothesis_delete_ids",
        "tracking",
        "audit_message",
    }
    _require_exact_keys(
        patch,
        required=required,
        optional=optional,
        field="CasePatch",
    )
    _required_text(patch.get("patch_id"), "patch_id", limit=80)
    _required_text(patch.get("case_id"), "case_id", limit=80)
    _require_non_negative_int(patch.get("base_revision"), "base_revision")
    _required_text(
        patch.get("canonical_code"), "canonical_code", limit=16
    )
    if patch.get("mode") not in {"current", "historical"}:
        raise _error("CasePatch.mode不受支持。")
    if patch.get("as_of_date") is not None:
        _require_iso_date(patch.get("as_of_date"), "CasePatch.as_of_date")
    _require_iso_datetime(patch.get("emitted_at"), "CasePatch.emitted_at")
    if patch.get("source_module") not in SOURCE_MODULES:
        raise _error("CasePatch.source_module不在白名单。")
    if not optional.intersection(patch):
        raise _error("CasePatch没有可应用内容。")
    return patch


def _apply_case_brief_update(
    current: Mapping[str, object],
    update: object,
) -> dict[str, object]:
    if not isinstance(update, Mapping) or not update:
        raise _error("CasePatch.case_brief_update必须是非空对象。")
    _require_exact_keys(
        update,
        required=set(),
        optional={
            "primary_question",
            "evidence",
            "contradictions",
            "unknowns",
            "next_action",
        },
        field="CasePatch.case_brief_update",
    )
    candidate = deepcopy(dict(current))
    for field, field_value in update.items():
        candidate[field] = deepcopy(field_value)
    _validate_case_brief(candidate)
    return candidate


def apply_case_patch(case: object, patch: object) -> dict[str, Any]:
    """Atomically apply a module patch or return unchanged on exact replay."""
    validate_research_case(case)
    envelope = _validate_patch_envelope(patch)
    current: Mapping[str, object] = case  # type: ignore[assignment]
    patch_id = str(envelope["patch_id"])
    if envelope["case_id"] != current["case_id"]:
        raise _error("CasePatch.case_id与目标案件不匹配。")
    if envelope["canonical_code"] != current["company"]["canonical_code"]:
        raise _error("CasePatch.canonical_code与目标案件不匹配。")
    if envelope["mode"] != current["scope"]["mode"]:
        raise _error("CasePatch.mode与目标案件不匹配。")
    if envelope["as_of_date"] != current["scope"]["as_of_date"]:
        raise _error("CasePatch.as_of_date与目标案件不匹配。")
    if patch_id in current["applied_patch_ids"]:
        return deepcopy(dict(current))
    if current["lifecycle"] != "active":
        raise _error("已归档案件不允许应用CasePatch。")
    if envelope["base_revision"] != current["revision"]:
        raise ResearchCaseConflictError("CasePatch基于过期的案件revision。")

    source_module = str(envelope["source_module"])
    emitted_at = str(envelope["emitted_at"])
    work = deepcopy(dict(current))

    if "artifact" in envelope:
        artifact = envelope.get("artifact")
        _validate_artifact(artifact)
        if artifact["module"] != source_module:
            raise _error("artifact.module必须与CasePatch.source_module一致。")
        work["artifacts"] = _upsert_by_id(
            work["artifacts"],
            dict(artifact),
            "artifact_id",
            limit=MAX_ARTIFACTS,
            field="artifacts",
        )

    if "evidence" in envelope:
        evidence_items = envelope.get("evidence")
        if not isinstance(evidence_items, list):
            raise _error("CasePatch.evidence必须是数组。")
        patch_evidence_ids: set[str] = set()
        for evidence in evidence_items:
            _validate_evidence(evidence, case=work)
            if evidence["source_module"] != source_module:
                raise _error(
                    "evidence.source_module必须与CasePatch.source_module一致。"
                )
            evidence_id = str(evidence["evidence_id"])
            if evidence_id in patch_evidence_ids:
                raise _error("CasePatch.evidence包含重复编号。")
            patch_evidence_ids.add(evidence_id)
            work["evidence"] = _upsert_by_id(
                work["evidence"],
                dict(evidence),
                "evidence_id",
                limit=MAX_EVIDENCE,
                field="evidence",
            )

    if "case_brief_update" in envelope:
        work["case_brief"] = _apply_case_brief_update(
            work["case_brief"],
            envelope.get("case_brief_update"),
        )

    if "question_updates" in envelope:
        updates = envelope.get("question_updates")
        if not isinstance(updates, Mapping) or not updates:
            raise _error("CasePatch.question_updates必须是非空对象。")
        if not set(updates).issubset(QUESTION_KEYS):
            raise _error("CasePatch.question_updates包含未知问题。")
        for key, update in updates.items():
            if not isinstance(update, Mapping):
                raise _error(f"question_updates.{key}必须是对象。")
            _require_exact_keys(
                update,
                required=set(),
                optional={
                    "status",
                    "summary",
                    "next_action",
                    "artifact_ids",
                    "evidence_ids",
                },
                field=f"question_updates.{key}",
            )
            if not update:
                raise _error(f"question_updates.{key}不能为空。")
            target = work["questions"][key]
            if "status" in update:
                if update.get("status") not in QUESTION_STATUSES:
                    raise _error(f"question_updates.{key}.status不受支持。")
                target["status"] = update["status"]
            if "summary" in update:
                target["summary"] = _optional_text(
                    update.get("summary"),
                    f"question_updates.{key}.summary",
                    limit=2_000,
                )
            if "next_action" in update:
                target["next_action"] = _optional_text(
                    update.get("next_action"),
                    f"question_updates.{key}.next_action",
                    limit=1_000,
                )
            if "artifact_ids" in update:
                _validate_reference_ids(
                    update.get("artifact_ids"),
                    f"question_updates.{key}.artifact_ids",
                    limit=MAX_ARTIFACTS,
                )
                target["artifact_ids"] = deepcopy(update["artifact_ids"])
            if "evidence_ids" in update:
                _validate_reference_ids(
                    update.get("evidence_ids"),
                    f"question_updates.{key}.evidence_ids",
                    limit=MAX_EVIDENCE,
                )
                target["evidence_ids"] = deepcopy(update["evidence_ids"])
            target["updated_at"] = emitted_at
            if source_module not in target["source_modules"]:
                target["source_modules"].append(source_module)

    delete_ids: list[str] = []
    if "hypothesis_delete_ids" in envelope:
        raw_delete_ids = envelope.get("hypothesis_delete_ids")
        if not isinstance(raw_delete_ids, list):
            raise _error("hypothesis_delete_ids必须是数组。")
        delete_ids = [
            _required_text(item, "hypothesis_delete_ids", limit=80)
            for item in raw_delete_ids
        ]
        if len(delete_ids) != len(set(delete_ids)):
            raise _error("hypothesis_delete_ids包含重复编号。")
        work["hypotheses"] = [
            item
            for item in work["hypotheses"]
            if item["hypothesis_id"] not in set(delete_ids)
        ]

    if "hypothesis_upserts" in envelope:
        raw_upserts = envelope.get("hypothesis_upserts")
        if not isinstance(raw_upserts, list):
            raise _error("hypothesis_upserts必须是数组。")
        seen_hypothesis_ids: set[str] = set()
        for hypothesis in raw_upserts:
            _validate_hypothesis(hypothesis)
            if hypothesis["source_module"] != source_module:
                raise _error(
                    "hypothesis.source_module必须与CasePatch.source_module一致。"
                )
            hypothesis_id = str(hypothesis["hypothesis_id"])
            if hypothesis_id in seen_hypothesis_ids:
                raise _error("hypothesis_upserts包含重复编号。")
            seen_hypothesis_ids.add(hypothesis_id)
            work["hypotheses"] = _upsert_by_id(
                work["hypotheses"],
                dict(hypothesis),
                "hypothesis_id",
                limit=MAX_HYPOTHESES,
                field="hypotheses",
            )

    if "tracking" in envelope:
        tracking = envelope.get("tracking")
        _validate_tracking(tracking)
        work["tracking"] = deepcopy(dict(tracking))

    if "audit_message" in envelope:
        message = _required_text(
            envelope.get("audit_message"),
            "CasePatch.audit_message",
            limit=1_000,
        )
        if len(work["audit_log"]) >= MAX_AUDIT_LOG:
            raise ResearchCaseCapacityError("audit_log已达到容量100。")
        work["audit_log"].append(
            {
                "at": emitted_at,
                "message": message,
                "source_module": source_module,
                "patch_id": patch_id,
            }
        )

    work["applied_patch_ids"] = _remember_recent_id(
        work["applied_patch_ids"],
        patch_id,
        limit=MAX_PATCH_IDS,
    )
    work["revision"] += 1
    work["updated_at"] = emitted_at
    work["readiness"] = calculate_readiness(work)
    validate_research_case(work)
    return work


def empty_research_case_store() -> dict[str, Any]:
    """Return a fresh JSON store for the future browser storage key."""
    return {
        "schema_version": SCHEMA_VERSION,
        "store_revision": 0,
        "active_case_id": None,
        "cases": {},
        "applied_command_ids": [],
    }


def validate_research_case_store(value: object) -> None:
    """Validate a complete store without coercing or dropping user data."""
    if not isinstance(value, Mapping):
        raise _error("ResearchCase Store必须是对象。")
    _require_exact_keys(
        value,
        required={
            "schema_version",
            "store_revision",
            "active_case_id",
            "cases",
            "applied_command_ids",
        },
        field="ResearchCase Store",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise _error("Store schema_version不受支持。")
    _require_non_negative_int(value.get("store_revision"), "store_revision")
    cases = value.get("cases")
    if not isinstance(cases, Mapping):
        raise _error("cases必须是对象。")
    if len(cases) > MAX_CASES:
        raise ResearchCaseCapacityError("cases已超过容量5。")
    for case_id, case in cases.items():
        if not isinstance(case_id, str) or case.get("case_id") != case_id:
            raise _error("cases键必须与case.case_id一致。")
        validate_research_case(case)
    active_case_id = value.get("active_case_id")
    if active_case_id is not None and active_case_id not in cases:
        raise _error("active_case_id指向不存在的案件。")
    command_ids = value.get("applied_command_ids")
    if not isinstance(command_ids, list) or len(command_ids) > MAX_STORE_COMMAND_IDS:
        raise ResearchCaseCapacityError("applied_command_ids超过容量50或格式错误。")
    if len(command_ids) != len(set(command_ids)):
        raise _error("applied_command_ids包含重复编号。")
    for command_id in command_ids:
        _required_text(command_id, "applied_command_ids", limit=80)
    if _json_size(dict(value), "ResearchCase Store") > MAX_STORE_BYTES:
        raise ResearchCaseCapacityError(
            f"ResearchCase Store JSON超过{MAX_STORE_BYTES}字节。"
        )


def _validate_store_command(command: object) -> Mapping[str, object]:
    if not isinstance(command, Mapping):
        raise _error("Store命令必须是对象。")
    common = {"command_id", "base_store_revision", "action", "emitted_at"}
    action = command.get("action")
    action_fields = {
        "create": {
            "case_id",
            "company",
            "mode",
            "as_of_date",
            "effective_market_date",
        },
        "activate": {"case_id"},
        "archive": {"case_id"},
        "delete_archived": {"case_id"},
        "roll_forward": {"case_id", "effective_market_date"},
        "apply_patch": {"patch"},
    }
    if action not in action_fields:
        raise _error("Store命令action不受支持。")
    _require_exact_keys(
        command,
        required=common | action_fields[str(action)],
        field="Store命令",
    )
    _required_text(command.get("command_id"), "command_id", limit=80)
    _require_non_negative_int(
        command.get("base_store_revision"), "base_store_revision"
    )
    _require_iso_datetime(command.get("emitted_at"), "emitted_at")
    return command


def _append_case_audit(
    case: dict[str, Any], *, at: str, message: str
) -> None:
    if len(case["audit_log"]) >= MAX_AUDIT_LOG:
        raise ResearchCaseCapacityError("audit_log已达到容量100。")
    case["audit_log"].append({"at": at, "message": message})


def reduce_research_case_store(
    store: object,
    command: object,
) -> dict[str, Any]:
    """Apply one idempotent, revision-checked Store command atomically."""
    validate_research_case_store(store)
    envelope = _validate_store_command(command)
    current: Mapping[str, object] = store  # type: ignore[assignment]
    command_id = str(envelope["command_id"])
    if command_id in current["applied_command_ids"]:
        return deepcopy(dict(current))
    if envelope["base_store_revision"] != current["store_revision"]:
        raise ResearchCaseConflictError("Store命令基于过期的store_revision。")

    action = str(envelope["action"])
    work = deepcopy(dict(current))
    cases: dict[str, dict[str, Any]] = work["cases"]
    emitted_at = str(envelope["emitted_at"])

    if action == "create":
        case_id = _required_text(envelope.get("case_id"), "case_id", limit=80)
        if case_id in cases:
            raise _error("case_id已经存在。")
        if len(cases) >= MAX_CASES:
            raise ResearchCaseCapacityError("cases已达到容量5。")
        cases[case_id] = new_research_case(
            case_id,
            envelope.get("company"),
            mode=envelope.get("mode"),
            as_of_date=envelope.get("as_of_date"),
            effective_market_date=envelope.get("effective_market_date"),
            created_at=emitted_at,
        )
        work["active_case_id"] = case_id
    elif action == "apply_patch":
        patch = _validate_patch_envelope(envelope.get("patch"))
        case_id = str(patch["case_id"])
        if case_id not in cases:
            raise _error("CasePatch目标案件不存在。")
        if patch["patch_id"] in cases[case_id]["applied_patch_ids"]:
            return deepcopy(dict(current))
        cases[case_id] = apply_case_patch(cases[case_id], patch)
    else:
        case_id = _required_text(envelope.get("case_id"), "case_id", limit=80)
        if case_id not in cases:
            raise _error("目标案件不存在。")
        if action == "activate":
            if cases[case_id]["lifecycle"] != "active":
                raise _error("已归档案件不能重新激活；请新建后续案件。")
            work["active_case_id"] = case_id
        elif action == "archive":
            case = cases[case_id]
            if case["lifecycle"] == "archived":
                raise _error("案件已经归档。")
            case["lifecycle"] = "archived"
            case["revision"] += 1
            case["updated_at"] = emitted_at
            _append_case_audit(case, at=emitted_at, message="案件已归档。")
            if work["active_case_id"] == case_id:
                work["active_case_id"] = None
        elif action == "delete_archived":
            if cases[case_id]["lifecycle"] != "archived":
                raise _error("只有已归档案件可以删除。")
            del cases[case_id]
            if work["active_case_id"] == case_id:
                work["active_case_id"] = None
        else:
            case = cases[case_id]
            if case["lifecycle"] != "active":
                raise _error("已归档案件不允许roll_forward。")
            if case["scope"]["mode"] != "current":
                raise _error("historical案件不允许roll_forward。")
            next_date = _require_iso_date(
                envelope.get("effective_market_date"),
                "effective_market_date",
            )
            previous_date = case["scope"]["effective_market_date"]
            if next_date <= previous_date:
                raise _error("current案件只能向后的市场日roll_forward。")
            case["scope"]["effective_market_date"] = next_date
            case["revision"] += 1
            case["updated_at"] = emitted_at
            _append_case_audit(
                case,
                at=emitted_at,
                message=f"有效市场日由{previous_date}推进至{next_date}。",
            )

    work["store_revision"] += 1
    work["applied_command_ids"] = _remember_recent_id(
        work["applied_command_ids"],
        command_id,
        limit=MAX_STORE_COMMAND_IDS,
    )
    validate_research_case_store(work)
    return work
