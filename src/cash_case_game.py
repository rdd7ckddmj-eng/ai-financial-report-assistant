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
