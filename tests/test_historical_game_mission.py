from datetime import date

from src.historical_game_mission import (
    HISTORICAL_GAME_MISSION,
    HISTORICAL_MISSION_EVENT_ID,
    evaluate_historical_mission_date,
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
