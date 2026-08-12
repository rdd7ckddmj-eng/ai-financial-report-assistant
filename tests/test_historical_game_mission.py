from datetime import date

from src.historical_game_mission import (
    HISTORICAL_GAME_MISSION,
    HISTORICAL_MISSION_EVENT_ID,
    build_historical_mission_reasoning_question,
    evaluate_historical_mission_date,
    evaluate_historical_mission_reasoning,
    resolve_historical_mission_clock_boundary,
)


def test_historical_mission_uses_one_bounded_verified_event() -> None:
    mission = HISTORICAL_GAME_MISSION

    assert mission["company_code"] == "600519"
    assert mission["answer_event_id"] == HISTORICAL_MISSION_EVENT_ID
    assert mission["window_start"] == date(2024, 9, 18)
    assert mission["window_end"] == date(2024, 9, 24)
    assert mission["window_start"] <= mission["initial_date"]
    assert mission["initial_date"] <= mission["window_end"]
    assert "2024年9月21日" not in mission["question"]


def test_historical_mission_distinguishes_early_exact_and_late_dates() -> None:
    publication_date = date(2024, 9, 21)

    early = evaluate_historical_mission_date(
        date(2024, 9, 20),
        publication_date,
    )
    exact = evaluate_historical_mission_date(
        date(2024, 9, 21),
        publication_date,
    )
    late = evaluate_historical_mission_date(
        date(2024, 9, 22),
        publication_date,
    )

    assert early["status"] == "too_early"
    assert early["is_correct"] is False
    assert exact["status"] == "correct"
    assert exact["is_correct"] is True
    assert "非交易日" in exact["feedback"]
    assert late["status"] == "too_late"
    assert late["is_correct"] is False


def test_historical_mission_resolves_three_different_clocks() -> None:
    boundary = resolve_historical_mission_clock_boundary(
        [
            date(2024, 9, 19),
            date(2024, 9, 20),
            date(2024, 9, 23),
            date(2024, 9, 24),
        ],
        date(2024, 9, 21),
    )

    assert boundary == {
        "publication_date": date(2024, 9, 21),
        "effective_market_date": date(2024, 9, 20),
        "next_market_date": date(2024, 9, 23),
    }


def test_historical_mission_reasoning_requires_all_three_boundaries() -> None:
    boundary = resolve_historical_mission_clock_boundary(
        [date(2024, 9, 20), date(2024, 9, 23)],
        date(2024, 9, 21),
    )
    first_question = build_historical_mission_reasoning_question(boundary, 0)
    second_question = build_historical_mission_reasoning_question(boundary, 1)

    assert len(first_question["options"]) == 6
    assert first_question["options"] != second_question["options"]
    assert first_question["correct_option"] in first_question["options"]
    assert first_question["options"][0] != first_question["correct_option"]
    assert "2024-09-20" in first_question["correct_option"]
    assert "2024-09-21" in first_question["correct_option"]
    assert "2024-09-23" in first_question["correct_option"]

    wrong_option = next(
        option
        for option in first_question["options"]
        if option != first_question["correct_option"]
    )
    wrong = evaluate_historical_mission_reasoning(
        wrong_option,
        first_question,
    )
    correct = evaluate_historical_mission_reasoning(
        first_question["correct_option"],
        first_question,
    )

    assert wrong["is_correct"] is False
    assert "没有扣除生命" in wrong["feedback"]
    assert correct["is_correct"] is True
    assert "证据时钟" in correct["feedback"]


def test_historical_mission_rejects_incomplete_market_boundaries() -> None:
    try:
        resolve_historical_mission_clock_boundary(
            [date(2024, 9, 19), date(2024, 9, 20)],
            date(2024, 9, 21),
        )
    except ValueError as error:
        assert "公告前后两个交易时点" in str(error)
    else:
        raise AssertionError("缺少公告后交易日时不应生成任务答案。")
