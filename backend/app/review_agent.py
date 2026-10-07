"""管理员审核 Agent（B-人机协同）：第一层"AI 规则初审员"。

这是毕业设计的核心亮点之一——典型的「Agent 规则初审 + 人工终审」人机协同范式：

    START -> rule_scan(确定性规则扫描)
                |
                +-- 命中明确违规 --> decision=rejected ----> END（自动驳回）
                |
                +-- 无任何风险信号 --> decision=approved --> END（自动通过）
                |
                +-- 存在边界信号 --> llm_review(大模型用途复核) --> END
                                       decision=approved / rejected / manual
                                                                  |
                                                          manual = 转人工终审

设计要点：
1. rule_scan 是纯确定性节点（时长、深夜、容量占比、信用分、用途敏感词……），
   结论稳定可解释、零 token 成本；只有"拿不准"的边界情况才调用大模型，省钱且可控。
2. 图节点只负责"裁决"（写 decision/reasons），不碰数据库；落库、扣分、发通知
   全部由 services 层在图外完成，图本身无副作用、易测试。
3. 大模型不可用或输出无法解析时，安全降级为 manual（转人工），绝不误放。
"""
import json
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .config import settings
from .llm import get_llm_client

# ---- 初审规则阈值（集中声明，便于答辩时调参演示） ----
MAX_AUTO_DURATION_HOURS = 3.0   # 自动通过的单次最长时长（小时），超过转人工
EVENING_START_HOUR = 20         # 20:00 之后开始算晚间使用，属边界情况
TEMPORARY_BOOK_HOURS = 2        # 距开始不足 2 小时的"临时预约"，属边界情况
GOOD_CREDIT = 85                # 自动通过建议信用分下限
HIGH_CAPACITY_RATIO = 0.7       # 参与人数超过容量 70%，属边界情况
VAGUE_PURPOSES = {"", "测试", "随便", "用一下", "有事", "其他", "学习", "实验"}

# 明确违规的用途关键词：实验室场景下的安全红线，命中即自动驳回
BANNED_KEYWORDS = [
    "明火", "易燃", "易爆", "危险品", "爆炸物", "电焊", "气焊",
    "赌博", "酗酒", "喝酒", "饮酒", "聚餐", "火锅", "做饭", "烧烤",
    "住宿", "过夜", "睡",
]

APPROVE = "approved"
REJECT = "rejected"
MANUAL = "manual"


class ReviewState(TypedDict):
    """审核图状态：ctx 为预约快照（services 层组装），其余为节点产物。"""
    ctx: dict            # 预约快照（实验室/时段/用途/信用分/容量比…）
    signals: list[str]   # 边界风险信号（中文人话，直接展示给管理员）
    hard_violations: list[str]  # 明确违规项
    decision: str        # "" 表示尚未裁决；approved / rejected / manual
    reasons: list[str]   # 裁决理由（写入 review_note 与站内通知）
    llm_used: bool       # 本次是否调用了大模型复核


# ---------- 节点 1：确定性规则扫描 ----------
def rule_scan(state: ReviewState) -> dict:
    ctx = state["ctx"]
    signals: list[str] = []
    hard: list[str] = []

    purpose = (ctx.get("purpose") or "").strip()

    # 1) 安全红线：用途命中违禁词 → 明确违规
    hit_words = [w for w in BANNED_KEYWORDS if w in purpose]
    if hit_words:
        hard.append(f"用途含实验室禁止事项关键词：{'、'.join(hit_words)}")

    # 2) 时长：超过自动通过上限
    if ctx.get("duration_hours", 0) > MAX_AUTO_DURATION_HOURS:
        signals.append(f"预约时长 {ctx['duration_hours']:.1f} 小时，超过 {MAX_AUTO_DURATION_HOURS:.0f} 小时自动通过上限")

    # 3) 晚间使用
    if ctx.get("start_hour", 0) >= EVENING_START_HOUR:
        signals.append(f"晚间时段使用（{ctx.get('start')} 开始），需管理员确认")

    # 4) 用途模糊：过短或过于笼统
    if len(purpose) < 4 or purpose in VAGUE_PURPOSES:
        signals.append("用途描述过于模糊，需核实真实用途")

    # 5) 信用分偏低
    if ctx.get("credit_score", 100) < GOOD_CREDIT:
        signals.append(f"申请人信用分 {ctx.get('credit_score')}，低于自动通过建议线 {GOOD_CREDIT}")

    # 6) 容量占比过高（团队预约）
    ratio = ctx.get("capacity_ratio") or 0
    if ratio > HIGH_CAPACITY_RATIO:
        signals.append(f"参与人数约占实验室容量 {ratio:.0%}，属大型团队活动")

    # 7) 临时预约
    hbs = ctx.get("hours_before_start")
    if hbs is not None and 0 <= hbs < TEMPORARY_BOOK_HOURS:
        signals.append(f"距开始不足 {TEMPORARY_BOOK_HOURS} 小时的临时预约")

    # 8) 周末使用（部分实验室周末管理收紧，作为边界提示而非禁止）
    if ctx.get("is_weekend"):
        signals.append("周末使用实验室")

    # ---- 裁决：明确违规直接驳回；无信号自动通过；有边界信号交 LLM 复核 ----
    if hard:
        return {"hard_violations": hard, "decision": REJECT,
                "reasons": hard, "signals": signals}
    if not signals:
        return {"hard_violations": [], "signals": [], "decision": APPROVE,
                "reasons": ["时长、用途、信用分均符合自动通过规则"]}
    return {"hard_violations": [], "signals": signals, "decision": "", "reasons": []}


# ---------- 条件边：规则扫描后是否需要大模型复核 ----------
def need_llm_review(state: ReviewState) -> str:
    return "llm_review" if not state["decision"] else END


# ---------- 节点 2：大模型边界复核（用途合规性裁量） ----------
_LLM_PROMPT = """你是高校实验室预约的初审管理员，负责对一条"存在边界风险信号"的预约做用途合规复核。

预约快照：
{ctx}

系统已识别的风险信号：
{signals}

请结合用途判断，输出 JSON（不要输出任何其他内容）：
{{"decision": "approved" | "manual" | "rejected", "reason": "一句中文理由"}}

判定标准：
- approved：用途真实具体、与课程/科研/竞赛等正常教学活动相符，风险信号可接受，可自动通过；
- manual：用途模糊或风险信号需要管理员线下裁量（如晚间大型活动、临时预约），转人工终审；
- reject：用途明显违反实验室安全管理规定（明火、危险品、聚餐娱乐、住宿等）。"""


def _parse_decision(text: str) -> tuple[str, str]:
    """从模型输出中抽取 JSON 裁决；解析失败一律降级 manual。"""
    try:
        match = re.search(r"\{[\s\S]*\}", text or "")
        data = json.loads(match.group(0) if match else text)
        decision = data.get("decision", MANUAL)
        if decision not in (APPROVE, REJECT, MANUAL):
            decision = MANUAL
        reason = str(data.get("reason", "")).strip() or "大模型复核未给出理由"
        return decision, reason
    except Exception:
        return MANUAL, "大模型复核结果无法解析，转人工终审（安全降级）"


def llm_review(state: ReviewState) -> dict:
    try:
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{
                "role": "user",
                "content": _LLM_PROMPT.format(
                    ctx=json.dumps(state["ctx"], ensure_ascii=False, indent=2),
                    signals="\n".join(f"- {s}" for s in state["signals"]),
                ),
            }],
            temperature=0.1,
        )
        text = resp.choices[0].message.content or ""
        decision, reason = _parse_decision(text)
    except Exception as e:
        # LLM 服务不可用：宁转人工，不误判
        decision, reason = MANUAL, f"大模型复核不可用（{e}），转人工终审"
    return {"decision": decision, "reasons": [reason], "llm_used": True}


def build_review_graph():
    """编译审核 Agent 状态图（模块导入时编译一次，全局复用）。"""
    builder = StateGraph(ReviewState)
    builder.add_node("rule_scan", rule_scan)
    builder.add_node("llm_review", llm_review)
    builder.add_edge(START, "rule_scan")
    builder.add_conditional_edges(
        "rule_scan", need_llm_review, {"llm_review": "llm_review", END: END}
    )
    builder.add_edge("llm_review", END)
    return builder.compile()


review_graph = build_review_graph()


def run_review(ctx: dict) -> dict:
    """对外入口：传入预约快照，返回裁决结果。

    返回：{"decision": approved/rejected/manual, "reasons": [...],
           "signals": [...], "llm_used": bool}
    """
    init = {
        "ctx": ctx, "signals": [], "hard_violations": [],
        "decision": "", "reasons": [], "llm_used": False,
    }
    final = review_graph.invoke(init)
    return {
        "decision": final["decision"] or MANUAL,
        "reasons": final.get("reasons") or [],
        "signals": final.get("signals") or [],
        "llm_used": final.get("llm_used", False),
    }
