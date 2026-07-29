from types import SimpleNamespace

from src.llm_analyst import (
    LLMAnalysis,
    LLMEvidencePoint,
    run_llm_analyst,
    serialise_llm_run,
)


def _answer() -> dict:
    excerpt = (
        "Operating cash flow increased because working capital improved."
    )
    return {
        "is_supported": True,
        "conclusion": "The report contains direct evidence.",
        "answer": "The report contains direct evidence.",
        "key_points": [{"page_number": 29, "text": excerpt}],
        "evidence": [{"page_number": 29, "excerpt": excerpt}],
        "concepts": ["operating cash flow"],
        "limitation": "This is a narrow extractive answer.",
    }


def _skeptical_review() -> dict:
    return {
        "status": "no_counter_evidence_found",
        "summary": "No relevant offset was found in the retrieved passages.",
        "challenges": [],
        "limitation": "The check covers retrieved passages only.",
    }


def _verification(status: str = "approved") -> dict:
    return {
        "status": status,
        "summary": "Verified.",
        "checks": [],
        "limitation": "This is a provenance check.",
    }


def _valid_analysis() -> LLMAnalysis:
    excerpt = (
        "Operating cash flow increased because working capital improved."
    )
    return LLMAnalysis(
        conclusion="Working capital improvement supported cash flow.",
        evidence_points=[
            LLMEvidencePoint(
                claim="Working capital was the reported driver.",
                supporting_excerpt=excerpt,
                source_page=29,
            )
        ],
        limitation="The supplied evidence covers one reported driver.",
        no_investment_recommendation=True,
    )


class FakeResponses:
    def __init__(
        self,
        analysis: LLMAnalysis | None = None,
        error: Exception | None = None,
    ) -> None:
        self.analysis = analysis
        self.error = error
        self.kwargs: dict | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_parsed=self.analysis)


class FakeClient:
    def __init__(
        self,
        analysis: LLMAnalysis | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = FakeResponses(analysis=analysis, error=error)


class FakeQuotaError(Exception):
    status_code = 429
    body = {"code": "insufficient_quota"}


def test_llm_analyst_accepts_only_guardrail_checked_output() -> None:
    client = FakeClient(analysis=_valid_analysis())

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=client,
        model="test-model",
    )

    assert result["status"] == "completed"
    assert all(check["passed"] for check in result["checks"])
    assert result["analysis"].evidence_points[0].source_page == 29
    assert client.responses.kwargs["text_format"] is LLMAnalysis
    assert client.responses.kwargs["store"] is False


def test_llm_analyst_rejects_an_unverified_page() -> None:
    analysis = _valid_analysis()
    analysis.evidence_points[0].source_page = 30

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(analysis=analysis),
    )

    assert result["status"] == "fallback"
    page_check = next(
        check
        for check in result["checks"]
        if check["name"].startswith("Verified PDF pages")
    )
    assert page_check["passed"] is False
    assert result["analysis"] is None


def test_llm_analyst_rejects_a_non_verbatim_supporting_excerpt() -> None:
    analysis = _valid_analysis()
    analysis.evidence_points[0].supporting_excerpt = (
        "Management said working capital improved substantially."
    )

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(analysis=analysis),
    )

    assert result["status"] == "fallback"
    excerpt_check = next(
        check
        for check in result["checks"]
        if check["name"].startswith("Verbatim evidence")
    )
    assert excerpt_check["passed"] is False


def test_llm_analyst_rejects_an_invented_number() -> None:
    analysis = _valid_analysis()
    analysis.conclusion = "Operating cash flow improved by 25%."

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(analysis=analysis),
    )

    assert result["status"] == "fallback"
    number_check = next(
        check
        for check in result["checks"]
        if check["name"].startswith("Numeric grounding")
    )
    assert number_check["passed"] is False


def test_llm_analyst_rejects_investment_advice() -> None:
    analysis = _valid_analysis()
    analysis.conclusion = "Investors should buy the shares."

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(analysis=analysis),
    )

    assert result["status"] == "fallback"
    advice_check = next(
        check
        for check in result["checks"]
        if check["name"].startswith("No investment recommendation")
    )
    assert advice_check["passed"] is False


def test_llm_analyst_does_not_call_api_after_rejected_verification() -> None:
    client = FakeClient(error=AssertionError("API should not be called"))

    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(status="rejected"),
        client=client,
    )

    assert result["status"] == "fallback"
    assert client.responses.kwargs is None


def test_llm_analyst_safely_falls_back_when_api_fails() -> None:
    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(error=RuntimeError("temporary failure")),
    )

    assert result["status"] == "fallback"
    assert result["analysis"] is None


def test_llm_analyst_explains_missing_api_quota_without_raw_error() -> None:
    result = run_llm_analyst(
        query="为什么经营现金流增加？",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(error=FakeQuotaError("sensitive raw message")),
    )

    assert result["status"] == "fallback"
    assert "没有可用 API 额度" in result["summary"]
    assert "sensitive raw message" not in result["summary"]


def test_serialised_llm_run_contains_no_client_or_credentials() -> None:
    result = run_llm_analyst(
        query="Why did operating cash flow increase?",
        answer=_answer(),
        skeptical_review=_skeptical_review(),
        verification=_verification(),
        client=FakeClient(analysis=_valid_analysis()),
        model="test-model",
    )

    audit_data = serialise_llm_run(result)

    assert audit_data["model"] == "test-model"
    assert audit_data["analysis"]["evidence_points"][0]["source_page"] == 29
    assert "client" not in audit_data
    assert "api_key" not in str(audit_data).lower()
