from src.cash_game_characters import (
    CASH_GAME_MENTORS,
    MENTOR_BY_KEEPSAKE,
    mentor_for_step,
    normalise_keepsake_ids,
)


def test_nine_scenes_have_distinct_mentors_and_keepsakes() -> None:
    """Every scene must teach through a different person and research habit."""
    assert [mentor.step for mentor in CASH_GAME_MENTORS] == list(range(1, 10))
    assert len({mentor.name for mentor in CASH_GAME_MENTORS}) == 9
    assert len({mentor.role for mentor in CASH_GAME_MENTORS}) == 9
    assert len({mentor.capability for mentor in CASH_GAME_MENTORS}) == 9
    assert len({mentor.keepsake_id for mentor in CASH_GAME_MENTORS}) == 9
    assert mentor_for_step(8).name == "许照夜"
    assert MENTOR_BY_KEEPSAKE["double_sided_prism"].name == "苏棱"


def test_keepsake_normalisation_discards_unknown_and_restores_scene_order() -> None:
    supplied = [
        "reverse_black_piece",
        "../../unsafe",
        "dual_dial_watch",
        "reverse_black_piece",
        7,
    ]

    assert normalise_keepsake_ids(supplied) == [
        "dual_dial_watch",
        "reverse_black_piece",
    ]

