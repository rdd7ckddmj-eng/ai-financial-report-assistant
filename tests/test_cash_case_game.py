from datetime import date

import pytest

from src.cash_case_game import (
    build_cash_cross_check_task,
    build_cash_defense_committee_public_task,
    build_cash_defense_question,
    build_cash_evidence_case,
    build_cash_evidence_lab_public_task,
    build_cash_timing_question,
    evaluate_cash_clock_assignment,
    evaluate_cash_clock_bins,
    evaluate_cash_evidence_chain,
    evaluate_cash_evidence_classification,
    evaluate_cash_evidence_reading,
    evaluate_cash_evidence_selection,
    evaluate_cash_gap_hypothesis,
    evaluate_cash_investigation_orders,
    evaluate_cash_defense_committee,
    normalise_cash_clock_command,
    normalise_cash_defense_committee_command,
    normalise_cash_evidence_lab_command,
)


def _cash_clock_envelope(
    question: dict[str, object],
    action: str,
    **payload: object,
) -> dict[str, object]:
    """Build the public command envelope used by the browser component."""

    return {
        "schema_version": 1,
        "command_id": f"test-{action}-1",
        "question_id": question["question_id"],
        "revision": 3,
        "action": action,
        **payload,
    }


def _evidence_lab_envelope(
    evidence_case: dict[str, object],
    action: str,
    **payload: object,
) -> dict[str, object]:
    """Build one command sent by the Stage 5--7 browser component."""

    return {
        "schema_version": 1,
        "command_id": f"test-lab-{action}-1",
        "task_id": f"cash-evidence-lab:{evidence_case['case_id']}",
        "revision": 7,
        "action": action,
        **payload,
    }


def _defense_committee_envelope(
    task: dict[str, object],
    placements: dict[str, str],
    **overrides: object,
) -> dict[str, object]:
    """Build one formal three-seat committee submission."""

    command: dict[str, object] = {
        "schema_version": 1,
        "command_id": "test-defense-committee-1",
        "task_id": task["task_id"],
        "revision": 5,
        "action": "submit_committee_statement",
        "placements": placements,
    }
    command.update(overrides)
    return command


def _correct_cash_clock_bins(question: dict[str, object]) -> dict[str, str]:
    """Derive expected test placements from public semantic fact flags."""

    bins: dict[str, str] = {}
    for event in question["event_cards"]:  # type: ignore[union-attr]
        if event["affects_profit"] and event["affects_cash"]:
            bucket = "both"
        elif event["affects_profit"]:
            bucket = "profit"
        elif event["affects_cash"]:
            bucket = "cash"
        else:
            bucket = "neither"
        bins[event["event_id"]] = bucket
    return bins


def test_cash_timing_question_separates_profit_from_cash() -> None:
    question = build_cash_timing_question(0)

    assert question["revenue_wan"] == 120
    assert question["expense_wan"] == 70
    assert question["cash_collected_wan"] == 20
    assert question["profit_effect_wan"] == 50
    assert question["cash_effect_wan"] == -50
    assert question["correct_inference_option"] in question["inference_options"]
    assert len(question["inference_options"]) == 6
    assert "应收款" in question["explanation"]
    assert question["correct_profit_event_ids"] == [
        "service_completed",
        "expense_incurred",
    ]
    assert question["correct_cash_event_ids"] == [
        "expense_paid",
        "cash_collected",
    ]
    assert "不是比谁更会按日期排队" in question["reasoning_explanation"]
    assert "未来付款计划" in question["reasoning_explanation"]


def test_new_attempt_receives_a_different_sheet_and_option_order() -> None:
    first = build_cash_timing_question(0)
    second = build_cash_timing_question(1)

    assert first["question_id"] != second["question_id"]
    assert first["prompt"] != second["prompt"]
    assert (
        first["correct_inference_option"]
        != second["correct_inference_option"]
    )
    assert first["inference_options"] != second["inference_options"]
    assert first["event_cards"] != second["event_cards"]


def test_question_generation_remains_unique_across_many_retries() -> None:
    questions = [build_cash_timing_question(index) for index in range(25)]

    assert len({item["question_id"] for item in questions}) == 25
    assert len({item["prompt"] for item in questions}) == 25
    assert all(len(item["inference_options"]) == 6 for item in questions)


def test_one_thousand_dossiers_only_contain_real_calendar_dates() -> None:
    """Retries must never manufacture labels such as 12月32日."""

    for attempt_index in range(1_000):
        question = build_cash_timing_question(attempt_index)
        reporting_date = question["reporting_date"]

        assert reporting_date == date(2025, 12, 31)
        for event in question["event_cards"]:
            event_date = event["event_date"]
            assert isinstance(event_date, date)
            expected_prefix = (
                "次年" if event_date.year > reporting_date.year else ""
            )
            assert event["date_label"] == (
                f"{expected_prefix}{event_date.month}月{event_date.day}日"
            )
            if event["affects_profit"] or event["affects_cash"]:
                assert event_date <= reporting_date


def test_cash_clock_assignment_requires_fact_attribution() -> None:
    question = build_cash_timing_question(0)

    correct = evaluate_cash_clock_assignment(
        question,
        question["correct_profit_event_ids"],
        question["correct_cash_event_ids"],
    )
    assert correct == {
        "is_correct": True,
        "profit_is_correct": True,
        "cash_is_correct": True,
        "feedback": (
            "归因成立：验收与已经发生的相关成本进入利润时钟；真实回款"
            "与费用支付进入现金时钟。成本发生和付款是两件不同的事。"
        ),
    }

    cash_mixed_with_promises = evaluate_cash_clock_assignment(
        question,
        question["correct_profit_event_ids"],
        ["cash_collected", "future_payment_plan"],
    )
    assert not cash_mixed_with_promises["is_correct"]
    assert cash_mixed_with_promises["profit_is_correct"]
    assert not cash_mixed_with_promises["cash_is_correct"]
    assert "付款承诺" in cash_mixed_with_promises["feedback"]


def test_event_fact_flags_match_the_expected_clock_assignments() -> None:
    """The answer derives from semantic flags rather than chronological order."""

    question = build_cash_timing_question(3)
    profit_ids = {
        event["event_id"]
        for event in question["event_cards"]
        if event["affects_profit"]
    }
    cash_ids = {
        event["event_id"]
        for event in question["event_cards"]
        if event["affects_cash"]
    }

    assert profit_ids == set(question["correct_profit_event_ids"])
    assert cash_ids == set(question["correct_cash_event_ids"])
    assert not profit_ids & cash_ids
    assert {event["event_id"] for event in question["event_cards"]} - (
        profit_ids | cash_ids
    ) == {"contract_signed", "future_payment_plan"}


def test_visual_game_command_normalises_routes_without_answer_key() -> None:
    question = build_cash_timing_question(0)
    bins = _correct_cash_clock_bins(question)
    command = _cash_clock_envelope(
        question,
        "submit_routes",
        bins=bins,
    )

    normalised = normalise_cash_clock_command(question, command, 3)

    assert normalised == {
        "schema_version": 1,
        "command_id": "test-submit_routes-1",
        "question_id": question["question_id"],
        "revision": 3,
        "action": "submit_routes",
        "clean_payload": {"bins": bins},
    }
    assert "correct_bins" not in normalised
    assert "answer" not in normalised["clean_payload"]


def test_visual_game_command_rejects_stale_revision() -> None:
    question = build_cash_timing_question(0)
    command = _cash_clock_envelope(
        question,
        "submit_routes",
        bins=_correct_cash_clock_bins(question),
    )

    with pytest.raises(ValueError, match="revision已经过期"):
        normalise_cash_clock_command(question, command, 4)


def test_visual_game_command_rejects_wrong_question_and_schema() -> None:
    question = build_cash_timing_question(0)
    command = _cash_clock_envelope(
        question,
        "submit_routes",
        bins=_correct_cash_clock_bins(question),
    )
    command["question_id"] = "another-question"

    with pytest.raises(ValueError, match="question_id"):
        normalise_cash_clock_command(question, command, 3)

    command["question_id"] = question["question_id"]
    command["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        normalise_cash_clock_command(question, command, 3)


def test_route_command_requires_all_and_only_current_event_ids() -> None:
    question = build_cash_timing_question(0)
    bins = _correct_cash_clock_bins(question)
    missing_bins = dict(bins)
    missing_bins.pop("contract_signed")
    unknown_bins = {**bins, "invented-event": "cash"}

    with pytest.raises(ValueError, match="缺少事实卡"):
        normalise_cash_clock_command(
            question,
            _cash_clock_envelope(
                question,
                "submit_routes",
                bins=missing_bins,
            ),
            3,
        )
    with pytest.raises(ValueError, match="未知事实卡"):
        normalise_cash_clock_command(
            question,
            _cash_clock_envelope(
                question,
                "submit_routes",
                bins=unknown_bins,
            ),
            3,
        )


def test_cash_clock_bins_accept_all_correct_routes() -> None:
    question = build_cash_timing_question(0)
    bins = _correct_cash_clock_bins(question)

    result = evaluate_cash_clock_bins(
        question,
        _cash_clock_envelope(question, "submit_routes", bins=bins),
        3,
    )

    assert result["phase"] == "routes"
    assert result["action"] == "submit_routes"
    assert result["complete"] is True
    assert result["rejected"] == []
    assert set(result["accepted"]) == set(bins)
    assert "履约" in result["feedback"]


def test_cash_clock_bins_preserve_correct_cards_on_partial_error() -> None:
    question = build_cash_timing_question(0)
    bins = _correct_cash_clock_bins(question)
    bins["service_completed"] = "cash"
    bins["future_payment_plan"] = "both"

    result = evaluate_cash_clock_bins(
        question,
        _cash_clock_envelope(question, "submit_routes", bins=bins),
        3,
    )

    assert result["complete"] is False
    assert set(result["rejected"]) == {
        "service_completed",
        "future_payment_plan",
    }
    assert set(result["accepted"]) == set(bins) - set(result["rejected"])
    assert "承诺" in result["feedback"]


@pytest.mark.parametrize(
    ("hypothesis_id", "complete", "feedback_fragment"),
    [
        ("receivable_pending", True, "尚未成为结论"),
        ("proven_fraud", False, "不能直接证明造假"),
        ("customer_default", False, "不能把未收款直接升级"),
        ("cash_received", False, "现金只认"),
    ],
)
def test_gap_hypothesis_keeps_a_verifiable_evidence_boundary(
    hypothesis_id: str,
    complete: bool,
    feedback_fragment: str,
) -> None:
    question = build_cash_timing_question(0)

    result = evaluate_cash_gap_hypothesis(
        question,
        _cash_clock_envelope(
            question,
            "submit_hypothesis",
            hypothesis_id=hypothesis_id,
        ),
        3,
    )

    assert result["phase"] == "hypothesis"
    assert result["complete"] is complete
    assert feedback_fragment in result["feedback"]
    if complete:
        assert result["accepted"] == [hypothesis_id]
        assert result["rejected"] == []
    else:
        assert result["accepted"] == []
        assert result["rejected"] == [hypothesis_id]


def test_investigation_orders_accept_three_matches_and_distraction() -> None:
    question = build_cash_timing_question(0)
    command = _cash_clock_envelope(
        question,
        "submit_orders",
        pockets={
            "income_boundary": "contract_acceptance",
            "receivable_existence": "receivable_aging",
            "subsequent_cash": "bank_statement",
        },
        discarded=["management_promise"],
    )

    result = evaluate_cash_investigation_orders(question, command, 3)

    assert result["phase"] == "orders"
    assert result["complete"] is True
    assert result["rejected"] == []
    assert set(result["accepted"]) == {
        "contract_acceptance",
        "receivable_aging",
        "bank_statement",
        "management_promise",
    }
    assert "管理层承诺" in result["feedback"]


def test_investigation_orders_reject_management_promise_as_evidence() -> None:
    question = build_cash_timing_question(0)
    command = _cash_clock_envelope(
        question,
        "submit_orders",
        pockets={
            "income_boundary": "management_promise",
            "receivable_existence": "receivable_aging",
            "subsequent_cash": "bank_statement",
        },
        discarded=["contract_acceptance"],
    )

    result = evaluate_cash_investigation_orders(question, command, 3)

    assert result["complete"] is False
    assert "management_promise" in result["rejected"]
    assert "管理层承诺" in result["feedback"]


def test_investigation_orders_reject_duplicate_or_unknown_material() -> None:
    question = build_cash_timing_question(0)
    duplicate = _cash_clock_envelope(
        question,
        "submit_orders",
        pockets={
            "income_boundary": "contract_acceptance",
            "receivable_existence": "contract_acceptance",
            "subsequent_cash": "bank_statement",
        },
    )
    unknown = _cash_clock_envelope(
        question,
        "submit_orders",
        pockets={
            "income_boundary": "invented-order",
            "receivable_existence": "receivable_aging",
            "subsequent_cash": "bank_statement",
        },
    )

    with pytest.raises(ValueError, match="不能重复"):
        normalise_cash_clock_command(question, duplicate, 3)
    with pytest.raises(ValueError, match="未知材料编号"):
        normalise_cash_clock_command(question, unknown, 3)


@pytest.mark.parametrize("action", ["discover_keepsake", "open_door"])
def test_scene_action_command_has_no_stage_payload(action: str) -> None:
    question = build_cash_timing_question(0)
    command = _cash_clock_envelope(question, action)

    normalised = normalise_cash_clock_command(question, command, 3)

    assert normalised["action"] == action
    assert normalised["clean_payload"] == {}


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


@pytest.mark.parametrize("attempt_index", range(12))
def test_office_case_continues_the_same_dual_clock_dossier(
    attempt_index: int,
) -> None:
    timing_question = build_cash_timing_question(attempt_index)
    evidence_case = build_cash_evidence_case(attempt_index)
    acceptance_event = next(
        event
        for event in timing_question["event_cards"]
        if event["event_id"] == "service_completed"
    )

    assert evidence_case["reporting_date"] == timing_question["reporting_date"]
    assert evidence_case["contract_amount_wan"] == timing_question["revenue_wan"]
    assert evidence_case["outstanding_wan"] == (
        timing_question["revenue_wan"]
        - timing_question["cash_collected_wan"]
    )
    assert evidence_case["acceptance_date"] == acceptance_event["event_date"]


def test_wrong_evidence_attempt_changes_material_details_and_order() -> None:
    first = build_cash_evidence_case(0)
    second = build_cash_evidence_case(1)

    assert first["case_id"] != second["case_id"]
    assert first["contract_amount_wan"] != second["contract_amount_wan"]
    assert first["outstanding_wan"] != second["outstanding_wan"]
    assert [item["document_id"] for item in first["documents"]] != [
        item["document_id"] for item in second["documents"]
    ]


def test_cross_check_separates_year_end_facts_from_later_evidence() -> None:
    evidence_case = build_cash_evidence_case(0)
    task = build_cash_cross_check_task(evidence_case)

    assert len(task["options"]) == 6
    assert len(task["correct_options"]) == 3
    assert all(option in task["options"] for option in task["correct_options"])
    assert any("银行回单证明" in option for option in task["options"])
    assert "不能倒流成年末事实" in task["prompt"]
    assert "期后银行回单只能证明后来到账" in task["explanation"]


def test_cross_check_changes_with_the_reissued_office_file() -> None:
    first = build_cash_cross_check_task(build_cash_evidence_case(0))
    second = build_cash_cross_check_task(build_cash_evidence_case(1))

    assert first["task_id"] != second["task_id"]
    assert first["options"] != second["options"]


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


def test_evidence_lab_public_task_contains_no_answer_mapping() -> None:
    evidence_case = build_cash_evidence_case(0)
    task = build_cash_evidence_lab_public_task(evidence_case)
    reading = task["reading"]
    classification = task["classification"]
    chain = task["chain"]

    assert isinstance(reading, dict)
    assert isinstance(classification, dict)
    assert isinstance(chain, dict)
    assert len(reading["documents"]) == 6
    assert len(reading["field_options"]) == 14
    assert reading["required_view_count"] == 6
    assert reading["target_mark_count"] == 8
    assert len(classification["classes"]) == 3
    assert len(classification["items"]) == 6
    assert len(chain["claims"]) == 4

    # The browser receives movable IDs and copy, never the Python answer key.
    assert all(
        "class_id" not in item
        for item in classification["items"]
    )
    assert all(
        "document_id" not in claim
        for claim in chain["claims"]
    )
    assert all(
        "is_required" not in option and "correct" not in option
        for option in reading["field_options"]
    )
    assert "required_document_ids" not in task
    assert "answer" not in task


def test_evidence_lab_public_task_changes_copy_but_keeps_stable_ids() -> None:
    first = build_cash_evidence_lab_public_task(build_cash_evidence_case(0))
    second = build_cash_evidence_lab_public_task(build_cash_evidence_case(1))
    first_reading = first["reading"]
    second_reading = second["reading"]
    first_classification = first["classification"]
    second_classification = second["classification"]
    assert isinstance(first_reading, dict)
    assert isinstance(second_reading, dict)
    assert isinstance(first_classification, dict)
    assert isinstance(second_classification, dict)

    assert first["task_id"] != second["task_id"]
    assert first_classification["items"] != second_classification["items"]
    assert {
        item["field_id"] for item in first_reading["field_options"]
    } == {
        item["field_id"] for item in second_reading["field_options"]
    }


def test_evidence_lab_normaliser_accepts_answer_free_reading_command() -> None:
    evidence_case = build_cash_evidence_case(0)
    task = build_cash_evidence_lab_public_task(evidence_case)
    reading = task["reading"]
    assert isinstance(reading, dict)
    document_ids = [
        document["document_id"] for document in reading["documents"]
    ]
    marked_ids = [
        "contract_reference",
        "contract_payment_window",
        "acceptance_date",
    ]
    command = _evidence_lab_envelope(
        evidence_case,
        "submit_reading",
        viewed_document_ids=document_ids,
        marked_field_ids=marked_ids,
    )

    normalised = normalise_cash_evidence_lab_command(
        evidence_case, command, 7
    )

    assert normalised == {
        "schema_version": 1,
        "command_id": "test-lab-submit_reading-1",
        "task_id": task["task_id"],
        "revision": 7,
        "action": "submit_reading",
        "clean_payload": {
            "viewed_document_ids": document_ids,
            "marked_field_ids": marked_ids,
        },
    }
    assert "answer" not in normalised["clean_payload"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"revision": 6}, "revision已经过期"),
        ({"task_id": "cash-evidence-lab:other"}, "task_id"),
        ({"schema_version": True}, "schema_version"),
        ({"answer": "year_end_fact"}, "未知字段"),
    ],
)
def test_evidence_lab_normaliser_rejects_stale_or_tampered_envelope(
    mutation: dict[str, object],
    message: str,
) -> None:
    evidence_case = build_cash_evidence_case(0)
    command = _evidence_lab_envelope(
        evidence_case,
        "submit_reading",
        viewed_document_ids=[],
        marked_field_ids=[],
    )
    command.update(mutation)

    with pytest.raises(ValueError, match=message):
        normalise_cash_evidence_lab_command(evidence_case, command, 7)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "viewed_document_ids": ["invented-document"],
                "marked_field_ids": [],
            },
            "未知编号",
        ),
        (
            {
                "viewed_document_ids": [],
                "marked_field_ids": [
                    "contract_reference",
                    "contract_reference",
                ],
            },
            "重复编号",
        ),
    ],
)
def test_evidence_lab_reading_command_rejects_unknown_or_duplicate_ids(
    payload: dict[str, object],
    message: str,
) -> None:
    evidence_case = build_cash_evidence_case(0)

    with pytest.raises(ValueError, match=message):
        normalise_cash_evidence_lab_command(
            evidence_case,
            _evidence_lab_envelope(
                evidence_case,
                "submit_reading",
                **payload,
            ),
            7,
        )


def test_evidence_lab_classification_command_is_strict() -> None:
    evidence_case = build_cash_evidence_case(0)
    valid = _evidence_lab_envelope(
        evidence_case,
        "submit_classification",
        placements={
            "later_bank_receipt": "subsequent_evidence",
            "chat_expectation": "unverified_claim",
        },
    )
    normalised = normalise_cash_evidence_lab_command(
        evidence_case, valid, 7
    )
    assert normalised["clean_payload"] == {
        "placements": {
            "later_bank_receipt": "subsequent_evidence",
            "chat_expectation": "unverified_claim",
        }
    }

    unknown_item = _evidence_lab_envelope(
        evidence_case,
        "submit_classification",
        placements={"invented-item": "year_end_fact"},
    )
    unknown_class = _evidence_lab_envelope(
        evidence_case,
        "submit_classification",
        placements={"later_bank_receipt": "future_fact"},
    )
    with pytest.raises(ValueError, match="未知分类卡"):
        normalise_cash_evidence_lab_command(
            evidence_case, unknown_item, 7
        )
    with pytest.raises(ValueError, match="区域编号无效"):
        normalise_cash_evidence_lab_command(
            evidence_case, unknown_class, 7
        )


def test_evidence_lab_chain_command_is_strict() -> None:
    evidence_case = build_cash_evidence_case(0)
    valid = _evidence_lab_envelope(
        evidence_case,
        "submit_chain",
        links={"claim_later_cash": "post_period_receipt"},
    )
    normalised = normalise_cash_evidence_lab_command(
        evidence_case, valid, 7
    )
    assert normalised["clean_payload"] == {
        "links": {"claim_later_cash": "post_period_receipt"}
    }

    unknown_claim = _evidence_lab_envelope(
        evidence_case,
        "submit_chain",
        links={"invented-claim": "post_period_receipt"},
    )
    unknown_document = _evidence_lab_envelope(
        evidence_case,
        "submit_chain",
        links={"claim_later_cash": "invented-document"},
    )
    with pytest.raises(ValueError, match="未知主张"):
        normalise_cash_evidence_lab_command(
            evidence_case, unknown_claim, 7
        )
    with pytest.raises(ValueError, match="未知材料编号"):
        normalise_cash_evidence_lab_command(
            evidence_case, unknown_document, 7
        )


def test_reading_locks_correct_marks_and_returns_only_wrong_marks() -> None:
    evidence_case = build_cash_evidence_case(0)
    task = build_cash_evidence_lab_public_task(evidence_case)
    reading = task["reading"]
    assert isinstance(reading, dict)
    document_ids = [
        document["document_id"] for document in reading["documents"]
    ]
    evaluation = evaluate_cash_evidence_reading(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_reading",
            viewed_document_ids=document_ids,
            marked_field_ids=[
                "contract_reference",
                "contract_payment_window",
                "contract_polished_layout",
            ],
        ),
        7,
    )

    assert evaluation["phase"] == "reading"
    assert evaluation["accepted"] == [
        "contract_reference",
        "contract_payment_window",
    ]
    assert evaluation["rejected"] == ["contract_polished_layout"]
    assert evaluation["complete"] is False
    assert evaluation["accepted_count"] == 2
    assert evaluation["target_count"] == 8
    assert "不会清空" in evaluation["feedback"]


def test_reading_requires_all_pages_and_all_eight_key_fields() -> None:
    evidence_case = build_cash_evidence_case(0)
    task = build_cash_evidence_lab_public_task(evidence_case)
    reading = task["reading"]
    assert isinstance(reading, dict)
    document_ids = [
        document["document_id"] for document in reading["documents"]
    ]
    required_marks = [
        "contract_reference",
        "contract_payment_window",
        "acceptance_date",
        "acceptance_external_seal",
        "ar_year_end_balance",
        "ar_due_status",
        "receipt_date",
        "receipt_bank_match",
    ]
    missing_page = evaluate_cash_evidence_reading(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_reading",
            viewed_document_ids=document_ids[:-1],
            marked_field_ids=required_marks,
        ),
        7,
    )
    complete = evaluate_cash_evidence_reading(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_reading",
            viewed_document_ids=document_ids,
            marked_field_ids=required_marks,
        ),
        7,
    )

    assert missing_page["complete"] is False
    assert "没有完整翻阅" in missing_page["feedback"]
    assert complete["complete"] is True
    assert complete["accepted"] == required_marks
    assert complete["rejected"] == []


def test_classification_releases_only_wrong_cards_and_keeps_same_case() -> None:
    evidence_case = build_cash_evidence_case(0)
    original_case_id = evidence_case["case_id"]
    evaluation = evaluate_cash_evidence_classification(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_classification",
            placements={
                "contract_term_at_year_end": "year_end_fact",
                "signed_acceptance_before_cutoff": "year_end_fact",
                "year_end_ar_not_due": "year_end_fact",
                "later_bank_receipt": "year_end_fact",
                "chat_expectation": "unverified_claim",
                "management_forecast": "unverified_claim",
            },
        ),
        7,
    )

    assert evidence_case["case_id"] == original_case_id
    assert evaluation["accepted"] == [
        "contract_term_at_year_end",
        "signed_acceptance_before_cutoff",
        "year_end_ar_not_due",
        "chat_expectation",
        "management_forecast",
    ]
    assert evaluation["rejected"] == ["later_bank_receipt"]
    assert evaluation["complete"] is False
    assert "不会重搜办公室" in evaluation["feedback"]
    assert "不会更换卷宗" in evaluation["feedback"]


def test_classification_accepts_complete_three_region_board() -> None:
    evidence_case = build_cash_evidence_case(0)
    evaluation = evaluate_cash_evidence_classification(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_classification",
            placements={
                "contract_term_at_year_end": "year_end_fact",
                "signed_acceptance_before_cutoff": "year_end_fact",
                "year_end_ar_not_due": "year_end_fact",
                "later_bank_receipt": "subsequent_evidence",
                "chat_expectation": "unverified_claim",
                "management_forecast": "unverified_claim",
            },
        ),
        7,
    )

    assert evaluation["complete"] is True
    assert evaluation["accepted_count"] == 6
    assert evaluation["target_count"] == 6
    assert evaluation["rejected"] == []


def test_chain_releases_only_wrong_links_and_keeps_correct_links() -> None:
    evidence_case = build_cash_evidence_case(0)
    evaluation = evaluate_cash_evidence_chain(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_chain",
            links={
                "claim_payment_boundary": "contract_clause",
                "claim_completion_before_cutoff": "executive_slide",
                "claim_year_end_balance": "ar_subledger",
                "claim_later_cash": "post_period_receipt",
            },
        ),
        7,
    )

    assert evaluation["accepted"] == [
        "claim_payment_boundary",
        "claim_year_end_balance",
        "claim_later_cash",
    ]
    assert evaluation["rejected"] == [
        "claim_completion_before_cutoff"
    ]
    assert evaluation["complete"] is False
    assert "正确工作全部保留" in evaluation["feedback"]


def test_chain_accepts_four_direct_support_links() -> None:
    evidence_case = build_cash_evidence_case(0)
    evaluation = evaluate_cash_evidence_chain(
        evidence_case,
        _evidence_lab_envelope(
            evidence_case,
            "submit_chain",
            links={
                "claim_payment_boundary": "contract_clause",
                "claim_completion_before_cutoff": "signed_acceptance",
                "claim_year_end_balance": "ar_subledger",
                "claim_later_cash": "post_period_receipt",
            },
        ),
        7,
    )

    assert evaluation["complete"] is True
    assert evaluation["accepted_count"] == 4
    assert evaluation["target_count"] == 4
    assert evaluation["rejected"] == []


@pytest.mark.parametrize(
    ("evaluator", "action", "payload", "message"),
    [
        (
            evaluate_cash_evidence_reading,
            "submit_chain",
            {"links": {}},
            "只接受submit_reading",
        ),
        (
            evaluate_cash_evidence_classification,
            "submit_chain",
            {"links": {}},
            "只接受submit_classification",
        ),
        (
            evaluate_cash_evidence_chain,
            "submit_classification",
            {"placements": {}},
            "只接受submit_chain",
        ),
    ],
)
def test_evidence_lab_evaluators_reject_commands_for_another_phase(
    evaluator: object,
    action: str,
    payload: dict[str, object],
    message: str,
) -> None:
    evidence_case = build_cash_evidence_case(0)
    with pytest.raises(ValueError, match=message):
        evaluator(  # type: ignore[operator]
            evidence_case,
            _evidence_lab_envelope(evidence_case, action, **payload),
            7,
        )


def test_cash_defense_has_three_distinct_reasoning_rounds() -> None:
    questions = [build_cash_defense_question(index, 0) for index in range(3)]

    assert [item["round_title"] for item in questions] == [
        "形成初步结论",
        "守住证据边界",
        "决定核验行动",
    ]
    assert all(len(item["evidence_items"]) == 4 for item in questions)
    assert all(len(item["options"]) == 6 for item in questions)
    assert all(item["correct_option"] in item["options"] for item in questions)


def test_cash_defense_rotates_four_real_reasoning_scenarios() -> None:
    questions = [build_cash_defense_question(0, index) for index in range(4)]

    assert {item["scenario_type"] for item in questions} == {
        "explained_timing_gap",
        "late_acceptance",
        "overdue_uncollected",
        "partial_acceptance",
    }
    assert len({item["question_id"] for item in questions}) == 4
    assert len({tuple(item["evidence_items"]) for item in questions}) == 4
    assert len({tuple(item["options"]) for item in questions}) == 4


def test_cash_defense_conclusions_keep_evidence_boundaries() -> None:
    explained = build_cash_defense_question(0, 0)
    late_acceptance = build_cash_defense_question(0, 1)
    overdue = build_cash_defense_question(0, 2)
    partial = build_cash_defense_question(0, 3)

    assert "不能据此代表整家公司" in explained["correct_option"]
    assert "不足以直接认定故意造假" in late_acceptance["correct_option"]
    assert "不自动推翻收入真实性" in overdue["correct_option"]
    assert "不等于整个合同都没有商业实质" in partial["correct_option"]


def _committee_card_by_prefix(
    task: dict[str, object],
    seat_id: str,
    prefix: str,
) -> str:
    """Locate a test card from its public text without fixed option position."""

    seats = task["seats"]
    assert isinstance(seats, list)
    seat = next(item for item in seats if item["seat_id"] == seat_id)
    return next(
        card["card_id"]
        for card in seat["cards"]
        if card["text"].startswith(prefix)
    )


def _correct_first_committee_statement(
    task: dict[str, object],
) -> dict[str, str]:
    """Build the known scenario-zero statement used by evaluator tests."""

    return {
        "conclusion_strength": _committee_card_by_prefix(
            task,
            "conclusion_strength",
            "本项目现有证据支持年末前完成履约",
        ),
        "evidence_boundary": _committee_card_by_prefix(
            task,
            "evidence_boundary",
            "这组材料只能解释这个项目",
        ),
        "next_action": _committee_card_by_prefix(
            task,
            "next_action",
            "抽取其他重要客户样本",
        ),
    }


def test_committee_public_task_is_three_seat_drag_board_without_answers() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    seats = task["seats"]

    assert task["round_number"] == 1
    assert task["challenge_number"] == 1
    assert task["scenario_type"] == "explained_timing_gap"
    assert len(task["evidence_items"]) == 4
    assert isinstance(seats, list)
    assert [seat["seat_id"] for seat in seats] == [
        "conclusion_strength",
        "evidence_boundary",
        "next_action",
    ]
    assert all(len(seat["cards"]) == 6 for seat in seats)
    assert all(
        "correct_option" not in seat and "explanation" not in seat
        for seat in seats
    )
    assert all(
        "correct" not in card and "is_answer" not in card
        for seat in seats
        for card in seat["cards"]
    )
    assert "correct_option" not in task
    assert "explanation" not in task
    assert "正式错误才消耗一次容错" in task["committee_rule"]


def test_committee_round_and_current_challenge_rotate_independently() -> None:
    first = build_cash_defense_committee_public_task(0, 0)
    replacement = build_cash_defense_committee_public_task(0, 1)
    passed_next_round = build_cash_defense_committee_public_task(1, 0)

    assert first["task_id"] != replacement["task_id"]
    assert first["scenario_type"] != replacement["scenario_type"]
    assert replacement["round_number"] == 1
    assert replacement["challenge_number"] == 2
    assert passed_next_round["round_number"] == 2
    assert passed_next_round["challenge_number"] == 1


def test_committee_normaliser_accepts_partial_answer_free_board() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    placements = {
        "conclusion_strength": _committee_card_by_prefix(
            task,
            "conclusion_strength",
            "本项目现有证据支持年末前完成履约",
        )
    }
    command = _defense_committee_envelope(task, placements)

    normalised = normalise_cash_defense_committee_command(
        0, 0, command, 5
    )

    assert normalised == {
        "schema_version": 1,
        "command_id": "test-defense-committee-1",
        "task_id": task["task_id"],
        "revision": 5,
        "action": "submit_committee_statement",
        "clean_payload": {"placements": placements},
    }
    assert "answer" not in normalised["clean_payload"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"schema_version": False}, "schema_version"),
        ({"revision": 4}, "revision已经过期"),
        ({"task_id": "cash-defense-committee:old"}, "task_id"),
        ({"action": "choose_option"}, "action"),
        ({"answer": "hidden"}, "未知字段"),
    ],
)
def test_committee_normaliser_rejects_tampered_envelope(
    overrides: dict[str, object],
    message: str,
) -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    command = _defense_committee_envelope(task, {}, **overrides)

    with pytest.raises(ValueError, match=message):
        normalise_cash_defense_committee_command(0, 0, command, 5)


def test_committee_normaliser_rejects_unknown_seat_or_foreign_card() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    seats = task["seats"]
    assert isinstance(seats, list)
    conclusion_card = seats[0]["cards"][0]["card_id"]
    unknown_seat = _defense_committee_envelope(
        task, {"secret_seat": conclusion_card}
    )
    foreign_card = _defense_committee_envelope(
        task, {"evidence_boundary": conclusion_card}
    )

    with pytest.raises(ValueError, match="未知委员会席位"):
        normalise_cash_defense_committee_command(
            0, 0, unknown_seat, 5
        )
    with pytest.raises(ValueError, match="无效答辩牌"):
        normalise_cash_defense_committee_command(
            0, 0, foreign_card, 5
        )


def test_empty_committee_seats_do_not_consume_formal_life() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    one_correct_seat = {
        "conclusion_strength": _correct_first_committee_statement(task)[
            "conclusion_strength"
        ]
    }
    evaluation = evaluate_cash_defense_committee(
        0,
        0,
        _defense_committee_envelope(task, one_correct_seat),
        5,
    )

    assert evaluation["accepted"] == ["conclusion_strength"]
    assert evaluation["rejected"] == []
    assert evaluation["complete"] is False
    assert evaluation["consume_life"] is False
    assert evaluation["replace_challenge"] is False
    assert "不消耗容错" in evaluation["feedback"]


def test_wrong_committee_card_consumes_one_life_and_only_replaces_challenge() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    correct = _correct_first_committee_statement(task)
    seats = task["seats"]
    assert isinstance(seats, list)
    conclusion_seat = next(
        seat for seat in seats if seat["seat_id"] == "conclusion_strength"
    )
    wrong_conclusion = next(
        card["card_id"]
        for card in conclusion_seat["cards"]
        if card["card_id"] != correct["conclusion_strength"]
    )
    placements = {
        **correct,
        "conclusion_strength": wrong_conclusion,
    }
    evaluation = evaluate_cash_defense_committee(
        0,
        0,
        _defense_committee_envelope(task, placements),
        5,
    )

    assert evaluation["accepted"] == [
        "evidence_boundary",
        "next_action",
    ]
    assert evaluation["rejected"] == ["conclusion_strength"]
    assert evaluation["complete"] is False
    assert evaluation["consume_life"] is True
    assert evaluation["replace_challenge"] is True
    assert "消耗1次容错" in evaluation["feedback"]
    assert "已经通过的委员会轮次继续保留" in evaluation["feedback"]
    assert "不回办公室、不重做证据链" in evaluation["feedback"]


def test_complete_committee_statement_passes_without_life_cost() -> None:
    task = build_cash_defense_committee_public_task(0, 0)
    evaluation = evaluate_cash_defense_committee(
        0,
        0,
        _defense_committee_envelope(
            task, _correct_first_committee_statement(task)
        ),
        5,
    )

    assert evaluation["accepted"] == [
        "conclusion_strength",
        "evidence_boundary",
        "next_action",
    ]
    assert evaluation["rejected"] == []
    assert evaluation["complete"] is True
    assert evaluation["accepted_count"] == 3
    assert evaluation["target_count"] == 3
    assert evaluation["consume_life"] is False
    assert evaluation["replace_challenge"] is False
    assert "三席一致通过" in evaluation["feedback"]


@pytest.mark.parametrize(
    ("round_index", "attempt_index", "message"),
    [(-1, 0, "答辩轮次"), (3, 0, "答辩轮次"), (0, -1, "答辩题序号")],
)
def test_cash_defense_rejects_invalid_indices(
    round_index: int,
    attempt_index: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_cash_defense_question(round_index, attempt_index)


@pytest.mark.parametrize(
    ("round_index", "challenge_index", "message"),
    [
        (-1, 0, "委员会轮次"),
        (3, 0, "委员会轮次"),
        (False, 0, "委员会轮次"),
        (0, -1, "委员会挑战序号"),
        (0, True, "委员会挑战序号"),
    ],
)
def test_committee_task_rejects_invalid_indices(
    round_index: int,
    challenge_index: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_cash_defense_committee_public_task(
            round_index, challenge_index
        )
