"""Deterministic teaching and evidence tasks for the first finance case."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TypedDict


class CashTimingQuestion(TypedDict):
    """One changing profit-versus-cash practice sheet."""

    question_id: str
    attempt_number: int
    revenue_wan: int
    expense_wan: int
    cash_collected_wan: int
    profit_effect_wan: int
    cash_effect_wan: int
    prompt: str
    options: list[str]
    correct_option: str
    explanation: str


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
    contract_amount_wan: int
    outstanding_wan: int
    documents: list[EvidenceDocument]
    required_document_ids: list[str]
    question: str
    explanation: str


class EvidenceSelectionEvaluation(TypedDict):
    """Result of one document-chain submission."""

    is_correct: bool
    missing_count: int
    distraction_count: int
    feedback: str


def _signed_wan(value: int) -> str:
    """Format one signed amount without hiding zero behind a plus sign."""
    if value > 0:
        return f"+{value}万元"
    if value < 0:
        return f"-{abs(value)}万元"
    return "0万元"


def _option(profit_wan: int, cash_wan: int) -> str:
    return (
        f"利润 {_signed_wan(profit_wan)}；"
        f"本月现金 {_signed_wan(cash_wan)}"
    )


def build_cash_timing_question(attempt_index: int) -> CashTimingQuestion:
    """Build a new calculation sheet after every incorrect submission.

    Amounts change with the attempt index, so restarting the practice does not
    teach the player to memorise one option.  The underlying accounting logic
    remains stable and explainable.
    """
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError("练习题序号必须是非负整数。")

    revenue_wan = 120 + attempt_index * 7
    expense_wan = 70 + attempt_index * 3
    cash_collected_wan = (attempt_index * 13) % 61
    profit_effect_wan = revenue_wan - expense_wan
    cash_effect_wan = cash_collected_wan - expense_wan

    correct_option = _option(profit_effect_wan, cash_effect_wan)
    candidate_options = [
        correct_option,
        _option(revenue_wan, cash_collected_wan),
        _option(profit_effect_wan, cash_collected_wan),
        _option(cash_effect_wan, profit_effect_wan),
        _option(cash_effect_wan, cash_effect_wan),
        _option(profit_effect_wan, 0),
    ]
    unique_options = list(dict.fromkeys(candidate_options))
    if len(unique_options) < 5:
        unique_options.append(
            _option(revenue_wan - cash_collected_wan, -expense_wan)
        )

    rotation = (attempt_index * 2 + 1) % len(unique_options)
    options = unique_options[rotation:] + unique_options[:rotation]

    outstanding_wan = revenue_wan - cash_collected_wan
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
        "prompt": prompt,
        "options": options,
        "correct_option": correct_option,
        "explanation": explanation,
    }


def build_cash_evidence_case(attempt_index: int) -> CashEvidenceCase:
    """Build a new six-document investigation after each failed chain.

    Four documents form a complete, cross-checked chain. Two polished-looking
    documents are distractions because they are internal claims rather than
    proof of performance or cash collection.
    """
    if not isinstance(attempt_index, int) or attempt_index < 0:
        raise ValueError("证据卷宗序号必须是非负整数。")

    reporting_date = date(2025, 12, 31)
    contract_amount_wan = 460 + attempt_index * 23
    deposit_wan = 90 + attempt_index * 5
    outstanding_wan = contract_amount_wan - deposit_wan
    acceptance_date = date(2025, 12, 22) + timedelta(
        days=attempt_index % 5
    )
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
        "contract_amount_wan": contract_amount_wan,
        "outstanding_wan": outstanding_wan,
        "documents": documents,
        "required_document_ids": required_document_ids,
        "question": question,
        "explanation": explanation,
    }


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
