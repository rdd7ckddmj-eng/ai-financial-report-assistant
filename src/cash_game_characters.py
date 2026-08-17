"""Character, capability and keepsake design for ``The Missing Cash``.

The game uses one mentor per scene so that financial knowledge and research
habits are taught by a recognisable person instead of by anonymous UI copy.
This module contains no Streamlit code; the page layer decides how each mentor
and keepsake is presented.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CashGameMentor:
    """One scene mentor and the research habit represented by their keepsake."""

    step: int
    name: str
    role: str
    capability: str
    keepsake_id: str
    keepsake_name: str
    keepsake_mark: str
    reminder: str
    council_hint: str


CASH_GAME_MENTORS: tuple[CashGameMentor, ...] = (
    CashGameMentor(
        1,
        "周既白",
        "证据边界官",
        "克制与边界意识",
        "blank_access_card",
        "无字门禁卡",
        "▱",
        "结论的边界，和结论本身同样重要。",
        "先写下这份材料不能证明什么，再决定它能证明什么。",
    ),
    CashGameMentor(
        2,
        "沈知微",
        "会计语言导师",
        "概念拆解与双表思维",
        "dual_dial_watch",
        "双刻度怀表",
        "◴",
        "两根表针都在走，记录的却不是同一种时间。",
        "把利润与现金分别列式；不要让一个答案替另一张表说话。",
    ),
    CashGameMentor(
        3,
        "程砚舟",
        "时间线分析师",
        "时序建模与数据读取",
        "brass_timeline_ruler",
        "黄铜时间尺",
        "⌁",
        "顺序不是结论的装饰，它决定因果能否成立。",
        "先排事件，再计算；日期冲突时，任何总数都值得重算。",
    ),
    CashGameMentor(
        4,
        "叶观澜",
        "现场取证官",
        "观察力、细节与反直觉搜索",
        "frosted_lens",
        "暗纹放大镜",
        "⌕",
        "最醒目的未必关键，最普通的也未必无关。",
        "把你第一眼忽略的物件再看一次；关键线索常没有主角光环。",
    ),
    CashGameMentor(
        5,
        "裴叙言",
        "材料解码师",
        "深度阅读与限制词识别",
        "margin_ink_tab",
        "页边墨签",
        "▥",
        "读过材料不等于读懂；限制词往往比数字更昂贵。",
        "回到页脚、附言和条件句，找出数字成立所依赖的前提。",
    ),
    CashGameMentor(
        6,
        "苏棱",
        "交叉核验官",
        "来源独立性与一致性核验",
        "double_sided_prism",
        "双面棱镜",
        "◇",
        "一份材料引用另一份，不会凭空多出第二个独立来源。",
        "追到每条信息的最初出处；同源复述不能算交叉验证。",
    ),
    CashGameMentor(
        7,
        "顾临川",
        "因果架构师",
        "因果链、反事实与逻辑闭环",
        "causal_chain_clasp",
        "因果链扣",
        "⌘",
        "相关性只是门铃，不是屋里的主人。",
        "逐环检查事实、时间和机制；断掉一环，就把结论降级。",
    ),
    CashGameMentor(
        8,
        "许照夜",
        "反证审查官",
        "职业怀疑与不确定性控制",
        "reverse_black_piece",
        "逆向黑棋",
        "◆",
        "真正的怀疑也要接受审问，否则偏见只是换了制服。",
        "替相反结论寻找最强证据，再检查自己的怀疑是否同样可证伪。",
    ),
    CashGameMentor(
        9,
        "江衡远",
        "综合决策主席",
        "综合判断、清晰表达与责任意识",
        "unwritten_verdict_seal",
        "未落字裁决章",
        "◎",
        "成熟的判断不是消灭未知，而是准确标出未知。",
        "把事实、推断、未知和下一步行动分开说，结论才经得起复核。",
    ),
)


MENTOR_BY_STEP = {mentor.step: mentor for mentor in CASH_GAME_MENTORS}
MENTOR_BY_KEEPSAKE = {
    mentor.keepsake_id: mentor for mentor in CASH_GAME_MENTORS
}
KEEPSAKE_IDS = frozenset(MENTOR_BY_KEEPSAKE)


def mentor_for_step(step: int) -> CashGameMentor:
    """Return the bounded mentor used by one of the nine scenes."""
    return MENTOR_BY_STEP.get(step, MENTOR_BY_STEP[1])


def normalise_keepsake_ids(value: object) -> list[str]:
    """Return unique, known keepsakes in canonical scene order."""
    if not isinstance(value, (list, tuple)):
        return []
    supplied = {item for item in value if isinstance(item, str)}
    return [
        mentor.keepsake_id
        for mentor in CASH_GAME_MENTORS
        if mentor.keepsake_id in supplied
    ]


__all__ = [
    "CASH_GAME_MENTORS",
    "KEEPSAKE_IDS",
    "MENTOR_BY_KEEPSAKE",
    "CashGameMentor",
    "mentor_for_step",
    "normalise_keepsake_ids",
]
