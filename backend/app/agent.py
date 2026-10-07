"""基于 LangGraph 的智能预约 Agent。

图结构（StateGraph）：

    START -> llm(调用大模型) --条件边--> tools(执行工具) --边--> llm ...
                          |
                          +--(无工具调用 / 超轮次)--> END

LangGraph 核心概念对照：
- StateGraph : 状态图，节点之间共享并传递 AgentState
- State      : AgentState，包含 messages/rounds/db/user/events
- Node       : llm 节点（大模型决策）、tools 节点（执行工具）
- Edge       : START->llm、tools->llm（固定边）
- Conditional Edge : should_continue，根据最新消息是否含 tool_calls 决定走向

安全治理（D）：
- llm 节点按当前用户角色下发工具声明（学生看不到管理员工具）；
- tools 节点执行前二次校验角色（双保险，防止提示词注入诱导越权）；
- 每次工具调用写 tool_audit_logs 审计日志。
"""
import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from .config import settings
from .llm import get_llm_client
from .models import ToolAuditLog, User
from .tools import TOOL_DISPATCH, is_tool_allowed, schemas_for_role

MAX_ROUNDS = 8  # 最多 8 轮工具调用，防死循环
AUDIT_RESULT_LIMIT = 1000  # 审计日志结果摘要最大字符数


class AgentState(TypedDict):
    """图中流转的状态：节点返回的 dict 会整体更新对应字段。"""

    messages: list[dict]  # OpenAI 格式的对话消息（system/user/assistant/tool）
    rounds: int           # 已执行的 LLM 轮次
    db: Session           # 数据库会话（工具节点使用）
    user: User            # 当前用户 ORM 对象（工具读取 id/role/信用分）
    events: list[dict]    # 过程事件（tool_call / tool_result），供 SSE 输出


# ---------- 节点 1：调用大模型（决策下一步） ----------
def llm_node(state: AgentState) -> dict:
    client = get_llm_client()
    # 按角色裁剪工具列表：学生请求里不会出现任何管理员工具的声明
    tools_schema = schemas_for_role(state["user"].role)
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=state["messages"],
        tools=tools_schema,
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    assistant = {"role": "assistant", "content": msg.content or ""}
    events: list[dict] = []
    if msg.tool_calls:
        assistant["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
        for tc in assistant["tool_calls"]:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            events.append({"type": "tool_call", "name": tc["function"]["name"], "arguments": args})
    return {
        "messages": state["messages"] + [assistant],
        "rounds": state["rounds"] + 1,
        "events": state["events"] + events,
    }


def _write_audit_log(db: Session, user: User, tool_name: str, args: dict,
                     result: dict, success: bool) -> None:
    """审计日志落库。日志失败不能影响主流程，故吞掉异常。"""
    try:
        summary = result.get("error") if not success and isinstance(result, dict) else json.dumps(
            result, ensure_ascii=False
        )
        db.add(ToolAuditLog(
            user_id=user.id, username=user.username, role=user.role,
            tool_name=tool_name,
            arguments_json=json.dumps(args, ensure_ascii=False)[:AUDIT_RESULT_LIMIT],
            success=success,
            result_summary=(summary or "")[:AUDIT_RESULT_LIMIT],
        ))
        db.commit()
    except Exception:
        db.rollback()


# ---------- 节点 2：执行工具调用 ----------
def tools_node(state: AgentState) -> dict:
    user = state["user"]
    db = state["db"]
    last = state["messages"][-1]
    new_messages = list(state["messages"])
    events = list(state["events"])
    for tc in last.get("tool_calls") or []:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}

        # 越权拦截：即使模型（或被提示词注入）下发了越权工具，也在执行层拒绝
        if not is_tool_allowed(name, user.role):
            result = {"error": f"权限不足：工具 {name} 仅管理员可用"}
            _write_audit_log(db, user, name, args, result, success=False)
        else:
            func = TOOL_DISPATCH.get(name)
            if not func:
                result = {"error": f"未知工具 {name}"}
                _write_audit_log(db, user, name, args, result, success=False)
            else:
                try:
                    result = func(db, user=user, **args)
                    # 工具返回 error 视为业务失败（如冲突、频率限制），审计标红
                    _write_audit_log(db, user, name, args, result,
                                     success=not (isinstance(result, dict) and "error" in result))
                except Exception as e:
                    result = {"error": str(e)}
                    _write_audit_log(db, user, name, args, result, success=False)

        new_messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(result, ensure_ascii=False),
        })
        events.append({"type": "tool_result", "name": name, "result": result})
    return {"messages": new_messages, "events": events}


# ---------- 条件边：是否需要执行工具 ----------
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if last.get("tool_calls") and state["rounds"] < MAX_ROUNDS:
        return "tools"
    return END


def build_agent_graph():
    """构建并编译预约 Agent 状态图。

    可以类比为「画流程图」：先声明有哪些处理框（节点），
    再用线（边）把它们连起来，最后编译成一台可执行的机器。
    """
    # 1) 创建一张空的状态图，并指定图里流转的数据结构是 AgentState。
    builder = StateGraph(AgentState)

    # 2) 注册节点
    builder.add_node("llm", llm_node)       # "llm"框：调用大模型做决策
    builder.add_node("tools", tools_node)   # "tools"框：执行具体工具

    # 3) 固定边 START -> llm
    builder.add_edge(START, "llm")

    # 4) 条件边：llm 执行完由 should_continue 决定去 tools 还是 END
    builder.add_conditional_edges(
        "llm", should_continue, {"tools": "tools", END: END}
    )

    # 5) 固定边 tools -> llm（llm → tools → llm ... 的循环）
    builder.add_edge("tools", "llm")

    # 6) compile：校验图的合法性并生成可执行对象
    return builder.compile()


# 模块加载时就把图编译好一次，之后所有请求共用这一个对象。
# 图本身不存任何用户数据——每次请求的消息、db 会话、用户对象都在
# 调用时传入的 AgentState 里，图只是一张固定的"流程图模板"。
agent_graph = build_agent_graph()
