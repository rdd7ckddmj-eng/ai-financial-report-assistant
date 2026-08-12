"""One deliberate game mission that reuses Historical Lens.

The product intentionally keeps this interaction rare.  Its purpose is to
teach the difference between an evidence publication date and a market trading
date, not to turn every research page into a repeated quiz.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict


HISTORICAL_MISSION_ID = "moutai-repurchase-publication-boundary"
HISTORICAL_MISSION_EVENT_ID = "moutai-2024-repurchase-plan"


class HistoricalGameMission(TypedDict):
    """Configuration for the single cross-module Historical Lens mission."""

    mission_id: str
    company_code: str
    company_name: str
    title: str
    case_file: str
    question: str
    window_start: date
    window_end: date
    initial_date: date
    answer_event_id: str


class HistoricalMissionEvaluation(TypedDict):
    """A bounded answer state that does not expose the target date early."""

    status: Literal["correct", "too_early", "too_late"]
    is_correct: bool
    feedback: str


HISTORICAL_GAME_MISSION: HistoricalGameMission = {
    "mission_id": HISTORICAL_MISSION_ID,
    "company_code": "600519",
    "company_name": "贵州茅台",
    "title": "开放调查 01｜两只时钟",
    "case_file": "贵州茅台回购方案公开时点争议",
    "question": (
        "一份内部复盘把回购方案写进了2024年9月20日的“当时已知”材料。"
        "请找出这份官方方案第一次可以进入历史研究快照的日期，并判断这份"
        "复盘是否使用了未来信息。"
    ),
    "window_start": date(2024, 9, 18),
    "window_end": date(2024, 9, 24),
    "initial_date": date(2024, 9, 18),
    "answer_event_id": HISTORICAL_MISSION_EVENT_ID,
}


def evaluate_historical_mission_date(
    selected_date: date,
    publication_date: date,
) -> HistoricalMissionEvaluation:
    """Evaluate the chosen boundary without turning the task into guessing."""
    if selected_date == publication_date:
        return {
            "status": "correct",
            "is_correct": True,
            "feedback": (
                "时点正确。你区分了公告的公开日期与行情的有效交易日："
                "证据可以在非交易日公开，但当天行情仍会停留在此前最近一个"
                "交易日。"
            ),
        }
    if selected_date < publication_date:
        return {
            "status": "too_early",
            "is_correct": False,
            "feedback": (
                "这个日期仍然太早。检查“当时已经公开的官方证据”，再把"
                "时间轴向后移动；不要用报告描述的事项代替实际公开日期。"
            ),
        }
    return {
        "status": "too_late",
        "is_correct": False,
        "feedback": (
            "这个日期已经能够看到目标证据，但还不是它第一次进入快照的"
            "日期。把时间轴向前移动，并比较相邻两天的证据边界。"
        ),
    }
