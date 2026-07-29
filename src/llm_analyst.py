"""Generate a readable explanation from already verified report evidence."""

import json
import os
import re
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from src.answer_verifier import VerificationResult
from src.grounded_answer import GroundedAnswer
from src.report_metric_tool import MetricToolResult
from src.skeptical_review import SkepticalReview


class LLMEvidencePoint(BaseModel):
    """One LLM-written claim linked to a verbatim report extract."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=500)
    supporting_excerpt: str = Field(min_length=1, max_length=700)
    source_page: int = Field(ge=1)


class LLMAnalysis(BaseModel):
    """Structured output accepted from the LLM before local validation."""

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(min_length=1, max_length=900)
    evidence_points: list[LLMEvidencePoint] = Field(
        min_length=1,
        max_length=4,
    )
    limitation: str = Field(min_length=1, max_length=700)
    no_investment_recommendation: bool


class LLMValidationCheck(TypedDict):
    """One deterministic guardrail applied after the LLM response."""

    name: str
    passed: bool
    detail: str


class LLMAnalystRun(TypedDict):
    """Safe result returned to the interface and audit record."""

    status: Literal["completed", "fallback", "disabled"]
    model: str
    analysis: LLMAnalysis | None
    checks: list[LLMValidationCheck]
    summary: str


SYSTEM_INSTRUCTIONS = """
You are the synthesis Agent in an evidence-controlled financial-report
workflow. Write a concise answer in the same language as the user's question.

Hard rules:
1. Use only the supplied verified evidence and deterministic metric result.
2. Never calculate, estimate, change, or add a financial number.
3. Every evidence point must contain a supporting_excerpt copied verbatim
   from one supplied excerpt and must use that excerpt's PDF page.
4. Explain uncertainty and relevant counter-evidence.
5. Do not recommend buying, selling, holding, or investing in a security.
6. Set no_investment_recommendation to true.
7. If the evidence is narrow, say so in limitation rather than filling gaps.
""".strip()

NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")
ADVICE_PATTERN = re.compile(
    r"\b(?:buy|sell|hold|overweight|underweight|invest)\b"
    r"|买入|卖出|持有|增持|减持|投资建议|建议投资",
    re.IGNORECASE,
)


def _not_run(
    status: Literal["fallback", "disabled"],
    model: str,
    summary: str,
    checks: list[LLMValidationCheck] | None = None,
) -> LLMAnalystRun:
    """Return a consistent safe result when the LLM cannot be displayed."""
    return {
        "status": status,
        "model": model,
        "analysis": None,
        "checks": checks or [],
        "summary": summary,
    }


def _normalise_text(text: str) -> str:
    """Normalise whitespace for exact excerpt checks."""
    return " ".join(text.replace("\xa0", " ").split()).strip().lower()


def _number_tokens(text: str) -> set[str]:
    """Return comparable digit tokens without thousands separators."""
    return {
        match.group(0).replace(",", "")
        for match in NUMBER_PATTERN.finditer(text)
    }


def _safe_api_failure_summary(error: Exception, chinese: bool) -> str:
    """Explain common API failures without exposing request or secret data."""
    body = getattr(error, "body", None)
    error_code = body.get("code") if isinstance(body, dict) else None
    status_code = getattr(error, "status_code", None)

    if error_code == "insufficient_quota":
        return (
            "API 密钥已被平台识别，但当前项目没有可用 API 额度。"
            "页面已自动保留经过验证的原始答案。"
            if chinese
            else (
                "The API key was recognised, but this project has no "
                "available API quota. The page kept the verified original "
                "answer."
            )
        )
    if status_code in {401, 403}:
        return (
            "API 密钥或项目权限未通过平台验证，页面已自动保留原始答案。"
            if chinese
            else (
                "The API key or project permission was not accepted. The "
                "page kept the verified original answer."
            )
        )
    if status_code == 429:
        return (
            "API 当前达到请求限制，页面已自动保留经过验证的原始答案。"
            if chinese
            else (
                "The API is currently rate-limited. The page kept the "
                "verified original answer."
            )
        )
    return (
        "LLM 请求没有完成，页面已自动退回经过验证的原始答案。"
        if chinese
        else (
            "The LLM request did not complete. The page automatically kept "
            "the verified original answer."
        )
    )


def _verified_sources(
    answer: GroundedAnswer,
    skeptical_review: SkepticalReview,
) -> list[dict[str, object]]:
    """Build the only report text that the LLM is allowed to use."""
    sources: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()

    for source_type, items in (
        ("answer_evidence", answer["evidence"]),
        ("counter_evidence", skeptical_review["challenges"]),
    ):
        for item in items:
            text = item.get("excerpt", "")
            key = (item["page_number"], _normalise_text(text))
            if not text or key in seen:
                continue
            sources.append(
                {
                    "source_type": source_type,
                    "page_number": item["page_number"],
                    "excerpt": text,
                }
            )
            seen.add(key)

    return sources


def _metric_context(
    metric_result: MetricToolResult | None,
) -> dict[str, object] | None:
    """Expose calculated facts without asking the LLM to recalculate them."""
    if metric_result is None or not metric_result["is_available"]:
        return None
    return {
        "label": metric_result["label"],
        "display_value": metric_result["display_value"],
        "formula": metric_result["formula"],
        "inputs": metric_result["inputs"],
        "source_page": metric_result["source_page"],
        "comparability_messages": metric_result["messages"],
    }


def _validate_analysis(
    analysis: LLMAnalysis,
    sources: list[dict[str, object]],
    metric_context: dict[str, object] | None,
) -> list[LLMValidationCheck]:
    """Check citations, excerpts, numbers, and advice locally in Python."""
    sources_by_page: dict[int, list[str]] = {}
    for source in sources:
        page_number = int(source["page_number"])
        sources_by_page.setdefault(page_number, []).append(
            str(source["excerpt"])
        )

    pages_passed = all(
        point.source_page in sources_by_page
        for point in analysis.evidence_points
    )
    excerpts_passed = pages_passed and all(
        any(
            _normalise_text(point.supporting_excerpt)
            in _normalise_text(source_text)
            for source_text in sources_by_page[point.source_page]
        )
        for point in analysis.evidence_points
    )

    allowed_fact_text = json.dumps(
        {
            "verified_sources": sources,
            "deterministic_metric": metric_context,
        },
        ensure_ascii=False,
    )
    allowed_numbers = _number_tokens(allowed_fact_text)
    generated_text = " ".join(
        [
            analysis.conclusion,
            analysis.limitation,
            *[
                f"{point.claim} {point.supporting_excerpt}"
                for point in analysis.evidence_points
            ],
        ]
    )
    generated_numbers = _number_tokens(generated_text)
    numbers_passed = generated_numbers.issubset(allowed_numbers)

    advice_text = " ".join(
        [
            analysis.conclusion,
            analysis.limitation,
            *[point.claim for point in analysis.evidence_points],
        ]
    )
    advice_passed = (
        analysis.no_investment_recommendation
        and ADVICE_PATTERN.search(advice_text) is None
    )

    return [
        {
            "name": "Verified PDF pages / 已验证页码",
            "passed": pages_passed,
            "detail": (
                "Every LLM evidence point uses a page already approved by "
                "the deterministic workflow."
            ),
        },
        {
            "name": "Verbatim evidence / 原文证据",
            "passed": excerpts_passed,
            "detail": (
                "Every supporting excerpt exists verbatim on its cited "
                "verified PDF page."
            ),
        },
        {
            "name": "Numeric grounding / 数字约束",
            "passed": numbers_passed,
            "detail": (
                "The LLM introduced no digit-based figure outside the "
                "verified evidence or Python metric result."
            ),
        },
        {
            "name": "No investment recommendation / 无投资建议",
            "passed": advice_passed,
            "detail": (
                "The generated text contains no buy, sell, hold, or "
                "investment recommendation."
            ),
        },
    ]


def run_llm_analyst(
    query: str,
    answer: GroundedAnswer | None,
    skeptical_review: SkepticalReview | None,
    verification: VerificationResult | None,
    metric_result: MetricToolResult | None = None,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> LLMAnalystRun:
    """Call the LLM only after deterministic evidence verification."""
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
    chinese_query = bool(CHINESE_CHARACTER_PATTERN.search(query))

    if (
        answer is None
        or skeptical_review is None
        or verification is None
        or not answer["is_supported"]
        or verification["status"] not in {"approved", "approved_with_caveats"}
    ):
        summary = (
            "LLM 未运行：确定性证据或验证状态尚未达到安全门槛。"
            if chinese_query
            else (
                "The LLM did not run because the deterministic evidence or "
                "verification status did not meet the safety threshold."
            )
        )
        return _not_run("fallback", model_name, summary)

    sources = _verified_sources(answer, skeptical_review)
    if not sources:
        return _not_run(
            "fallback",
            model_name,
            "LLM 未运行：没有可交给模型的已验证证据。"
            if chinese_query
            else "The LLM did not run because no verified evidence was available.",
        )

    if client is None and not os.getenv("OPENAI_API_KEY"):
        return _not_run(
            "disabled",
            model_name,
            "LLM Agent 未启用：本机环境中没有 API 密钥。"
            if chinese_query
            else "The LLM Agent is disabled because no local API key was found.",
        )

    metric_context = _metric_context(metric_result)
    context = {
        "question": query,
        "verifier_status": verification["status"],
        "verified_evidence": sources,
        "deterministic_metric": metric_context,
        "required_language": "Chinese" if chinese_query else "English",
    }

    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        response = client.responses.parse(
            model=model_name,
            input=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                },
            ],
            text_format=LLMAnalysis,
            max_output_tokens=1_000,
            store=False,
        )
        analysis = response.output_parsed
    except Exception as error:
        return _not_run(
            "fallback",
            model_name,
            _safe_api_failure_summary(error, chinese_query),
        )

    if analysis is None:
        return _not_run(
            "fallback",
            model_name,
            "LLM 没有返回可验证的结构化内容，已使用原始答案。"
            if chinese_query
            else (
                "The LLM returned no verifiable structured content, so the "
                "original answer was kept."
            ),
        )

    checks = _validate_analysis(
        analysis=analysis,
        sources=sources,
        metric_context=metric_context,
    )
    if not all(check["passed"] for check in checks):
        return _not_run(
            "fallback",
            model_name,
            (
                "LLM 内容未通过本地保护检查，已自动退回经过验证的原始答案。"
                if chinese_query
                else (
                    "The LLM content failed a local guardrail, so the page "
                    "automatically kept the verified original answer."
                )
            ),
            checks=checks,
        )

    return {
        "status": "completed",
        "model": model_name,
        "analysis": analysis,
        "checks": checks,
        "summary": (
            "LLM 分析已通过本地证据、数字、页码和投资建议检查。"
            if chinese_query
            else (
                "The LLM analysis passed the local evidence, number, page, "
                "and investment-advice checks."
            )
        ),
    }


def serialise_llm_run(result: LLMAnalystRun) -> dict[str, object]:
    """Convert a run to JSON-safe audit data without including credentials."""
    return {
        "status": result["status"],
        "model": result["model"],
        "analysis": (
            result["analysis"].model_dump()
            if result["analysis"] is not None
            else None
        ),
        "checks": result["checks"],
        "summary": result["summary"],
    }
