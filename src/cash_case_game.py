"""Deterministic teaching and evidence tasks for the first finance case."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import TypedDict


class CashTimingQuestion(TypedDict):
    """One changing profit-versus-cash evidence diagnosis."""

    question_id: str
    attempt_number: int
    revenue_wan: int
    expense_wan: int
    cash_collected_wan: int
    profit_effect_wan: int
    cash_effect_wan: int
    reporting_date: date
    event_cards: list["CashTimingEvent"]
    correct_profit_event_ids: list[str]
    correct_cash_event_ids: list[str]
    reasoning_explanation: str
    prompt: str
    inference_options: list[str]
    correct_inference_option: str
    inference_feedback: dict[str, str]
    explanation: str


class CashTimingEvent(TypedDict):
    """One dated business fact used to distinguish two measurement clocks."""

    event_id: str
    event_date: date
    date_label: str
    title: str
    detail: str
    affects_profit: bool
    affects_cash: bool


class CashClockAssignmentEvaluation(TypedDict):
    """Result of routing business facts to the two measurement clocks."""

    is_correct: bool
    profit_is_correct: bool
    cash_is_correct: bool
    feedback: str


class CashClockCommand(TypedDict):
    """One validated browser command without any server-side answer key."""

    schema_version: int
    command_id: str
    question_id: str
    revision: int
    action: str
    clean_payload: dict[str, object]


class CashClockCommandEvaluation(TypedDict):
    """Authoritative result returned after one visual-game submission."""

    phase: str
    action: str
    accepted: list[str]
    rejected: list[str]
    feedback: str
    complete: bool
    clean_payload: dict[str, object]


class EvidenceDocument(TypedDict):
    """One discoverable office document, including plausible distractions."""

    document_id: str
    location: str
    title: str
    document_type: str
    body: str
    footer: str


class CashEvidenceCase(TypedDict):
    """One internally consistent changing office-investigation file."""

    case_id: str
    attempt_number: int
    reporting_date: date
    acceptance_date: date
    due_date: date
    receipt_date: date
    payment_days: int
    customer_name: str
    contract_number: str
    contract_amount_wan: int
    outstanding_wan: int
    documents: list[EvidenceDocument]
    required_document_ids: list[str]
    question: str
    explanation: str


class CashCrossCheckTask(TypedDict):
    """One report-date fact check built from the current evidence file."""

    task_id: str
    prompt: str
    options: list[str]
    correct_options: list[str]
    explanation: str


class EvidenceSelectionEvaluation(TypedDict):
    """Result of one document-chain submission."""

    is_correct: bool
    missing_count: int
    distraction_count: int
    feedback: str


class CashEvidenceLabCommand(TypedDict):
    """One validated Stage 5--7 command with no embedded answer key."""

    schema_version: int
    command_id: str
    task_id: str
    revision: int
    action: str
    clean_payload: dict[str, object]


class CashEvidenceLabEvaluation(TypedDict):
    """Stable result shape used by the three evidence-lab scenes."""

    phase: str
    action: str
    accepted: list[str]
    rejected: list[str]
    feedback: str
    complete: bool
    accepted_count: int
    target_count: int
    clean_payload: dict[str, object]


class CashDefenseQuestion(TypedDict):
    """One changing formal-defence question with a defensible boundary."""

    question_id: str
    round_index: int
    round_number: int
    round_title: str
    attempt_number: int
    scenario_type: str
    company_name: str
    evidence_items: list[str]
    prompt: str
    options: list[str]
    correct_option: str
    explanation: str


class CashDefenseCommitteeCommand(TypedDict):
    """One validated three-seat formal-defence submission."""

    schema_version: int
    command_id: str
    task_id: str
    revision: int
    action: str
    clean_payload: dict[str, object]


class CashDefenseCommitteeEvaluation(TypedDict):
    """Authoritative committee result, including formal life cost."""

    phase: str
    action: str
    accepted: list[str]
    rejected: list[str]
    feedback: str
    complete: bool
    accepted_count: int
    target_count: int
    consume_life: bool
    replace_challenge: bool
    clean_payload: dict[str, object]


def _signed_wan(value: int) -> str:
    """Format one signed amount without hiding zero behind a plus sign."""
    if value > 0:
        return f"+{value}万元"
    if value < 0:
        return f"-{abs(value)}万元"
    return "0万元"


def build_cash_timing_question(attempt_index: int) -> CashTimingQuestion:
    """Build one internally consistent profit-versus-cash dossier.

    Amounts change only when a player explicitly starts a new dossier.  A
    wrong answer keeps the same facts and preserves completed work, so the
    challenge tests accounting reasoning instead of tolerance for repetition.
    """
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError("练习题序号必须是非负整数。")

    revenue_wan = 120 + attempt_index * 7
    expense_wan = 70 + attempt_index * 3
    cash_collected_wan = 20 + (attempt_index * 13) % 61
    profit_effect_wan = revenue_wan - expense_wan
    cash_effect_wan = cash_collected_wan - expense_wan

    outstanding_wan = revenue_wan - cash_collected_wan
    correct_inference_option = (
        f"{outstanding_wan}万元可能形成应收款假设；仍需合同、验收、"
        "应收明细和期后回款证据核实，不能仅凭差额判定造假。"
    )
    premature_receivable_option = (
        f"{outstanding_wan}万元可直接确认为应收款；只要年末明细与合同"
        "金额一致，就无需再核对客户验收或期后回款。"
    )
    premature_default_option = (
        f"{outstanding_wan}万元说明回款质量已经恶化；即使尚未检查合同"
        "到期日，也应把‘客户可能违约’写成确定结论。"
    )
    promise_as_cash_option = (
        f"客户已承诺以后支付{outstanding_wan}万元，因此该差额可视为"
        "正常账期；付款计划足以替代本月银行流水。"
    )
    cash_basis_option = (
        f"利润为{profit_effect_wan}万元但现金为{cash_effect_wan}万元，"
        "说明收入缺少现金支撑；最稳妥做法是等全部收款后再确认收入。"
    )
    no_hypothesis_option = (
        "材料尚不完整，因此只能记录‘利润与现金不同步’；在四类证据"
        "收齐前，不应形成任何应收款核验假设。"
    )
    inference_candidates = [
        correct_inference_option,
        premature_receivable_option,
        premature_default_option,
        promise_as_cash_option,
        cash_basis_option,
        no_hypothesis_option,
    ]
    inference_rotation = (attempt_index * 2 + 1) % len(inference_candidates)
    inference_options = (
        inference_candidates[inference_rotation:]
        + inference_candidates[:inference_rotation]
    )
    inference_feedback = {
        correct_inference_option: "边界判断成立。",
        premature_receivable_option: (
            "合同和内部明细还不够。验收回答收入是否已经赚到，期后银行"
            "回单回答这笔应收后来是否真实收回，二者不能省略。"
        ),
        premature_default_option: (
            "风险信号不能跳过合同期限直接升级为违约结论。先核对到期日与"
            "账龄，再决定这笔应收是正常账期还是异常拖欠。"
        ),
        promise_as_cash_option: (
            "付款计划可以解释管理层预期，却不能替代本月银行流水。正常"
            "账期也需要合同条款、应收明细与后来到账相互核验。"
        ),
        cash_basis_option: (
            "这把现金收付条件误加给了收入确认。若服务已经完成并验收，"
            "收入可以先进入利润；未收部分则转化为待核实的应收款。"
        ),
        no_hypothesis_option: (
            "可检验假设不等于最终结论。研究应先提出‘可能形成应收款’，"
            "再明确列出会支持或推翻它的证据，而不是停止思考。"
        ),
    }
    # Use real date arithmetic and keep every generated fact before the
    # 31 December reporting cut-off.  The earlier string arithmetic could
    # produce impossible labels such as "12月32日" after several retries.
    day_offset = attempt_index % 4
    reporting_date = date(2025, 12, 31)
    contract_date = date(2025, 12, 11) + timedelta(days=day_offset)
    acceptance_date = date(2025, 12, 18) + timedelta(days=day_offset)
    expense_incurred_date = date(2025, 12, 21) + timedelta(days=day_offset)
    expense_date = date(2025, 12, 23) + timedelta(days=day_offset)
    collection_date = date(2025, 12, 27) + timedelta(days=day_offset)
    future_payment_date = date(2026, 1, 12) + timedelta(days=day_offset)

    def event_date_label(value: date) -> str:
        prefix = "次年" if value.year > reporting_date.year else ""
        return f"{prefix}{value.month}月{value.day}日"

    event_cards_in_order: list[CashTimingEvent] = [
        {
            "event_id": "contract_signed",
            "event_date": contract_date,
            "date_label": event_date_label(contract_date),
            "title": "双方签署服务合同",
            "detail": "合同已经生效，但此时服务尚未完成。",
            "affects_profit": False,
            "affects_cash": False,
        },
        {
            "event_id": "service_completed",
            "event_date": acceptance_date,
            "date_label": event_date_label(acceptance_date),
            "title": "服务完成并通过验收",
            "detail": f"客户确认本期已履约，可确认收入{revenue_wan}万元。",
            "affects_profit": True,
            "affects_cash": False,
        },
        {
            "event_id": "expense_incurred",
            "event_date": expense_incurred_date,
            "date_label": event_date_label(expense_incurred_date),
            "title": "相关人工与服务器成本发生",
            "detail": f"为完成本期服务，已经发生相关成本{expense_wan}万元。",
            "affects_profit": True,
            "affects_cash": False,
        },
        {
            "event_id": "expense_paid",
            "event_date": expense_date,
            "date_label": event_date_label(expense_date),
            "title": "相关费用完成支付",
            "detail": f"银行账户实际支付人工与服务器费用{expense_wan}万元。",
            "affects_profit": False,
            "affects_cash": True,
        },
        {
            "event_id": "cash_collected",
            "event_date": collection_date,
            "date_label": event_date_label(collection_date),
            "title": "客户回款",
            "detail": f"本月实际收到客户款项{cash_collected_wan}万元。",
            "affects_profit": False,
            "affects_cash": True,
        },
        {
            "event_id": "future_payment_plan",
            "event_date": future_payment_date,
            "date_label": event_date_label(future_payment_date),
            "title": "客户承诺支付剩余款项",
            "detail": "这是报告期后的付款计划，不是本月到账记录。",
            "affects_profit": False,
            "affects_cash": False,
        },
    ]
    display_orders = (
        (3, 0, 5, 1, 4, 2),
        (5, 1, 4, 0, 2, 3),
        (1, 5, 2, 4, 3, 0),
        (4, 2, 0, 5, 1, 3),
    )
    display_order = display_orders[attempt_index % len(display_orders)]
    event_cards = [event_cards_in_order[index] for index in display_order]
    correct_profit_event_ids = [
        event["event_id"]
        for event in event_cards_in_order
        if event["affects_profit"]
    ]
    correct_cash_event_ids = [
        event["event_id"]
        for event in event_cards_in_order
        if event["affects_cash"]
    ]
    reasoning_explanation = (
        "这道题不是比谁更会按日期排队。收入确认要先检查履约是否完成、"
        "客户是否验收，相关成本在发生时进入利润；现金只认银行账户里"
        "真实发生的收付。合同、应收款和未来付款计划都可能是证据，但"
        "它们本身不能冒充到账现金。"
    )
    prompt = (
        f"岚桥智能已经完成并通过客户验收一项服务，按合同可确认收入"
        f"{revenue_wan}万元。本月相关人工和服务器费用{expense_wan}万元"
        f"已经全部支付；截至月末，客户本月实际支付{cash_collected_wan}万元，"
        "其余款项以后再付。只考虑这项业务，它对本月利润和现金分别产生"
        "什么影响？"
    )
    explanation = (
        f"服务已经完成并验收，所以先确认收入{revenue_wan}万元；减去"
        f"相关费用{expense_wan}万元，利润影响为"
        f"{_signed_wan(profit_effect_wan)}。现金只计算本月真正收到和付出"
        f"的钱：收到{cash_collected_wan}万元，付出{expense_wan}万元，"
        f"现金影响为{_signed_wan(cash_effect_wan)}。尚未收到的"
        f"{outstanding_wan}万元形成应收款线索，不等于本月已经收到现金。"
    )
    return {
        "question_id": (
            f"cash-timing-{attempt_index + 1}-"
            f"{revenue_wan}-{cash_collected_wan}"
        ),
        "attempt_number": attempt_index + 1,
        "revenue_wan": revenue_wan,
        "expense_wan": expense_wan,
        "cash_collected_wan": cash_collected_wan,
        "profit_effect_wan": profit_effect_wan,
        "cash_effect_wan": cash_effect_wan,
        "reporting_date": reporting_date,
        "event_cards": event_cards,
        "correct_profit_event_ids": correct_profit_event_ids,
        "correct_cash_event_ids": correct_cash_event_ids,
        "reasoning_explanation": reasoning_explanation,
        "prompt": prompt,
        "inference_options": inference_options,
        "correct_inference_option": correct_inference_option,
        "inference_feedback": inference_feedback,
        "explanation": explanation,
    }


def evaluate_cash_clock_assignment(
    question: CashTimingQuestion,
    profit_event_ids: object,
    cash_event_ids: object,
) -> CashClockAssignmentEvaluation:
    """Evaluate fact routing without rewarding date-order pattern matching."""

    valid_ids = {event["event_id"] for event in question["event_cards"]}

    def clean_ids(value: object) -> set[str]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            return set()
        return {
            item
            for item in value
            if isinstance(item, str) and item in valid_ids
        }

    selected_profit = clean_ids(profit_event_ids)
    selected_cash = clean_ids(cash_event_ids)
    expected_profit = set(question["correct_profit_event_ids"])
    expected_cash = set(question["correct_cash_event_ids"])
    profit_is_correct = selected_profit == expected_profit
    cash_is_correct = selected_cash == expected_cash
    is_correct = profit_is_correct and cash_is_correct

    if is_correct:
        feedback = (
            "归因成立：验收与已经发生的相关成本进入利润时钟；真实回款"
            "与费用支付进入现金时钟。成本发生和付款是两件不同的事。"
        )
    elif not profit_is_correct and not cash_is_correct:
        feedback = (
            "两只时钟都混入了不属于自己的事实。先问“本期是否完成履约”，"
            "再问“银行账户是否真实收付”；日期先后本身不是答案。"
        )
    elif not profit_is_correct:
        feedback = (
            "现金路径已经找对，但利润时钟仍需复核。合同生效和未来付款"
            "计划不等于本期已经完成履约。"
        )
    else:
        feedback = (
            "利润确认边界已经找对，但现金时钟仍有混淆。应收款和付款承诺"
            "都不是到账；现金只认本期真实发生的收付。"
        )

    return {
        "is_correct": is_correct,
        "profit_is_correct": profit_is_correct,
        "cash_is_correct": cash_is_correct,
        "feedback": feedback,
    }


CASH_CLOCK_COMMAND_SCHEMA_VERSION = 1

_CASH_CLOCK_ACTIONS = {
    "submit_routes",
    "submit_hypothesis",
    "submit_orders",
    "discover_keepsake",
    "open_door",
}
_CASH_CLOCK_BINS = {"profit", "cash", "both", "neither"}
_CASH_CLOCK_HYPOTHESES = {
    "receivable_pending",
    "proven_fraud",
    "customer_default",
    "cash_received",
}
_CASH_CLOCK_POCKET_IDS = {
    "income_boundary",
    "receivable_existence",
    "subsequent_cash",
}
_CASH_CLOCK_ORDER_IDS = {
    "contract_acceptance",
    "receivable_aging",
    "bank_statement",
    "management_promise",
}
_CASH_CLOCK_CORRECT_ORDERS = {
    "income_boundary": "contract_acceptance",
    "receivable_existence": "receivable_aging",
    "subsequent_cash": "bank_statement",
}
_COMMAND_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _require_exact_keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
    subject: str,
) -> None:
    """Reject missing and unexpected fields instead of guessing intent."""

    optional = optional or set()
    actual = set(value)
    missing = required - actual
    unexpected = actual - required - optional
    if missing:
        raise ValueError(
            f"{subject}缺少字段：{', '.join(sorted(missing))}。"
        )
    if unexpected:
        raise ValueError(
            f"{subject}包含未知字段：{', '.join(sorted(unexpected))}。"
        )


def _cash_clock_event_ids(question: CashTimingQuestion) -> list[str]:
    """Read and validate the six public event IDs in display order."""

    event_ids = [event["event_id"] for event in question["event_cards"]]
    if len(event_ids) != 6:
        raise ValueError("当前双时钟题必须恰好包含6张事实卡。")
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("当前双时钟题的事实卡编号存在重复。")
    return event_ids


def normalise_cash_clock_command(
    question: CashTimingQuestion,
    command: object,
    expected_revision: int,
) -> CashClockCommand:
    """Strictly validate one command sent by the visual game.

    The browser sends only the player's placements.  Correct buckets,
    hypotheses and evidence matches are deliberately derived later in Python,
    so inspecting or modifying browser state cannot reveal or change the
    answer key.
    """

    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        raise ValueError("服务端题目版本必须是非负整数。")
    if not isinstance(command, Mapping):
        raise ValueError("游戏命令必须是对象。")

    common_fields = {
        "schema_version",
        "command_id",
        "question_id",
        "revision",
        "action",
    }
    _require_exact_keys(
        command,
        required=common_fields,
        optional={"bins", "hypothesis_id", "pockets", "discarded"},
        subject="游戏命令",
    )

    schema_version = command["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CASH_CLOCK_COMMAND_SCHEMA_VERSION
    ):
        raise ValueError("游戏命令schema_version不受支持。")

    command_id = command["command_id"]
    if (
        not isinstance(command_id, str)
        or not _COMMAND_ID_PATTERN.fullmatch(command_id)
    ):
        raise ValueError("游戏命令command_id格式无效。")

    question_id = command["question_id"]
    if not isinstance(question_id, str) or question_id != question["question_id"]:
        raise ValueError("游戏命令question_id与当前题目不一致。")

    revision = command["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("游戏命令revision必须是整数。")
    if revision != expected_revision:
        raise ValueError("游戏命令revision已经过期，请按当前画面重新提交。")

    action = command["action"]
    if not isinstance(action, str) or action not in _CASH_CLOCK_ACTIONS:
        raise ValueError("游戏命令action不受支持。")

    event_ids = _cash_clock_event_ids(question)
    clean_payload: dict[str, object]
    if action == "submit_routes":
        _require_exact_keys(
            command,
            required=common_fields | {"bins"},
            subject="事实卡归位命令",
        )
        raw_bins = command["bins"]
        if not isinstance(raw_bins, Mapping):
            raise ValueError("bins必须是事实卡编号到时钟区域的对象。")
        submitted_ids = set(raw_bins)
        valid_ids = set(event_ids)
        unknown_ids = submitted_ids - valid_ids
        missing_ids = valid_ids - submitted_ids
        if unknown_ids:
            raise ValueError(
                "bins包含未知事实卡："
                f"{', '.join(sorted(str(item) for item in unknown_ids))}。"
            )
        if missing_ids:
            raise ValueError(
                "bins缺少事实卡："
                f"{', '.join(sorted(missing_ids))}。"
            )
        if len(raw_bins) != len(event_ids):
            raise ValueError("bins中的事实卡编号存在重复。")
        bins: dict[str, str] = {}
        for event_id in event_ids:
            bucket = raw_bins[event_id]
            if not isinstance(bucket, str) or bucket not in _CASH_CLOCK_BINS:
                raise ValueError(f"事实卡{event_id}的归位区域无效。")
            bins[event_id] = bucket
        clean_payload = {"bins": bins}
    elif action == "submit_hypothesis":
        _require_exact_keys(
            command,
            required=common_fields | {"hypothesis_id"},
            subject="差额假设命令",
        )
        hypothesis_id = command["hypothesis_id"]
        if (
            not isinstance(hypothesis_id, str)
            or hypothesis_id not in _CASH_CLOCK_HYPOTHESES
        ):
            raise ValueError("hypothesis_id不属于当前题目的合法假设。")
        clean_payload = {"hypothesis_id": hypothesis_id}
    elif action == "submit_orders":
        _require_exact_keys(
            command,
            required=common_fields | {"pockets"},
            optional={"discarded"},
            subject="调查令命令",
        )
        raw_pockets = command["pockets"]
        if not isinstance(raw_pockets, Mapping):
            raise ValueError("pockets必须是调查目标到材料编号的对象。")
        pocket_ids = set(raw_pockets)
        unknown_pockets = pocket_ids - _CASH_CLOCK_POCKET_IDS
        missing_pockets = _CASH_CLOCK_POCKET_IDS - pocket_ids
        if unknown_pockets:
            raise ValueError(
                "pockets包含未知调查目标："
                f"{', '.join(sorted(str(item) for item in unknown_pockets))}。"
            )
        if missing_pockets:
            raise ValueError(
                "pockets缺少调查目标："
                f"{', '.join(sorted(missing_pockets))}。"
            )
        pockets: dict[str, str] = {}
        for pocket_id in sorted(_CASH_CLOCK_POCKET_IDS):
            order_id = raw_pockets[pocket_id]
            if not isinstance(order_id, str) or order_id not in _CASH_CLOCK_ORDER_IDS:
                raise ValueError(f"调查目标{pocket_id}使用了未知材料编号。")
            pockets[pocket_id] = order_id

        discarded_value = command.get("discarded", [])
        if not isinstance(discarded_value, (list, tuple)):
            raise ValueError("discarded必须是材料编号列表。")
        if len(discarded_value) > 1:
            raise ValueError("调查令最多只能丢弃1项干扰材料。")
        discarded: list[str] = []
        for order_id in discarded_value:
            if not isinstance(order_id, str) or order_id not in _CASH_CLOCK_ORDER_IDS:
                raise ValueError("discarded包含未知材料编号。")
            discarded.append(order_id)

        used_order_ids = list(pockets.values()) + discarded
        if len(set(used_order_ids)) != len(used_order_ids):
            raise ValueError("同一调查材料不能重复放入多个位置。")
        clean_payload = {"pockets": pockets, "discarded": discarded}
    else:
        _require_exact_keys(
            command,
            required=common_fields,
            subject="场景动作命令",
        )
        clean_payload = {}

    return {
        "schema_version": CASH_CLOCK_COMMAND_SCHEMA_VERSION,
        "command_id": command_id,
        "question_id": question_id,
        "revision": revision,
        "action": action,
        "clean_payload": clean_payload,
    }


def _cash_clock_result(
    command: CashClockCommand,
    *,
    phase: str,
    accepted: list[str],
    rejected: list[str],
    feedback: str,
    complete: bool,
) -> CashClockCommandEvaluation:
    """Build one stable result shape for all three visual-game phases."""

    return {
        "phase": phase,
        "action": command["action"],
        "accepted": accepted,
        "rejected": rejected,
        "feedback": feedback,
        "complete": complete,
        "clean_payload": command["clean_payload"],
    }


def evaluate_cash_clock_bins(
    question: CashTimingQuestion,
    raw_command: object,
    expected_revision: int,
) -> CashClockCommandEvaluation:
    """Authoritatively classify all six facts into four semantic regions."""

    command = normalise_cash_clock_command(
        question, raw_command, expected_revision
    )
    if command["action"] != "submit_routes":
        raise ValueError("事实卡判定只接受submit_routes命令。")
    bins = command["clean_payload"]["bins"]
    assert isinstance(bins, dict)

    expected_bins: dict[str, str] = {}
    event_ids: list[str] = []
    for event in question["event_cards"]:
        event_id = event["event_id"]
        event_ids.append(event_id)
        if event["affects_profit"] and event["affects_cash"]:
            expected_bins[event_id] = "both"
        elif event["affects_profit"]:
            expected_bins[event_id] = "profit"
        elif event["affects_cash"]:
            expected_bins[event_id] = "cash"
        else:
            expected_bins[event_id] = "neither"

    accepted = [
        event_id
        for event_id in event_ids
        if bins[event_id] == expected_bins[event_id]
    ]
    rejected = [event_id for event_id in event_ids if event_id not in accepted]
    complete = not rejected
    if complete:
        feedback = (
            "六张事实卡都已归位。履约和成本发生回答利润，银行实收实付"
            "回答现金；合同签署和未来承诺本身不改变这两只时钟。"
        )
    elif "future_payment_plan" in rejected or "contract_signed" in rejected:
        feedback = (
            f"已有{len(accepted)}张归位，{len(rejected)}张仍需复核。承诺、"
            "合同和实际发生不是一回事；先问履约，再问银行是否真的收付。"
        )
    else:
        feedback = (
            f"已有{len(accepted)}张归位，{len(rejected)}张仍需复核。成本"
            "发生影响利润，费用实际支付影响现金，同一业务事实不要重复计算。"
        )
    return _cash_clock_result(
        command,
        phase="routes",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback,
        complete=complete,
    )


def evaluate_cash_gap_hypothesis(
    question: CashTimingQuestion,
    raw_command: object,
    expected_revision: int,
) -> CashClockCommandEvaluation:
    """Check whether the gap is framed as a testable receivable hypothesis."""

    command = normalise_cash_clock_command(
        question, raw_command, expected_revision
    )
    if command["action"] != "submit_hypothesis":
        raise ValueError("差额假设判定只接受submit_hypothesis命令。")
    hypothesis_id = command["clean_payload"]["hypothesis_id"]
    assert isinstance(hypothesis_id, str)
    complete = hypothesis_id == "receivable_pending"
    accepted = [hypothesis_id] if complete else []
    rejected = [] if complete else [hypothesis_id]
    feedback_by_hypothesis = {
        "receivable_pending": (
            "假设成立，但尚未成为结论：利润与现金的差额可能形成应收款，"
            "下一步必须用履约、期末余额和期后回款交叉核实。"
        ),
        "proven_fraud": (
            "差额只能触发调查，不能直接证明造假。把怀疑写成结论，会让"
            "后续证据只剩下替结论找理由。"
        ),
        "customer_default": (
            "尚未核对合同期限和账龄，不能把未收款直接升级为客户违约。"
        ),
        "cash_received": (
            "收入确认、应收款和客户付款承诺都不是银行到账。现金只认"
            "报告期内真实发生的收付。"
        ),
    }
    return _cash_clock_result(
        command,
        phase="hypothesis",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback_by_hypothesis[hypothesis_id],
        complete=complete,
    )


def evaluate_cash_investigation_orders(
    question: CashTimingQuestion,
    raw_command: object,
    expected_revision: int,
) -> CashClockCommandEvaluation:
    """Match three evidence requests and reject a management promise."""

    command = normalise_cash_clock_command(
        question, raw_command, expected_revision
    )
    if command["action"] != "submit_orders":
        raise ValueError("调查令判定只接受submit_orders命令。")
    pockets = command["clean_payload"]["pockets"]
    discarded = command["clean_payload"]["discarded"]
    assert isinstance(pockets, dict)
    assert isinstance(discarded, list)

    accepted: list[str] = []
    rejected: list[str] = []
    for pocket_id in sorted(_CASH_CLOCK_POCKET_IDS):
        order_id = pockets[pocket_id]
        if order_id == _CASH_CLOCK_CORRECT_ORDERS[pocket_id]:
            accepted.append(order_id)
        else:
            rejected.append(order_id)
    if discarded:
        if discarded[0] == "management_promise":
            accepted.append("management_promise")
        else:
            rejected.append(discarded[0])

    complete = all(
        pockets[pocket_id] == expected_order_id
        for pocket_id, expected_order_id in _CASH_CLOCK_CORRECT_ORDERS.items()
    )
    if complete:
        feedback = (
            "调查令已封装：履约验收核对收入边界，期末应收核对余额存在，"
            "期后银行流水核对后来回款。管理层承诺只能提供方向，不能替代证据。"
        )
    elif "management_promise" in pockets.values():
        feedback = (
            "管理层承诺被误放进了证据口袋。它可以提示去哪里查，却不能"
            "证明履约、年末余额或后来到账。"
        )
    else:
        feedback = (
            f"{len(accepted)}项调查令方向正确，{len(rejected)}项需要换位。"
            "三只口袋分别回答：收入何时赚到、年末还欠多少、后来是否到账。"
        )
    return _cash_clock_result(
        command,
        phase="orders",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback,
        complete=complete,
    )


def build_cash_evidence_case(attempt_index: int) -> CashEvidenceCase:
    """Build one six-document investigation tied to the selected dossier.

    Four documents form a complete, cross-checked chain. Two polished-looking
    documents are distractions because they are internal claims rather than
    proof of performance or cash collection.
    """
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError("证据卷宗序号必须是非负整数。")

    # Scene four is the investigation opened by scene three's signed order,
    # not a second, unrelated case.  Reuse the same reporting boundary,
    # revenue and cash received so the player never walks through a door and
    # finds that the company and amounts have silently changed.
    timing_question = build_cash_timing_question(attempt_index)
    reporting_date = timing_question["reporting_date"]
    contract_amount_wan = timing_question["revenue_wan"]
    deposit_wan = timing_question["cash_collected_wan"]
    outstanding_wan = contract_amount_wan - deposit_wan
    acceptance_event = next(
        event
        for event in timing_question["event_cards"]
        if event["event_id"] == "service_completed"
    )
    acceptance_date = acceptance_event["event_date"]
    payment_days = (30, 45, 60)[attempt_index % 3]
    due_date = acceptance_date + timedelta(days=payment_days)
    receipt_date = due_date - timedelta(days=attempt_index % 4)
    contract_number = f"LQ-AI-25-{170 + attempt_index:03d}"
    customer_name = (
        "远澜制造"
        if attempt_index % 2 == 0
        else "辰峰物流"
    )

    documents: list[EvidenceDocument] = [
        {
            "document_id": "executive_slide",
            "location": "会议室投影幕布",
            "title": "年度经营冲刺会｜项目已全面成功",
            "document_type": "内部管理层演示稿",
            "body": (
                f"演示稿写着“{customer_name}项目预计贡献收入"
                f"{contract_amount_wan}万元，回款确定性高”，页面右下角"
                "标注“内部讨论稿，不对外”。没有客户签章、验收编号或"
                "银行流水。"
            ),
            "footer": "制作部门：战略运营部｜证据日期：2025-12-18",
        },
        {
            "document_id": "contract_clause",
            "location": "上锁的合同柜",
            "title": f"技术服务合同节选｜{contract_number}",
            "document_type": "双方盖章合同",
            "body": (
                f"合同总价{contract_amount_wan}万元。客户先支付"
                f"{deposit_wan}万元；项目通过最终验收后"
                f"{payment_days}日内支付剩余款项。合同写明，最终验收"
                "以双方签署的验收确认书为准。"
            ),
            "footer": f"签约双方：岚桥智能 / {customer_name}｜已核对印章",
        },
        {
            "document_id": "celebration_chat",
            "location": "茶水间遗落的手机",
            "title": "项目群聊天截图｜终于交付了！",
            "document_type": "内部聊天记录",
            "body": (
                "项目经理发出庆祝表情并写道：“客户应该挺满意，销售说"
                "这单没问题，年终奖稳了。”聊天中没有客户本人、验收"
                "附件或款项入账记录。"
            ),
            "footer": f"群名：{customer_name}交付突击队｜截图日期：{acceptance_date}",
        },
        {
            "document_id": "signed_acceptance",
            "location": "打印机出纸托盘",
            "title": "系统运行确认单｜附件C（看起来像普通运维表）",
            "document_type": "客户签署的最终验收确认书",
            "body": (
                f"确认单引用合同{contract_number}，列明全部功能测试通过、"
                "遗留缺陷为0，并写明“同意最终验收”。落款日期为"
                f"{acceptance_date.isoformat()}，盖有{customer_name}"
                "合同专用章。"
            ),
            "footer": "页脚编号与合同附件清单一致｜外部证据",
        },
        {
            "document_id": "ar_subledger",
            "location": "财务共享盘的深层文件夹",
            "title": "12月31日往来余额明细_最终版7.xlsx",
            "document_type": "应收账款客户明细与账龄表",
            "body": (
                f"客户：{customer_name}；合同：{contract_number}；年末"
                f"未收余额{outstanding_wan}万元；账龄0—30天；合同到期日"
                f"{due_date.isoformat()}；截至年末标记“未逾期”。总账与"
                "明细账余额勾稽一致。"
            ),
            "footer": "内部会计记录｜需要与外部文件交叉核验",
        },
        {
            "document_id": "post_period_receipt",
            "location": "碎纸机旁的待归档纸袋",
            "title": "其他往来款入账回单｜系统自动打印",
            "document_type": "期后银行入账回单",
            "body": (
                f"入账日期{receipt_date.isoformat()}；付款人{customer_name}；"
                f"金额{outstanding_wan}万元；附言仅写“{contract_number}"
                "尾款”。金额与年末应收明细中的未收余额完全一致。"
            ),
            "footer": "银行电子回单编号可核验｜发生在报告期后",
        },
    ]
    rotation = (attempt_index * 2) % len(documents)
    documents = documents[rotation:] + documents[:rotation]

    required_document_ids = [
        "contract_clause",
        "signed_acceptance",
        "ar_subledger",
        "post_period_receipt",
    ]
    question = (
        "请选择4份材料，组成目前最完整的证据链，同时回答：业务是否在"
        "年末前完成、年末现金为什么尚未全部收到、未收余额是否超过合同"
        "期限，以及款项后来是否真正到账。"
    )
    explanation = (
        f"合同说明剩余款在验收后{payment_days}日内支付；客户签署的验收"
        f"确认书证明业务在{acceptance_date.isoformat()}前完成；应收明细"
        f"显示年末尚欠{outstanding_wan}万元且未逾期；期后银行回单又以"
        "相同合同编号和金额证明款项后来到账。这条链可以解释本案中的"
        "利润—现金时间差，但仍不代表所有类似差异都没有风险。管理层"
        "演示稿和内部聊天只能提供线索，不能替代客户或银行证据。"
    )
    return {
        "case_id": (
            f"cash-evidence-{attempt_index + 1}-"
            f"{contract_amount_wan}-{outstanding_wan}"
        ),
        "attempt_number": attempt_index + 1,
        "reporting_date": reporting_date,
        "acceptance_date": acceptance_date,
        "due_date": due_date,
        "receipt_date": receipt_date,
        "payment_days": payment_days,
        "customer_name": customer_name,
        "contract_number": contract_number,
        "contract_amount_wan": contract_amount_wan,
        "outstanding_wan": outstanding_wan,
        "documents": documents,
        "required_document_ids": required_document_ids,
        "question": question,
        "explanation": explanation,
    }


def build_cash_cross_check_task(
    evidence_case: CashEvidenceCase,
) -> CashCrossCheckTask:
    """Build a changing report-date boundary check from the active file.

    The answer depends on dates and source quality in the current documents,
    not on a fixed option position.  The later bank receipt is useful evidence,
    but it cannot be moved backwards and treated as year-end cash.
    """
    reporting_date = evidence_case["reporting_date"]
    correct_options = [
        (
            f"合同约定：{evidence_case['customer_name']}在最终验收后"
            f"{evidence_case['payment_days']}日内支付尾款。"
        ),
        (
            f"客户签章材料显示：项目已于"
            f"{evidence_case['acceptance_date'].isoformat()}完成最终验收。"
        ),
        (
            f"年末明细显示：截至{reporting_date.isoformat()}仍有"
            f"{evidence_case['outstanding_wan']}万元未收，但尚未逾期。"
        ),
    ]
    distractors = [
        (
            f"{evidence_case['receipt_date'].isoformat()}的银行回单证明："
            f"{reporting_date.isoformat()}当天已经收齐全部现金。"
        ),
        "项目群庆祝消息足以替代客户签署的最终验收文件。",
        "管理层写下“回款确定性高”，因此可以直接证明银行账户已经收款。",
    ]
    options = correct_options + distractors
    rotation = evidence_case["attempt_number"] % len(options)
    options = options[rotation:] + options[:rotation]
    return {
        "task_id": f"cross-check-{evidence_case['case_id']}",
        "prompt": (
            "只依据当前卷宗，选出恰好3条在报告期末已有材料直接支持的"
            "事实。注意：期后证据可以帮助核验，但不能倒流成年末事实。"
        ),
        "options": options,
        "correct_options": correct_options,
        "explanation": (
            "合同负责付款条件，客户签章文件负责完成时点，年末明细负责"
            "未收金额和是否逾期；期后银行回单只能证明后来到账。内部群聊"
            "和管理层判断可以成为搜索线索，但不能独立证明外部事实。"
        ),
    }


CASH_EVIDENCE_LAB_COMMAND_SCHEMA_VERSION = 1

_CASH_EVIDENCE_LAB_ACTIONS = {
    "submit_reading",
    "submit_classification",
    "submit_chain",
}
_CASH_EVIDENCE_LAB_CLASS_IDS = {
    "year_end_fact",
    "subsequent_evidence",
    "unverified_claim",
}
_CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS = {
    "contract_reference",
    "contract_payment_window",
    "acceptance_date",
    "acceptance_external_seal",
    "ar_year_end_balance",
    "ar_due_status",
    "receipt_date",
    "receipt_bank_match",
}
_CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER = {
    "contract_term_at_year_end": "year_end_fact",
    "signed_acceptance_before_cutoff": "year_end_fact",
    "year_end_ar_not_due": "year_end_fact",
    "later_bank_receipt": "subsequent_evidence",
    "chat_expectation": "unverified_claim",
    "management_forecast": "unverified_claim",
}
_CASH_EVIDENCE_LAB_CHAIN_ANSWER = {
    "claim_payment_boundary": "contract_clause",
    "claim_completion_before_cutoff": "signed_acceptance",
    "claim_year_end_balance": "ar_subledger",
    "claim_later_cash": "post_period_receipt",
}


def _cash_evidence_lab_task_id(evidence_case: CashEvidenceCase) -> str:
    """Return the stable public identifier shared by all three lab scenes."""

    return f"cash-evidence-lab:{evidence_case['case_id']}"


def _cash_evidence_lab_documents(
    evidence_case: CashEvidenceCase,
) -> dict[str, EvidenceDocument]:
    """Validate and index the six documents without exposing relevance."""

    documents = {
        document["document_id"]: document
        for document in evidence_case["documents"]
    }
    if len(documents) != len(evidence_case["documents"]):
        raise ValueError("当前证据卷宗的材料编号存在重复。")
    expected_ids = {
        "executive_slide",
        "contract_clause",
        "celebration_chat",
        "signed_acceptance",
        "ar_subledger",
        "post_period_receipt",
    }
    if set(documents) != expected_ids:
        raise ValueError("当前证据卷宗缺少证据实验室所需材料。")
    return documents


def build_cash_evidence_lab_public_task(
    evidence_case: CashEvidenceCase,
) -> dict[str, object]:
    """Build the answer-free Stage 5--7 contract consumed by the browser.

    The public task contains only objects the player can see or manipulate.
    Correct field marks, category placements and evidence links remain in
    module-private Python mappings and are evaluated only after submission.
    """

    documents = _cash_evidence_lab_documents(evidence_case)
    document_cards = [
        {
            "document_id": document["document_id"],
            "location": document["location"],
            "title": document["title"],
            "document_type": document["document_type"],
            "body": document["body"],
            "footer": document["footer"],
        }
        for document in evidence_case["documents"]
    ]
    field_options = [
        {
            "field_id": "contract_reference",
            "document_id": "contract_clause",
            "label": f"合同编号 {evidence_case['contract_number']} 与双方盖章",
        },
        {
            "field_id": "contract_payment_window",
            "document_id": "contract_clause",
            "label": (
                f"最终验收后{evidence_case['payment_days']}日内支付尾款"
            ),
        },
        {
            "field_id": "contract_polished_layout",
            "document_id": "contract_clause",
            "label": "合同采用正式排版并带有公司页眉",
        },
        {
            "field_id": "acceptance_date",
            "document_id": "signed_acceptance",
            "label": (
                "最终验收落款日 "
                f"{evidence_case['acceptance_date'].isoformat()}"
            ),
        },
        {
            "field_id": "acceptance_external_seal",
            "document_id": "signed_acceptance",
            "label": f"{evidence_case['customer_name']}合同专用章",
        },
        {
            "field_id": "acceptance_plain_title",
            "document_id": "signed_acceptance",
            "label": "文件标题看起来只是一张普通运维表",
        },
        {
            "field_id": "ar_year_end_balance",
            "document_id": "ar_subledger",
            "label": (
                f"报告期末未收余额{evidence_case['outstanding_wan']}万元"
            ),
        },
        {
            "field_id": "ar_due_status",
            "document_id": "ar_subledger",
            "label": (
                f"合同到期日{evidence_case['due_date'].isoformat()}，"
                "年末未逾期"
            ),
        },
        {
            "field_id": "ar_filename_version",
            "document_id": "ar_subledger",
            "label": "文件名带有“最终版7”字样",
        },
        {
            "field_id": "receipt_date",
            "document_id": "post_period_receipt",
            "label": (
                f"银行入账日{evidence_case['receipt_date'].isoformat()}"
            ),
        },
        {
            "field_id": "receipt_bank_match",
            "document_id": "post_period_receipt",
            "label": (
                f"付款人、合同号和{evidence_case['outstanding_wan']}万元"
                "均与年末应收匹配"
            ),
        },
        {
            "field_id": "receipt_auto_printed",
            "document_id": "post_period_receipt",
            "label": "回单由系统自动打印",
        },
        {
            "field_id": "slide_confidence_phrase",
            "document_id": "executive_slide",
            "label": "管理层写下“回款确定性高”",
        },
        {
            "field_id": "chat_bonus_phrase",
            "document_id": "celebration_chat",
            "label": "项目经理在群聊中写下“年终奖稳了”",
        },
    ]
    classification_items = [
        {
            "item_id": "contract_term_at_year_end",
            "label": (
                f"合同在年末前已经约定：验收后"
                f"{evidence_case['payment_days']}日内支付尾款。"
            ),
        },
        {
            "item_id": "signed_acceptance_before_cutoff",
            "label": (
                f"客户于{evidence_case['acceptance_date'].isoformat()}"
                "签署最终验收确认书。"
            ),
        },
        {
            "item_id": "year_end_ar_not_due",
            "label": (
                f"截至{evidence_case['reporting_date'].isoformat()}仍有"
                f"{evidence_case['outstanding_wan']}万元未收且尚未逾期。"
            ),
        },
        {
            "item_id": "later_bank_receipt",
            "label": (
                f"{evidence_case['receipt_date'].isoformat()}银行回单显示"
                "尾款后来到账。"
            ),
        },
        {
            "item_id": "chat_expectation",
            "label": "项目群认为客户满意、奖金已经稳了。",
        },
        {
            "item_id": "management_forecast",
            "label": "管理层预计回款确定性高。",
        },
    ]
    chain_claims = [
        {
            "claim_id": "claim_payment_boundary",
            "label": "尾款何时到期，由什么条件触发？",
        },
        {
            "claim_id": "claim_completion_before_cutoff",
            "label": "业务是否在报告期末前完成？",
        },
        {
            "claim_id": "claim_year_end_balance",
            "label": "年末还有多少未收，是否已经逾期？",
        },
        {
            "claim_id": "claim_later_cash",
            "label": "未收尾款后来是否真正进入银行账户？",
        },
    ]
    return {
        "schema_version": CASH_EVIDENCE_LAB_COMMAND_SCHEMA_VERSION,
        "task_id": _cash_evidence_lab_task_id(evidence_case),
        "case_id": evidence_case["case_id"],
        "reading": {
            "documents": document_cards,
            "field_options": field_options,
            "required_view_count": len(documents),
            "target_mark_count": len(
                _CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS
            ),
        },
        "classification": {
            "classes": [
                {"class_id": "year_end_fact", "label": "年末事实"},
                {
                    "class_id": "subsequent_evidence",
                    "label": "期后证据",
                },
                {"class_id": "unverified_claim", "label": "未经证实"},
            ],
            "items": classification_items,
        },
        "chain": {
            "claims": chain_claims,
            "documents": document_cards,
        },
    }


def _normalise_cash_evidence_lab_id_list(
    value: object,
    *,
    allowed_ids: set[str],
    subject: str,
) -> list[str]:
    """Validate one JSON ID list and preserve its submitted order."""

    if not isinstance(value, list):
        raise ValueError(f"{subject}必须是编号列表。")
    clean_ids: list[str] = []
    for raw_id in value:
        if not isinstance(raw_id, str) or raw_id not in allowed_ids:
            raise ValueError(f"{subject}包含未知编号。")
        clean_ids.append(raw_id)
    if len(set(clean_ids)) != len(clean_ids):
        raise ValueError(f"{subject}不能包含重复编号。")
    return clean_ids


def normalise_cash_evidence_lab_command(
    evidence_case: CashEvidenceCase,
    command: object,
    expected_revision: int,
) -> CashEvidenceLabCommand:
    """Strictly validate one Stage 5--7 browser command.

    Only player-authored placements are normalised.  The returned payload does
    not contain correctness flags or any of the private answer mappings.
    """

    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        raise ValueError("服务端证据实验室版本必须是非负整数。")
    if not isinstance(command, Mapping):
        raise ValueError("证据实验室命令必须是对象。")
    common_fields = {
        "schema_version",
        "command_id",
        "task_id",
        "revision",
        "action",
    }
    _require_exact_keys(
        command,
        required=common_fields,
        optional={
            "viewed_document_ids",
            "marked_field_ids",
            "placements",
            "links",
        },
        subject="证据实验室命令",
    )
    schema_version = command["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CASH_EVIDENCE_LAB_COMMAND_SCHEMA_VERSION
    ):
        raise ValueError("证据实验室命令schema_version不受支持。")
    command_id = command["command_id"]
    if (
        not isinstance(command_id, str)
        or not _COMMAND_ID_PATTERN.fullmatch(command_id)
    ):
        raise ValueError("证据实验室命令command_id格式无效。")
    task_id = command["task_id"]
    if (
        not isinstance(task_id, str)
        or task_id != _cash_evidence_lab_task_id(evidence_case)
    ):
        raise ValueError("证据实验室命令task_id与当前卷宗不一致。")
    revision = command["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("证据实验室命令revision必须是整数。")
    if revision != expected_revision:
        raise ValueError("证据实验室命令revision已经过期。")
    action = command["action"]
    if not isinstance(action, str) or action not in _CASH_EVIDENCE_LAB_ACTIONS:
        raise ValueError("证据实验室命令action不受支持。")

    public_task = build_cash_evidence_lab_public_task(evidence_case)
    reading = public_task["reading"]
    classification = public_task["classification"]
    chain = public_task["chain"]
    assert isinstance(reading, Mapping)
    assert isinstance(classification, Mapping)
    assert isinstance(chain, Mapping)
    document_ids = {
        document["document_id"]
        for document in reading["documents"]  # type: ignore[index,union-attr]
    }
    field_ids = {
        option["field_id"]
        for option in reading["field_options"]  # type: ignore[index,union-attr]
    }
    classification_ids = {
        item["item_id"]
        for item in classification["items"]  # type: ignore[index,union-attr]
    }
    claim_ids = {
        claim["claim_id"]
        for claim in chain["claims"]  # type: ignore[index,union-attr]
    }

    clean_payload: dict[str, object]
    if action == "submit_reading":
        _require_exact_keys(
            command,
            required=common_fields
            | {"viewed_document_ids", "marked_field_ids"},
            subject="证物研读命令",
        )
        clean_payload = {
            "viewed_document_ids": _normalise_cash_evidence_lab_id_list(
                command["viewed_document_ids"],
                allowed_ids=document_ids,
                subject="viewed_document_ids",
            ),
            "marked_field_ids": _normalise_cash_evidence_lab_id_list(
                command["marked_field_ids"],
                allowed_ids=field_ids,
                subject="marked_field_ids",
            ),
        }
    elif action == "submit_classification":
        _require_exact_keys(
            command,
            required=common_fields | {"placements"},
            subject="时间边界分类命令",
        )
        raw_placements = command["placements"]
        if not isinstance(raw_placements, Mapping):
            raise ValueError("placements必须是材料编号到区域编号的对象。")
        unknown_ids = set(raw_placements) - classification_ids
        if unknown_ids:
            raise ValueError("placements包含未知分类卡编号。")
        placements: dict[str, str] = {}
        for item_id, raw_class_id in raw_placements.items():
            if not isinstance(item_id, str):
                raise ValueError("placements的分类卡编号必须是字符串。")
            if (
                not isinstance(raw_class_id, str)
                or raw_class_id not in _CASH_EVIDENCE_LAB_CLASS_IDS
            ):
                raise ValueError(f"分类卡{item_id}的区域编号无效。")
            placements[item_id] = raw_class_id
        clean_payload = {"placements": placements}
    else:
        _require_exact_keys(
            command,
            required=common_fields | {"links"},
            subject="证据链连线命令",
        )
        raw_links = command["links"]
        if not isinstance(raw_links, Mapping):
            raise ValueError("links必须是主张编号到材料编号的对象。")
        unknown_claims = set(raw_links) - claim_ids
        if unknown_claims:
            raise ValueError("links包含未知主张编号。")
        links: dict[str, str] = {}
        for claim_id, raw_document_id in raw_links.items():
            if not isinstance(claim_id, str):
                raise ValueError("links的主张编号必须是字符串。")
            if (
                not isinstance(raw_document_id, str)
                or raw_document_id not in document_ids
            ):
                raise ValueError(f"主张{claim_id}使用了未知材料编号。")
            links[claim_id] = raw_document_id
        clean_payload = {"links": links}

    return {
        "schema_version": CASH_EVIDENCE_LAB_COMMAND_SCHEMA_VERSION,
        "command_id": command_id,
        "task_id": task_id,
        "revision": revision,
        "action": action,
        "clean_payload": clean_payload,
    }


def _cash_evidence_lab_result(
    command: CashEvidenceLabCommand,
    *,
    phase: str,
    accepted: list[str],
    rejected: list[str],
    feedback: str,
    complete: bool,
    target_count: int,
) -> CashEvidenceLabEvaluation:
    """Return enough information to lock correct work and release only errors."""

    return {
        "phase": phase,
        "action": command["action"],
        "accepted": accepted,
        "rejected": rejected,
        "feedback": feedback,
        "complete": complete,
        "accepted_count": len(accepted),
        "target_count": target_count,
        "clean_payload": command["clean_payload"],
    }


def evaluate_cash_evidence_reading(
    evidence_case: CashEvidenceCase,
    raw_command: object,
    expected_revision: int,
) -> CashEvidenceLabEvaluation:
    """Require deliberate page views and evidence-bearing field marks."""

    command = normalise_cash_evidence_lab_command(
        evidence_case, raw_command, expected_revision
    )
    if command["action"] != "submit_reading":
        raise ValueError("证物研读判定只接受submit_reading命令。")
    viewed_document_ids = command["clean_payload"]["viewed_document_ids"]
    marked_field_ids = command["clean_payload"]["marked_field_ids"]
    assert isinstance(viewed_document_ids, list)
    assert isinstance(marked_field_ids, list)
    document_ids = set(_cash_evidence_lab_documents(evidence_case))
    accepted = [
        field_id
        for field_id in marked_field_ids
        if field_id in _CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS
    ]
    rejected = [
        field_id
        for field_id in marked_field_ids
        if field_id not in _CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS
    ]
    unseen_count = len(document_ids - set(viewed_document_ids))
    missing_mark_count = len(
        _CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS - set(accepted)
    )
    complete = (
        unseen_count == 0
        and missing_mark_count == 0
        and not rejected
    )
    if complete:
        feedback = (
            "六份材料已经逐页核验，八个决定时间、金额、来源与边界的"
            "字段已封装。"
        )
    elif rejected:
        feedback = (
            f"{len(accepted)}个关键字段已锁定，{len(rejected)}个标记只反映"
            "外观、语气或文件名，已退回。正确标记和阅读进度不会清空。"
        )
    elif unseen_count:
        feedback = (
            f"关键标记已锁定；仍有{unseen_count}份材料没有完整翻阅。"
            "干扰材料也要读，才能知道它缺少什么。"
        )
    else:
        feedback = (
            f"已锁定{len(accepted)}个关键字段，还缺{missing_mark_count}个。"
            "优先寻找日期、金额、合同号、签章、付款期限和独立来源。"
        )
    return _cash_evidence_lab_result(
        command,
        phase="reading",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback,
        complete=complete,
        target_count=len(_CASH_EVIDENCE_LAB_REQUIRED_FIELD_IDS),
    )


def evaluate_cash_evidence_classification(
    evidence_case: CashEvidenceCase,
    raw_command: object,
    expected_revision: int,
) -> CashEvidenceLabEvaluation:
    """Classify statements without turning later evidence into earlier fact."""

    command = normalise_cash_evidence_lab_command(
        evidence_case, raw_command, expected_revision
    )
    if command["action"] != "submit_classification":
        raise ValueError(
            "时间边界分类判定只接受submit_classification命令。"
        )
    placements = command["clean_payload"]["placements"]
    assert isinstance(placements, dict)
    accepted = [
        item_id
        for item_id in _CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER
        if placements.get(item_id)
        == _CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER[item_id]
    ]
    rejected = [
        item_id
        for item_id in _CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER
        if item_id in placements
        and placements[item_id]
        != _CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER[item_id]
    ]
    missing_count = len(
        set(_CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER) - set(placements)
    )
    complete = (
        len(accepted) == len(_CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER)
        and not rejected
    )
    if complete:
        feedback = (
            "时间边界已守住：年末事实、期后证据与未经证实的内部主张"
            "已经分开。"
        )
    elif rejected:
        feedback = (
            f"{len(accepted)}张卡已锁定，{len(rejected)}张卡放错时间或"
            "证明层级，已单独退回；不会重搜办公室，也不会更换卷宗。"
        )
    else:
        feedback = (
            f"{len(accepted)}张卡已锁定，仍有{missing_count}张未归位。"
            "问自己：这件事在年末已经发生，还是年后才出现？"
        )
    return _cash_evidence_lab_result(
        command,
        phase="classification",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback,
        complete=complete,
        target_count=len(_CASH_EVIDENCE_LAB_CLASSIFICATION_ANSWER),
    )


def evaluate_cash_evidence_chain(
    evidence_case: CashEvidenceCase,
    raw_command: object,
    expected_revision: int,
) -> CashEvidenceLabEvaluation:
    """Connect each research claim to the document that directly supports it."""

    command = normalise_cash_evidence_lab_command(
        evidence_case, raw_command, expected_revision
    )
    if command["action"] != "submit_chain":
        raise ValueError("证据链判定只接受submit_chain命令。")
    links = command["clean_payload"]["links"]
    assert isinstance(links, dict)
    accepted = [
        claim_id
        for claim_id in _CASH_EVIDENCE_LAB_CHAIN_ANSWER
        if links.get(claim_id) == _CASH_EVIDENCE_LAB_CHAIN_ANSWER[claim_id]
    ]
    rejected = [
        claim_id
        for claim_id in _CASH_EVIDENCE_LAB_CHAIN_ANSWER
        if claim_id in links
        and links[claim_id] != _CASH_EVIDENCE_LAB_CHAIN_ANSWER[claim_id]
    ]
    missing_count = len(set(_CASH_EVIDENCE_LAB_CHAIN_ANSWER) - set(links))
    complete = (
        len(accepted) == len(_CASH_EVIDENCE_LAB_CHAIN_ANSWER)
        and not rejected
    )
    if complete:
        feedback = (
            "四环证据链闭合：合同界定付款边界，客户验收证明履约，"
            "年末明细定位余额，银行回单验证后来到账。"
        )
    elif rejected:
        feedback = (
            f"{len(accepted)}条连线已锁定，{len(rejected)}条连线证明对象"
            "不匹配，已单独断开；其余正确工作全部保留。"
        )
    else:
        feedback = (
            f"{len(accepted)}条连线已锁定，还缺{missing_count}条。"
            "一份材料先回答一个最直接的问题，不要用语气代替来源。"
        )
    return _cash_evidence_lab_result(
        command,
        phase="chain",
        accepted=accepted,
        rejected=rejected,
        feedback=feedback,
        complete=complete,
        target_count=len(_CASH_EVIDENCE_LAB_CHAIN_ANSWER),
    )


def evaluate_cash_evidence_selection(
    evidence_case: CashEvidenceCase,
    selected_document_ids: list[str],
) -> EvidenceSelectionEvaluation:
    """Check whether the selected documents form the complete evidence chain."""
    available_ids = {
        document["document_id"] for document in evidence_case["documents"]
    }
    selected_ids = set(selected_document_ids)
    unknown_ids = selected_ids - available_ids
    if unknown_ids:
        raise ValueError("提交的证据编号不属于当前卷宗。")

    required_ids = set(evidence_case["required_document_ids"])
    missing_count = len(required_ids - selected_ids)
    distraction_count = len(selected_ids - required_ids)
    is_correct = missing_count == 0 and distraction_count == 0
    if is_correct:
        feedback = "证据链完整，四个研究问题都获得了相互核验的材料。"
    elif distraction_count and missing_count:
        feedback = (
            f"当前证据链还缺少{missing_count}个关键环节，同时混入了"
            f"{distraction_count}份只能提供线索、不能独立证明事实的材料。"
        )
    elif missing_count:
        feedback = (
            f"当前证据链还缺少{missing_count}个关键环节。请重新检查业务"
            "完成、合同期限、年末余额和期后收款是否都有人负责证明。"
        )
    else:
        feedback = (
            f"关键环节已经找到，但混入了{distraction_count}份证明力不足的"
            "材料。正式外观、管理层语气和庆祝聊天都不等于外部证据。"
        )
    return {
        "is_correct": is_correct,
        "missing_count": missing_count,
        "distraction_count": distraction_count,
        "feedback": feedback,
    }


def _rotate_options(options: list[str], offset: int) -> list[str]:
    """Move a changing answer away from a memorisable fixed position."""
    rotation = offset % len(options)
    return options[rotation:] + options[:rotation]


def build_cash_defense_question(
    round_index: int,
    attempt_index: int,
) -> CashDefenseQuestion:
    """Build one of three formal-defence rounds from a changing case.

    Round 1 asks for the current conclusion, round 2 for its evidence boundary,
    and round 3 for the next verification action.  Four scenario families
    rotate after wrong answers so the player must transfer the method instead
    of remembering one sentence.
    """
    if not isinstance(round_index, int) or not 0 <= round_index <= 2:
        raise ValueError("答辩轮次必须是0、1或2。")
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError("答辩题序号必须是非负整数。")

    scenario_index = (round_index + attempt_index) % 4
    amount_wan = 480 + attempt_index * 17 + round_index * 11
    company_names = ("澄海数据", "越岭医疗", "星港系统", "云川智造")
    company_name = company_names[scenario_index]

    if scenario_index == 0:
        scenario_type = "explained_timing_gap"
        evidence_items = [
            f"双方合同总价{amount_wan}万元，客户应在最终验收后45日内付清尾款。",
            "客户于2025-12-24签署最终验收确认书，遗留缺陷为0。",
            "2025-12-31应收明细显示尾款账龄0—30天，尚未超过合同期限。",
            "2026-01-29银行回单显示同一客户按合同编号付清全部尾款。",
        ]
        conclusion = (
            "本项目现有证据支持年末前完成履约；年末未收尾款属于合同期限内"
            "的时间差，且期后回款得到核验，但不能据此代表整家公司。"
        )
        boundary = (
            "这组材料只能解释这个项目的确认与回款，不能证明其他客户都能"
            "按期付款，也不能证明公司整体现金质量没有风险。"
        )
        next_step = (
            "抽取其他重要客户样本，继续核对合同、验收、年末账龄和期后"
            "银行回款，判断本项目是否具有代表性。"
        )
        conclusion_distractors = [
            "本项目年末前完成履约且期后已回款，因此2025年末应把尾款"
            "列为现金，而不是应收账款。",
            "本项目未逾期且后来收回，可以据此判断公司整体经营现金流"
            "下降都只是正常时间差。",
            "客户年末尚未付清尾款，所以即使已经验收，也必须等实际回款"
            "后才能确认这项收入。",
            "客户验收书和期后回单能够相互核验，因此合同付款条款和年末"
            "账龄不再影响判断。",
            "年末应收明细标记未逾期，已经足以排除风险，不需要期后银行"
            "回单或其他客户样本。",
        ]
    elif scenario_index == 1:
        scenario_type = "late_acceptance"
        evidence_items = [
            f"公司在2025-12-30将项目全部{amount_wan}万元记入收入。",
            "合同规定必须取得客户签署的最终验收书，才能视为履约完成。",
            "项目经理12月28日的内部邮件写着“客户应该没有意见”。",
            "客户最终验收书的签署日期为2026-01-08，未发现倒签证据。",
        ]
        conclusion = (
            "现有外部证据未支持项目在年末前完成最终验收，收入截止时点需要"
            "进一步调整或核验；但这些材料本身还不足以直接认定故意造假。"
        )
        boundary = (
            "可以质疑这一个项目的收入截止，却不能仅凭一份跨期验收书推断"
            "全部收入虚假、管理层存在主观故意或未来股价一定下跌。"
        )
        next_step = (
            "核对年末前后的交付日志、客户往来和会计凭证，确认实际履约"
            "完成日，并检查相应收入是否在正确期间调整。"
        )
        conclusion_distractors = [
            "内部邮件写明客户应该没有意见，可以替代正式验收书，现有证据"
            "足以支持全部收入留在2025年。",
            "客户在2026年才最终验收，所以可以直接认定这项业务在2025年"
            "没有发生任何履约活动。",
            "验收日期跨期已经证明管理层故意造假，无须再检查交付日志和"
            "会计调整。",
            "客户后来完成验收，能够追溯修复年末证据缺口，因此原确认日期"
            "不需要调整。",
            "项目已经接近完成且客户后来接受交付，所以年末确认全部收入"
            "属于合理估计，不需要合同约定的验收条件。",
        ]
    elif scenario_index == 2:
        scenario_type = "overdue_uncollected"
        evidence_items = [
            f"客户已于2025-10-15验收，总合同金额{amount_wan}万元。",
            "合同尾款到期日为2025-11-14，年末已经超过约定付款期限。",
            "年末应收余额与合同尾款一致，但截至2026-02-28仍未见银行回款。",
            "销售人员称客户经营正常，但没有客户确认或信用评估文件。",
        ]
        conclusion = (
            "履约完成有证据支持，但尾款已经逾期且期后仍未收回，应重点评估"
            "应收款可收回性和减值风险；逾期本身不自动推翻收入真实性。"
        )
        boundary = (
            "可以识别逾期和可收回性风险，不能把“尚未回款”直接写成“收入"
            "必然虚假”，也不能用销售人员口头判断替代客户外部证据。"
        )
        next_step = (
            "取得客户询证或还款安排，核验最新银行流水与客户信用状况，并"
            "复核公司对应收款减值的估计和会计处理。"
        )
        conclusion_distractors = [
            "尾款逾期且期后未收回，已经足以证明原收入不存在，应直接冲销"
            "全部收入。",
            "客户已经验收，说明收入和应收款都没有风险，不再需要评估"
            "可收回性。",
            "销售人员认为客户经营正常，可以替代客户询证和信用资料，因此"
            "无需确认减值。",
            "截至2月底仍未回款，所以应直接对全部尾款计提100%减值，不需要"
            "客户信用和还款安排。",
            "逾期发生在收入确认之后，只影响销售部门催款，不会影响财务"
            "报表中的应收款计量。",
        ]
    else:
        scenario_type = "partial_acceptance"
        phase_one_wan = amount_wan * 2 // 5
        evidence_items = [
            f"合同包含两个独立里程碑，总价{amount_wan}万元。",
            f"客户12月27日只验收第一阶段，对应合同价{phase_one_wan}万元。",
            "第二阶段仍有三项功能未上线，客户于2026-01-16才签署验收书。",
            f"公司在2025年已经记录全部{amount_wan}万元收入。",
        ]
        conclusion = (
            f"年末证据只支持第一阶段{phase_one_wan}万元的履约，全部"
            f"{amount_wan}万元收入缺少同期间验收支持，应复核履约义务分拆"
            "和收入计量；这不等于整个合同都没有商业实质。"
        )
        boundary = (
            "可以指出全部收入的确认依据不足，但不能忽略第一阶段已获客户"
            "验收的事实，也不能把部分跨期夸大成整个合同完全虚构。"
        )
        next_step = (
            "把合同价分配到两个履约里程碑，核对各阶段交付和验收日期，再"
            "重算年末能够获得证据支持的收入金额。"
        )
        conclusion_distractors = [
            "客户已经接受第一阶段，说明其认可整个合同，因此年末确认全部"
            "合同收入具有客户证据。",
            "第二阶段在年末尚未验收，所以第一阶段已经取得的客户验收也"
            "不能支持任何收入。",
            "两个阶段对应同一份合同，应按照客户实际付款比例分配收入，"
            "不需要分析各自履约义务。",
            "第二阶段在次年1月完成，距离年末较近，可以作为2025年末已经"
            "履约的替代证据。",
            "合同签署时总价已经确定，所以两个里程碑的验收时间只影响回款，"
            "不影响收入计量。",
        ]

    boundary_distractors = [
        "这组材料不能预测股价，但只要合同类型相同，就可以推断其他客户"
        "项目具有相同结论。",
        "判断只限于当前报告期；不过期后材料可以反过来改变年末实际发生"
        "的履约日期和现金余额。",
        "这组材料能够形成项目结论，因此也足以评价管理层主观动机，只是"
        "不能评价未来经营。",
        "只要明确写出合同编号和金额，单一项目的结论就可以代表公司整体"
        "收入质量。",
        "证据边界只限制措辞强弱，不限制结论覆盖的客户、期间和会计问题。",
    ]
    action_distractors = [
        "先比较同行业公司的平均回款周期，再用行业水平替代当前客户的"
        "合同和回款证据。",
        "先扩大到更多客户和更多年度，把当前项目尚未解决的问题留到样本"
        "扩大后统一判断。",
        "先复核公司五年经营现金流趋势；只要长期趋势改善，就不再处理"
        "当前证据缺口。",
        "先访谈负责该项目的销售人员，把其业务判断作为最主要的外部核验。",
        "先观察事项公开后的市场反应，再用股价涨跌判断会计确认是否正确。",
    ]

    round_titles = ("形成初步结论", "守住证据边界", "决定核验行动")
    if round_index == 0:
        prompt = "审查官问：根据当前四项材料，哪一条初步结论最严谨？"
        options = [conclusion, *conclusion_distractors]
        explanation = f"合格结论必须同时容纳支持证据、风险信号和限制：{conclusion}"
    elif round_index == 1:
        prompt = "审查官追问：哪一句最准确地说明这项判断不能证明什么？"
        options = [boundary, *boundary_distractors]
        explanation = f"研究边界决定结论能覆盖谁、哪个期间和什么问题：{boundary}"
    else:
        prompt = "审查官最后问：为了减少当前最重要的不确定性，下一步先做什么？"
        options = [next_step, *action_distractors]
        explanation = f"下一步工作应直接对应当前最大的证据缺口：{next_step}"

    options = _rotate_options(
        list(dict.fromkeys(options)),
        attempt_index * 2 + round_index + 1,
    )
    return {
        "question_id": (
            f"cash-defense-{round_index + 1}-{attempt_index + 1}-"
            f"{scenario_type}-{amount_wan}"
        ),
        "round_index": round_index,
        "round_number": round_index + 1,
        "round_title": round_titles[round_index],
        "attempt_number": attempt_index + 1,
        "scenario_type": scenario_type,
        "company_name": company_name,
        "evidence_items": evidence_items,
        "prompt": prompt,
        "options": options,
        "correct_option": (
            conclusion if round_index == 0 else boundary
            if round_index == 1 else next_step
        ),
        "explanation": explanation,
    }


CASH_DEFENSE_COMMITTEE_COMMAND_SCHEMA_VERSION = 1

_CASH_DEFENSE_COMMITTEE_ACTION = "submit_committee_statement"
_CASH_DEFENSE_COMMITTEE_SEATS = (
    "conclusion_strength",
    "evidence_boundary",
    "next_action",
)
_CASH_DEFENSE_SCENARIO_TYPES = (
    "explained_timing_gap",
    "late_acceptance",
    "overdue_uncollected",
    "partial_acceptance",
)


def _cash_defense_committee_bundle(
    round_index: int,
    challenge_index: int,
) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
    """Build one coherent three-seat challenge and keep answers private."""

    if not isinstance(round_index, int) or isinstance(round_index, bool):
        raise ValueError("委员会轮次必须是整数。")
    if not 0 <= round_index <= 2:
        raise ValueError("委员会轮次必须是0、1或2。")
    if (
        not isinstance(challenge_index, int)
        or isinstance(challenge_index, bool)
        or challenge_index < 0
    ):
        raise ValueError("委员会挑战序号必须是非负整数。")

    # Every committee round asks for a complete research statement.  A failed
    # formal challenge rotates only this scenario; already passed rounds live
    # outside this stateless builder and remain untouched.
    scenario_counter = round_index + challenge_index
    scenario_index = scenario_counter % len(_CASH_DEFENSE_SCENARIO_TYPES)
    cycle = scenario_counter // len(_CASH_DEFENSE_SCENARIO_TYPES)
    attempts = {
        "conclusion_strength": scenario_index + cycle * 4,
        "evidence_boundary": (scenario_index - 1) % 4 + cycle * 4,
        "next_action": (scenario_index - 2) % 4 + cycle * 4,
    }
    questions = {
        "conclusion_strength": build_cash_defense_question(
            0, attempts["conclusion_strength"]
        ),
        "evidence_boundary": build_cash_defense_question(
            1, attempts["evidence_boundary"]
        ),
        "next_action": build_cash_defense_question(
            2, attempts["next_action"]
        ),
    }
    scenario_type = _CASH_DEFENSE_SCENARIO_TYPES[scenario_index]
    if any(
        question["scenario_type"] != scenario_type
        for question in questions.values()
    ):
        raise ValueError("委员会三席未能生成同一情境。")

    seat_meta = {
        "conclusion_strength": {
            "title": "结论强度席",
            "examiner": "叶知衡｜首席审查官",
            "instruction": "只说证据能够支持的强度，不抢跑到定罪。",
        },
        "evidence_boundary": {
            "title": "证据边界席",
            "examiner": "沈砚清｜证据边界官",
            "instruction": "说明结论不能外推到谁、哪个期间和什么问题。",
        },
        "next_action": {
            "title": "行动优先席",
            "examiner": "程未央｜核验行动官",
            "instruction": "先补最能改变判断的缺口，不用大而空的调查。",
        },
    }
    seats: list[dict[str, object]] = []
    answer_by_seat: dict[str, str] = {}
    explanation_by_seat: dict[str, str] = {}
    for seat_id in _CASH_DEFENSE_COMMITTEE_SEATS:
        question = questions[seat_id]
        cards = [
            {
                "card_id": f"{seat_id}:card:{index + 1}",
                "text": option,
            }
            for index, option in enumerate(question["options"])
        ]
        correct_card = next(
            card
            for card in cards
            if card["text"] == question["correct_option"]
        )
        answer_by_seat[seat_id] = str(correct_card["card_id"])
        explanation_by_seat[seat_id] = question["explanation"]
        seats.append(
            {
                "seat_id": seat_id,
                **seat_meta[seat_id],
                "prompt": question["prompt"],
                "cards": cards,
            }
        )

    anchor_question = questions["conclusion_strength"]
    task_id = (
        f"cash-defense-committee:{round_index + 1}:"
        f"{challenge_index + 1}:{anchor_question['question_id']}"
    )
    public_task = {
        "schema_version": CASH_DEFENSE_COMMITTEE_COMMAND_SCHEMA_VERSION,
        "task_id": task_id,
        "round_index": round_index,
        "round_number": round_index + 1,
        "challenge_number": challenge_index + 1,
        "scenario_type": scenario_type,
        "company_name": anchor_question["company_name"],
        "evidence_items": list(anchor_question["evidence_items"]),
        "committee_rule": (
            "从三组答辩牌各取一枚，依次放上结论、边界与行动席。"
            "空席不消耗生命；正式错误才消耗一次容错并更换当前挑战。"
        ),
        "seats": seats,
    }
    return public_task, answer_by_seat, explanation_by_seat


def build_cash_defense_committee_public_task(
    round_index: int,
    challenge_index: int,
) -> dict[str, object]:
    """Return an answer-free draggable three-seat committee challenge."""

    public_task, _answer_by_seat, _explanation_by_seat = (
        _cash_defense_committee_bundle(round_index, challenge_index)
    )
    return public_task


def normalise_cash_defense_committee_command(
    round_index: int,
    challenge_index: int,
    command: object,
    expected_revision: int,
) -> CashDefenseCommitteeCommand:
    """Strictly validate one formal committee submission."""

    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        raise ValueError("服务端委员会版本必须是非负整数。")
    if not isinstance(command, Mapping):
        raise ValueError("委员会命令必须是对象。")
    common_fields = {
        "schema_version",
        "command_id",
        "task_id",
        "revision",
        "action",
        "placements",
    }
    _require_exact_keys(
        command,
        required=common_fields,
        subject="委员会命令",
    )
    schema_version = command["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CASH_DEFENSE_COMMITTEE_COMMAND_SCHEMA_VERSION
    ):
        raise ValueError("委员会命令schema_version不受支持。")
    command_id = command["command_id"]
    if (
        not isinstance(command_id, str)
        or not _COMMAND_ID_PATTERN.fullmatch(command_id)
    ):
        raise ValueError("委员会命令command_id格式无效。")
    public_task = build_cash_defense_committee_public_task(
        round_index, challenge_index
    )
    task_id = command["task_id"]
    if not isinstance(task_id, str) or task_id != public_task["task_id"]:
        raise ValueError("委员会命令task_id与当前挑战不一致。")
    revision = command["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise ValueError("委员会命令revision必须是整数。")
    if revision != expected_revision:
        raise ValueError("委员会命令revision已经过期。")
    action = command["action"]
    if action != _CASH_DEFENSE_COMMITTEE_ACTION:
        raise ValueError("委员会命令action不受支持。")
    raw_placements = command["placements"]
    if not isinstance(raw_placements, Mapping):
        raise ValueError("placements必须是席位编号到答辩牌编号的对象。")
    unknown_seats = set(raw_placements) - set(_CASH_DEFENSE_COMMITTEE_SEATS)
    if unknown_seats:
        raise ValueError("placements包含未知委员会席位。")

    seats = public_task["seats"]
    assert isinstance(seats, list)
    valid_cards_by_seat = {
        str(seat["seat_id"]): {
            str(card["card_id"])
            for card in seat["cards"]  # type: ignore[index,union-attr]
        }
        for seat in seats
    }
    placements: dict[str, str] = {}
    for raw_seat_id, raw_card_id in raw_placements.items():
        if not isinstance(raw_seat_id, str):
            raise ValueError("placements的席位编号必须是字符串。")
        if (
            not isinstance(raw_card_id, str)
            or raw_card_id not in valid_cards_by_seat[raw_seat_id]
        ):
            raise ValueError(f"席位{raw_seat_id}使用了无效答辩牌。")
        placements[raw_seat_id] = raw_card_id
    return {
        "schema_version": CASH_DEFENSE_COMMITTEE_COMMAND_SCHEMA_VERSION,
        "command_id": command_id,
        "task_id": task_id,
        "revision": revision,
        "action": _CASH_DEFENSE_COMMITTEE_ACTION,
        "clean_payload": {"placements": placements},
    }


def evaluate_cash_defense_committee(
    round_index: int,
    challenge_index: int,
    raw_command: object,
    expected_revision: int,
) -> CashDefenseCommitteeEvaluation:
    """Judge a full statement and charge lives only for formal errors."""

    command = normalise_cash_defense_committee_command(
        round_index,
        challenge_index,
        raw_command,
        expected_revision,
    )
    _public_task, answer_by_seat, explanation_by_seat = (
        _cash_defense_committee_bundle(round_index, challenge_index)
    )
    placements = command["clean_payload"]["placements"]
    assert isinstance(placements, dict)
    accepted = [
        seat_id
        for seat_id in _CASH_DEFENSE_COMMITTEE_SEATS
        if placements.get(seat_id) == answer_by_seat[seat_id]
    ]
    rejected = [
        seat_id
        for seat_id in _CASH_DEFENSE_COMMITTEE_SEATS
        if seat_id in placements
        and placements[seat_id] != answer_by_seat[seat_id]
    ]
    missing_count = len(set(_CASH_DEFENSE_COMMITTEE_SEATS) - set(placements))
    complete = (
        len(accepted) == len(_CASH_DEFENSE_COMMITTEE_SEATS)
        and not rejected
    )
    consume_life = bool(rejected)
    replace_challenge = bool(rejected)
    if complete:
        feedback = (
            "三席一致通过。"
            + " ".join(
                explanation_by_seat[seat_id]
                for seat_id in _CASH_DEFENSE_COMMITTEE_SEATS
            )
        )
    elif rejected:
        feedback = (
            f"{len(accepted)}席认可，{len(rejected)}席否决。正式答辩消耗"
            "1次容错并更换当前挑战；已经通过的委员会轮次继续保留，"
            "不回办公室、不重做证据链。"
        )
    else:
        feedback = (
            f"{len(accepted)}席已就位，仍有{missing_count}席为空。"
            "尚未形成完整陈述，不消耗容错。"
        )
    return {
        "phase": "committee",
        "action": command["action"],
        "accepted": accepted,
        "rejected": rejected,
        "feedback": feedback,
        "complete": complete,
        "accepted_count": len(accepted),
        "target_count": len(_CASH_DEFENSE_COMMITTEE_SEATS),
        "consume_life": consume_life,
        "replace_challenge": replace_challenge,
        "clean_payload": command["clean_payload"],
    }
