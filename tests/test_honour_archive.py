from datetime import datetime, timezone

import pytest

from src.honour_archive import (
    build_honour_archive_html,
    build_honour_poster_payload,
    build_honour_record,
    format_completion_rank,
    format_honour_number,
    normalise_honour_record,
)


def test_rank_and_honour_number_use_different_number_formats() -> None:
    assert format_completion_rank(1) == "1"
    assert format_completion_rank(10) == "10"
    assert format_completion_rank(10_000) == "10000"
    assert format_honour_number(1) == "000001"
    assert format_honour_number(10) == "000010"

    with pytest.raises(ValueError, match="大于零"):
        format_completion_rank(0)
    with pytest.raises(ValueError, match="大于零"):
        format_completion_rank(1.5)  # type: ignore[arg-type]


def test_honour_record_and_html_escape_player_name() -> None:
    record = build_honour_record(
        '<script>alert("x")</script>北辰',
        completed_at=datetime(2026, 8, 12, 8, 30, tzinfo=timezone.utc),
    )
    html = build_honour_archive_html(record)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "测试赛季 · 本设备通关位次" in html
    assert "000001" in html
    assert "不代表职业资格" in html


def test_browser_honour_record_is_strictly_validated() -> None:
    record = build_honour_record(
        "北辰",
        completed_at=datetime(2026, 8, 12, 8, 30, tzinfo=timezone.utc),
    )

    assert normalise_honour_record(record) == record
    assert normalise_honour_record({**record, "completion_rank": 0}) is None
    assert normalise_honour_record({**record, "honour_number": "1"}) is None
    assert normalise_honour_record({**record, "mission_id": "fake"}) is None


def test_vertical_poster_payload_is_douyin_ready_and_bounded() -> None:
    record = build_honour_record(
        "方正",
        completed_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    payload = build_honour_poster_payload(record)

    assert (payload["width"], payload["height"]) == (1080, 1920)
    assert payload["file_name"].endswith(".png")
    assert payload["rank_label"] == "1"
    assert len(payload["story_lines"]) == 7
    assert "拒绝用明天解释今天" in payload["headline"]
    assert "不代表职业资格" in payload["disclaimer"]
