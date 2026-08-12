import pytest

from src.cash_case_game import (
    build_cash_evidence_case,
    build_cash_timing_question,
    evaluate_cash_evidence_selection,
)


def test_cash_timing_question_separates_profit_from_cash() -> None:
    question = build_cash_timing_question(0)

    assert question["revenue_wan"] == 120
    assert question["expense_wan"] == 70
    assert question["cash_collected_wan"] == 0
    assert question["profit_effect_wan"] == 50
    assert question["cash_effect_wan"] == -70
    assert question["correct_option"] in question["options"]
    assert len(question["options"]) >= 5
    assert "应收款" in question["explanation"]


def test_wrong_attempt_receives_a_different_sheet_and_option_order() -> None:
    first = build_cash_timing_question(0)
    second = build_cash_timing_question(1)

    assert first["question_id"] != second["question_id"]
    assert first["prompt"] != second["prompt"]
    assert first["correct_option"] != second["correct_option"]
    assert first["options"] != second["options"]


def test_question_generation_remains_unique_across_many_retries() -> None:
    questions = [build_cash_timing_question(index) for index in range(25)]

    assert len({item["question_id"] for item in questions}) == 25
    assert len({item["prompt"] for item in questions}) == 25
    assert all(len(item["options"]) >= 5 for item in questions)


@pytest.mark.parametrize("attempt_index", [-1, 1.5, "1"])
def test_question_rejects_invalid_attempt_index(attempt_index: object) -> None:
    with pytest.raises(ValueError, match="题序号"):
        build_cash_timing_question(attempt_index)  # type: ignore[arg-type]


def test_evidence_case_contains_four_link_chain_and_two_distractions() -> None:
    evidence_case = build_cash_evidence_case(0)
    documents = {
        item["document_id"]: item for item in evidence_case["documents"]
    }

    assert len(documents) == 6
    assert set(evidence_case["required_document_ids"]) == {
        "contract_clause",
        "signed_acceptance",
        "ar_subledger",
        "post_period_receipt",
    }
    assert "内部讨论稿" in documents["executive_slide"]["body"]
    assert "看起来像普通运维表" in documents["signed_acceptance"]["title"]
    assert "年末标记“未逾期”" in documents["ar_subledger"]["body"]
    assert "发生在报告期后" in documents["post_period_receipt"]["footer"]
    assert "管理层演示稿" in evidence_case["explanation"]


def test_wrong_evidence_attempt_changes_material_details_and_order() -> None:
    first = build_cash_evidence_case(0)
    second = build_cash_evidence_case(1)

    assert first["case_id"] != second["case_id"]
    assert first["contract_amount_wan"] != second["contract_amount_wan"]
    assert first["outstanding_wan"] != second["outstanding_wan"]
    assert [item["document_id"] for item in first["documents"]] != [
        item["document_id"] for item in second["documents"]
    ]


@pytest.mark.parametrize("attempt_index", [-1, 2.5, "2"])
def test_evidence_case_rejects_invalid_attempt_index(
    attempt_index: object,
) -> None:
    with pytest.raises(ValueError, match="卷宗序号"):
        build_cash_evidence_case(attempt_index)  # type: ignore[arg-type]


def test_evidence_selection_requires_exact_complete_chain() -> None:
    evidence_case = build_cash_evidence_case(0)

    correct = evaluate_cash_evidence_selection(
        evidence_case,
        evidence_case["required_document_ids"],
    )
    incomplete = evaluate_cash_evidence_selection(
        evidence_case,
        ["contract_clause", "signed_acceptance"],
    )
    mixed = evaluate_cash_evidence_selection(
        evidence_case,
        ["contract_clause", "executive_slide", "celebration_chat"],
    )

    assert correct["is_correct"] is True
    assert incomplete["missing_count"] == 2
    assert incomplete["distraction_count"] == 0
    assert mixed["missing_count"] == 3
    assert mixed["distraction_count"] == 2
    assert "只能提供线索" in mixed["feedback"]


def test_evidence_selection_rejects_unknown_document() -> None:
    with pytest.raises(ValueError, match="不属于当前卷宗"):
        evaluate_cash_evidence_selection(
            build_cash_evidence_case(0),
            ["invented-document"],
        )
