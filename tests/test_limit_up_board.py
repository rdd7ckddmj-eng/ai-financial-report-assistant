from datetime import date

import pandas as pd
import pytest

from src.limit_up_board import (
    build_limit_up_board_review,
    build_limit_up_board_snapshot,
    prepare_limit_up_pool,
    rank_limit_up_rows,
)


def _pool_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "代码": [4, "600519", "300750"],
            "名称": ["国华网安", "贵州茅台", "宁德时代"],
            "涨跌幅": [10.0, 10.01, 20.0],
            "最新价": [17.93, 1321.0, 310.0],
            "成交额": [800_000_000, 4_500_000_000, 6_000_000_000],
            "流通市值": [5_000_000_000, 1_600_000_000_000, 1_200_000_000_000],
            "总市值": [6_000_000_000, 1_700_000_000_000, 1_300_000_000_000],
            "换手率": [12.0, 1.5, 4.5],
            "封板资金": [120_000_000, 500_000_000, 300_000_000],
            "首次封板时间": [92500, "10:05:01", 94530],
            "最后封板时间": [141354, 100501, 145000],
            "炸板次数": [1, 0, 0],
            "涨停统计": ["10/6", "2/2", "1/1"],
            "连板数": [2, 2, 1],
            "所属行业": ["软件开发", "酿酒行业", "软件开发"],
        }
    )


def test_prepare_limit_up_pool_preserves_units_and_times() -> None:
    rows = prepare_limit_up_pool(_pool_frame())

    assert rows[0]["code"] == "000004"
    assert rows[0]["daily_change"] == pytest.approx(0.10)
    assert rows[0]["turnover"] == pytest.approx(0.12)
    assert rows[0]["first_limit_time"] == "09:25:00"
    assert rows[0]["last_limit_time"] == "14:13:54"
    assert rows[0]["consecutive_boards"] == 2


def test_limit_up_ranking_prefers_streak_then_board_stability() -> None:
    rows = prepare_limit_up_pool(_pool_frame())
    ranked = rank_limit_up_rows(rows)

    assert [row["code"] for row in ranked] == [
        "600519",
        "000004",
        "300750",
    ]


def test_limit_up_snapshot_builds_transparent_summary() -> None:
    snapshot = build_limit_up_board_snapshot(
        _pool_frame(),
        date(2026, 7, 30),
        max_rows=2,
    )

    assert snapshot["trade_date"] == "2026-07-30"
    assert snapshot["total_count"] == 3
    assert snapshot["first_board_count"] == 1
    assert snapshot["consecutive_board_count"] == 2
    assert snapshot["max_consecutive_boards"] == 2
    assert snapshot["median_turnover"] == pytest.approx(0.045)
    assert snapshot["leading_industry"] == "软件开发"
    assert snapshot["leading_industry_count"] == 2
    assert snapshot["review"]["early_seal_count"] == 2
    assert len(snapshot["rows"]) == 2


def test_limit_up_review_builds_ladder_industry_and_timing_evidence() -> None:
    rows = prepare_limit_up_pool(_pool_frame())

    review = build_limit_up_board_review(rows)

    assert review["ladder"] == [
        {"boards": 2, "company_count": 2, "share": pytest.approx(2 / 3)},
        {"boards": 1, "company_count": 1, "share": pytest.approx(1 / 3)},
    ]
    assert review["industries"][0]["industry"] == "软件开发"
    assert review["industries"][0]["company_count"] == 2
    assert review["industries"][0]["consecutive_count"] == 1
    assert review["industries"][0]["total_amount"] == pytest.approx(
        6_800_000_000
    )
    assert review["industries"][0]["median_turnover"] == pytest.approx(
        0.0825
    )
    assert review["early_seal_count"] == 2
    assert review["early_seal_ratio"] == pytest.approx(2 / 3)
    assert review["resealed_count"] == 1
    assert review["resealed_ratio"] == pytest.approx(1 / 3)
    assert review["leading_industry_share"] == pytest.approx(2 / 3)
    assert len(review["observations"]) == 4


def test_limit_up_review_preserves_missing_structure_as_unavailable() -> None:
    rows = prepare_limit_up_pool(
        pd.DataFrame({"代码": ["600519"], "名称": ["贵州茅台"]})
    )

    review = build_limit_up_board_review(rows)

    assert review["ladder"] == []
    assert review["industries"] == []
    assert review["early_seal_ratio"] is None
    assert review["resealed_ratio"] is None
    assert review["leading_industry_share"] is None
    assert "数据不足" in review["observations"][1]


def test_limit_up_pool_drops_invalid_and_duplicate_codes() -> None:
    frame = pd.DataFrame(
        {
            "代码": ["bad", "600519", "600519"],
            "名称": ["无效", "贵州茅台", "重复公司"],
        }
    )

    rows = prepare_limit_up_pool(frame)

    assert len(rows) == 1
    assert rows[0]["code"] == "600519"


def test_limit_up_pool_requires_identity_fields() -> None:
    with pytest.raises(ValueError, match="股票代码或公司名称"):
        prepare_limit_up_pool(pd.DataFrame({"换手率": [2.0]}))
