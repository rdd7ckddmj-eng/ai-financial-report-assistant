from src.adaptive_escalation import decide_adaptive_escalation
from src.agent_router import route_question


def _result(text: str = "Revenue was 100.") -> dict:
    return {
        "page_number": 10,
        "chunk_index": 1,
        "text": text,
        "score": 10.0,
        "matched_terms": ["revenue"],
        "matched_concepts": ["revenue and sales"],
    }


def _answer(is_supported: bool = True) -> dict:
    evidence = [{"page_number": 10, "excerpt": "Revenue was 100."}]
    points = [{"page_number": 10, "text": "Revenue was 100."}]
    return {
        "is_supported": is_supported,
        "conclusion": "Supported" if is_supported else "Unsupported",
        "answer": "Supported" if is_supported else "Unsupported",
        "key_points": points if is_supported else [],
        "evidence": evidence if is_supported else [],
        "concepts": ["revenue and sales"],
        "limitation": "Evidence only.",
    }


def _skeptic(status: str = "no_counter_evidence_found") -> dict:
    challenges = (
        [
            {
                "page_number": 10,
                "excerpt": "Revenue growth was partly offset by inflation.",
                "trigger": "partly offset by",
            }
        ]
        if status == "counter_evidence_found"
        else []
    )
    return {
        "status": status,
        "summary": "Review complete.",
        "challenges": challenges,
        "limitation": "Explicit markers only.",
    }


def _verification(status: str = "approved") -> dict:
    return {
        "status": status,
        "summary": "Audit complete.",
        "checks": [],
        "limitation": "Provenance only.",
    }


def test_supported_quick_lookup_stays_at_initial_depth() -> None:
    route = route_question("What was revenue?")

    decision = decide_adaptive_escalation(
        current_route=route,
        answer=_answer(),
        skeptical_review=_skeptic(),
        verification=_verification(),
        results=[_result()],
    )

    assert decision["escalated"] is False
    assert decision["route"] == route
    assert decision["signals"] == []


def test_quick_lookup_escalates_when_counter_evidence_is_found() -> None:
    decision = decide_adaptive_escalation(
        current_route=route_question("What was revenue?"),
        answer=_answer(),
        skeptical_review=_skeptic("counter_evidence_found"),
        verification=_verification("approved_with_caveats"),
        results=[_result()],
    )

    assert decision["escalated"] is True
    assert decision["route"]["mode"] == "skeptical_analysis"
    assert decision["route"]["top_k"] == 6
    assert any("Counter-evidence" in signal for signal in decision["signals"])


def test_weak_but_marker_does_not_escalate_a_quick_lookup() -> None:
    weak_review = _skeptic("counter_evidence_found")
    weak_review["challenges"][0]["trigger"] = "but"

    decision = decide_adaptive_escalation(
        current_route=route_question("What was revenue?"),
        answer=_answer(),
        skeptical_review=weak_review,
        verification=_verification("approved_with_caveats"),
        results=[_result()],
    )

    assert decision["escalated"] is False
    assert decision["signals"] == []


def test_skeptical_analysis_escalates_to_deep_investigation() -> None:
    decision = decide_adaptive_escalation(
        current_route=route_question("Why did revenue increase?"),
        answer=_answer(),
        skeptical_review=_skeptic("counter_evidence_found"),
        verification=_verification("approved_with_caveats"),
        results=[_result()],
    )

    assert decision["escalated"] is True
    assert decision["route"]["mode"] == "deep_investigation"
    assert decision["route"]["top_k"] == 10


def test_period_mismatch_escalates_a_metric_question() -> None:
    decision = decide_adaptive_escalation(
        current_route=route_question("What is revenue growth?"),
        answer=_answer(),
        skeptical_review=_skeptic(),
        verification=_verification(),
        results=[
            _result(
                "Revenue for the 53 weeks ended 2026 was compared with "
                "the 52 weeks ended 2025."
            )
        ],
        metric_available=True,
    )

    assert decision["escalated"] is True
    assert decision["route"]["mode"] == "skeptical_analysis"
    assert decision["route"]["tool_name"] == "revenue_growth"
    assert any("53 weeks" in signal for signal in decision["signals"])


def test_period_mismatch_does_not_escalate_a_current_value_lookup() -> None:
    decision = decide_adaptive_escalation(
        current_route=route_question("What was revenue?"),
        answer=_answer(),
        skeptical_review=_skeptic(),
        verification=_verification(),
        results=[
            _result(
                "Revenue for the 53 weeks ended 2026 was compared with "
                "the 52 weeks ended 2025."
            )
        ],
    )

    assert decision["escalated"] is False
    assert decision["signals"] == []


def test_missing_evidence_triggers_bounded_escalation() -> None:
    decision = decide_adaptive_escalation(
        current_route=route_question("What was revenue?"),
        answer=None,
        skeptical_review=None,
        verification=None,
        results=[],
    )

    assert decision["escalated"] is True
    assert decision["route"]["mode"] == "skeptical_analysis"
    assert any("No matching" in signal for signal in decision["signals"])


def test_deep_route_does_not_escalate_beyond_maximum() -> None:
    route = route_question("Did management deliver on its guidance?")

    decision = decide_adaptive_escalation(
        current_route=route,
        answer=_answer(),
        skeptical_review=_skeptic("counter_evidence_found"),
        verification=_verification("approved_with_caveats"),
        results=[_result()],
    )

    assert decision["escalated"] is False
    assert decision["route"] == route
    assert decision["signals"]
