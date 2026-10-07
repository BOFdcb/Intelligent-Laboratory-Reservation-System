"""数据分析 Agent（B-数据分析 Agent）：自然语言 -> 图表化运营建议。

与"规则问答型 RAG"差异化的关键：它能对业务数据库做**动态聚合计算**。
图结构：

    START -> parse(大模型解析问题为结构化指标)
                 |
                 v
             compute(确定性 SQL 聚合，零注入、可复现)
                 |
                 v
             summarize(大模型基于真实数字生成中文洞察与建议) -> END

安全设计：
- parse 节点输出被白名单约束（metric/range 枚举），任何越界值回退默认值；
- compute 节点不执行模型生成的 SQL，只在固定的指标函数中选择，杜绝 SQL 注入；
- 大模型节点失败时图仍可返回 charts（图表不依赖模型），洞察文本降级为提示语。
"""
import json
import re
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from . import analytics
from .config import settings
from .llm import get_llm_client

METRICS = ("overview", "lab_usage", "hot_slots", "daily_trend", "status_distribution")
RANGES = ("today", "this_week", "last_week", "this_month", "last_7_days", "last_30_days")

PARSE_PROMPT = """今天是 {today}。把管理员的数据分析问题解析成查询参数，只输出 JSON：
{{"metric": "overview|lab_usage|hot_slots|daily_trend|status_distribution",
  "range": "today|this_week|last_week|this_month|last_7_days|last_30_days"}}

指标映射：
- overview：综合/整体/看板/概况类问题
- lab_usage：哪个实验室最忙/最热门、使用率、使用时长、实验室排名
- hot_slots：热门时段、几点钟用得最多、高峰时间
- daily_trend：每天/最近几天预约量趋势、哪天最多
- status_distribution：通过率、取消率、待审核数量、状态占比、爽约率
范围映射：今天=today；本周/这周=this_week；上周=last_week；本月=this_month；
最近一周/近7天=last_7_days；近30天/最近一个月=last_30_days。无法判断时默认 overview + this_week。"""

SUMMARY_PROMPT = """你是高校实验室运营分析助手。以下是系统按管理员问题计算出的真实统计结果（JSON）：

{result}

请输出 3-5 条中文运营洞察，每条一行、用"• "开头。要求：
1. 必须基于上面的真实数字，不得编造；
2. 先讲发现的现象（最忙实验室、高峰时段、通过率/取消率等），再给可执行建议
   （如引导错峰、增加热门实验室开放、关注待审核积压、降低爽约率）；
3. 语言简洁，不要输出 JSON 或 markdown 表格。"""


class AnalyticsState(TypedDict):
    question: str
    db: Session
    today: str
    plan: dict           # 解析出的 metric/range
    result: dict         # compute 节点产物（charts + facts）
    summary: str         # 大模型洞察文本


# ---------- 节点 1：解析自然语言问题 ----------
def parse_node(state: AnalyticsState) -> dict:
    metric, range_key = "overview", "this_week"
    try:
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user",
                       "content": PARSE_PROMPT.format(today=state["today"])}
                      , {"role": "user", "content": state["question"]}],
            temperature=0.0,
        )
        text = resp.choices[0].message.content or ""
        match = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(match.group(0) if match else text)
        if data.get("metric") in METRICS:
            metric = data["metric"]
        if data.get("range") in RANGES:
            range_key = data["range"]
    except Exception:
        # 解析失败用默认值，保证图表仍能出
        pass
    return {"plan": {"metric": metric, "range": range_key}}


# ---------- 节点 2：确定性聚合计算（不执行模型生成的 SQL） ----------
def compute_node(state: AnalyticsState) -> dict:
    today = date.fromisoformat(state["today"])
    result = analytics.compute_stats(
        state["db"],
        metric=state["plan"]["metric"],
        range_key=state["plan"]["range"],
        today=today,
    )
    return {"result": result}


# ---------- 节点 3：基于真实数字生成洞察 ----------
def summarize_node(state: AnalyticsState) -> dict:
    # facts 体积小、信息密度高，只把 facts + 范围喂给模型，避免 token 浪费
    payload = {
        "range": state["result"]["range"],
        "facts": state["result"]["facts"],
    }
    try:
        resp = get_llm_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user",
                       "content": SUMMARY_PROMPT.format(
                           result=json.dumps(payload, ensure_ascii=False, indent=2))}],
            temperature=0.3,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        summary = f"（洞察生成失败：{e}，图表数据仍可参考）"
    return {"summary": summary}


def build_analytics_graph():
    builder = StateGraph(AnalyticsState)
    builder.add_node("parse", parse_node)
    builder.add_node("compute", compute_node)
    builder.add_node("summarize", summarize_node)
    builder.add_edge(START, "parse")
    builder.add_edge("parse", "compute")
    builder.add_edge("compute", "summarize")
    builder.add_edge("summarize", END)
    return builder.compile()


analytics_graph = build_analytics_graph()


def run_analytics(db: Session, question: str) -> dict:
    """同步入口（供 Agent 工具复用）：返回 charts/facts/summary 完整结构。"""
    init = {
        "question": question, "db": db, "today": date.today().isoformat(),
        "plan": {}, "result": {}, "summary": "",
    }
    final = analytics_graph.invoke(init)
    return {"plan": final["plan"], "result": final["result"],
            "summary": final["summary"]}
