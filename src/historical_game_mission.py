"""One deliberate game mission that reuses Historical Lens.

The product intentionally keeps this interaction rare.  Its purpose is to
teach the difference between an evidence publication date and a market trading
date, not to turn every research page into a repeated quiz.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Literal, TypedDict


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


class HistoricalMissionClockBoundary(TypedDict):
    """The three dates a player must keep separate in the migration task."""

    publication_date: date
    effective_market_date: date
    next_market_date: date


class HistoricalMissionReasoningQuestion(TypedDict):
    """Deterministic second-step question after the date is discovered."""

    question_id: str
    prompt: str
    options: list[str]
    correct_option: str
    explanation: str


class HistoricalMissionReasoningEvaluation(TypedDict):
    """Result of the three-boundary reasoning check."""

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


def _as_date(value: date | datetime | str) -> date:
    """Normalise market dates without depending on the page or pandas."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as error:
        raise ValueError("行情日期不是有效的 ISO 日期。") from error


def resolve_historical_mission_clock_boundary(
    market_dates: Iterable[date | datetime | str],
    publication_date: date,
) -> HistoricalMissionClockBoundary:
    """Resolve evidence time, effective K-line time and next trading time.

    Official evidence can be published on a non-trading day.  The market
    snapshot then remains on the latest prior trading date, while any later
    market response must be studied from a subsequent trading date.
    """
    normalised_dates = sorted({_as_date(value) for value in market_dates})
    effective_candidates = [
        market_date
        for market_date in normalised_dates
        if market_date <= publication_date
    ]
    next_candidates = [
        market_date
        for market_date in normalised_dates
        if market_date > publication_date
    ]
    if not effective_candidates or not next_candidates:
        raise ValueError("任务行情不足，无法同时确认公告前后两个交易时点。")
    return {
        "publication_date": publication_date,
        "effective_market_date": effective_candidates[-1],
        "next_market_date": next_candidates[0],
    }


def build_historical_mission_reasoning_question(
    boundary: HistoricalMissionClockBoundary,
    attempt_index: int = 0,
) -> HistoricalMissionReasoningQuestion:
    """Build one rigorous six-option check without exposing a price signal."""
    if attempt_index < 0:
        raise ValueError("任务尝试序号不能为负数。")

    publication_text = boundary["publication_date"].isoformat()
    effective_text = boundary["effective_market_date"].isoformat()
    next_text = boundary["next_market_date"].isoformat()
    if boundary["effective_market_date"] > boundary["publication_date"]:
        raise ValueError("实际采用交易日不能晚于公告公开日。")
    if boundary["next_market_date"] <= boundary["publication_date"]:
        raise ValueError("下一交易日必须晚于公告公开日。")

    correct_option = (
        f"复盘存在前视偏差：方案到 {publication_text} 才成为公开证据；"
        f"该日证据可以进入快照，但行情仍采用 {effective_text}；若另行观察"
        f"公告后的市场表现，最早从 {next_text} 开始，而且涨跌本身不能证明因果。"
    )
    base_options = [
        (
            f"复盘没有前视偏差：因为 {publication_text} 的行情仍采用"
            f" {effective_text}，所以 {effective_text} 的研究者也可以使用这份公告。"
        ),
        (
            f"复盘存在前视偏差，但方案要等到 {next_text} 开市后才算公开；"
            f"因此 {publication_text} 的任何研究快照都不能纳入它。"
        ),
        (
            f"只要方案在 {publication_text} 公开，当天就应当生成一根新的K线；"
            f"因此实际采用交易日也应改为 {publication_text}。"
        ),
        (
            f"方案讨论的是此前已经酝酿的事项，所以可以追溯写入"
            f" {effective_text} 的复盘；公开日期只影响链接，不影响当时已知。"
        ),
        correct_option,
        (
            f"只要 {next_text} 的股价出现明显变化，就可以确认这份"
            f" {publication_text} 公告是唯一原因，时间边界无需再核验。"
        ),
    ]
    offset = attempt_index % len(base_options)
    options = base_options[offset:] + base_options[:offset]
    explanation = (
        f"证据时钟停在 {publication_text}，行情时钟在非交易日仍停在"
        f" {effective_text}，下一次可观察交易发生在 {next_text}。"
        "三者用途不同：公开日决定信息能否进入研究，交易日决定K线位置，"
        "后续涨跌只能作为结果观察，不能自动证明公告造成了涨跌。"
    )
    return {
        "question_id": (
            f"{HISTORICAL_MISSION_ID}-reasoning-{attempt_index + 1}"
        ),
        "prompt": (
            "你已经找到目标证据的首次公开日。以下哪一项同时正确处理了"
            "前视偏差、非交易日行情和后续市场观察？"
        ),
        "options": options,
        "correct_option": correct_option,
        "explanation": explanation,
    }


def evaluate_historical_mission_reasoning(
    selected_option: str,
    question: HistoricalMissionReasoningQuestion,
) -> HistoricalMissionReasoningEvaluation:
    """Evaluate the reasoning step without using an LLM or price forecast."""
    if selected_option == question["correct_option"]:
        return {
            "is_correct": True,
            "feedback": question["explanation"],
        }
    return {
        "is_correct": False,
        "feedback": (
            "这项判断还没有同时守住三处边界：证据何时公开、页面采用"
            "哪一交易日、何时才能观察后续市场。没有扣除生命；选项顺序"
            "已经更换，请重新核对上方日期与时间隔离说明。"
        ),
    }
