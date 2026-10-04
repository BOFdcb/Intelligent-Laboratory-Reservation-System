"""基于 LangGraph 的智能预约 Agent。

图结构（StateGraph）：

    START -> llm(调用大模型) --条件边--> tools(执行工具) --边--> llm ...
                          |
                          +--(无工具调用 / 超轮次)--> END

LangGraph 核心概念对照：
- StateGraph : 状态图，节点之间共享并传递 AgentState
- State      : AgentState，包含 messages(消息列表) / rounds(轮次) / db / user_id
- Node       : llm 节点（大模型决策）、tools 节点（执行工具）
- Edge       : START->llm、tools->llm（固定边）
- Conditional Edge : should_continue，根据最新消息是否含 tool_calls 决定走向
"""
import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from .config import settings
from .llm import get_llm_client
from .tools import TOOLS_SCHEMA, TOOL_DISPATCH

MAX_ROUNDS = 8  # 最多 8 轮工具调用，防死循环


class AgentState(TypedDict):
    """图中流转的状态：节点返回的 dict 会整体更新对应字段。"""

    messages: list[dict]  # OpenAI 格式的对话消息（system/user/assistant/tool）
    rounds: int           # 已执行的 LLM 轮次
    db: Session           # 数据库会话（工具节点使用）
    user_id: int          # 当前用户 ID（create_booking 使用）
    events: list[dict]    # 过程事件（tool_call / tool_result），供 SSE 输出


# ---------- 节点 1：调用大模型（决策下一步） ----------
def llm_node(state: AgentState) -> dict:
    client = get_llm_client()
    resp = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=state["messages"],
        tools=TOOLS_SCHEMA,
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


# ---------- 节点 2：执行工具调用 ----------
def tools_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    new_messages = list(state["messages"])
    events = list(state["events"])
    for tc in last.get("tool_calls") or []:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        func = TOOL_DISPATCH.get(name)
        if not func:
            result = {"error": f"未知工具 {name}"}
        else:
            try:
                result = func(state["db"], user_id=state["user_id"], **args)
            except Exception as e:
                result = {"error": str(e)}
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
    #    之后每个节点的输入、输出都必须是这个结构的（部分）字段。
    builder = StateGraph(AgentState)

    # 2) 注册节点：相当于在流程图上画两个处理框。
    #    参数1是节点名字（字符串），参数2是节点要执行的函数。
    builder.add_node("llm", llm_node)       # "llm"框：调用大模型做决策
    builder.add_node("tools", tools_node)   # "tools"框：执行具体工具

    # 3) 添加固定边：表示无条件、固定的走向。
    #    START 是 LangGraph 内置的虚拟起点，
    #    这行的含义：图一启动，第一个执行的节点一定是 "llm"。
    builder.add_edge(START, "llm")

    # 4) 添加条件边：从 "llm" 出发，走向不是写死的，
    #    而是每次执行完 llm_node 后调用 should_continue(state)，
    #    根据它的返回值动态决定下一站。
    #
    #    第三个参数是「返回值 -> 节点名」的映射表：
    #      should_continue 返回 "tools" → 跳到 "tools" 节点
    #      should_continue 返回 END     → 结束整张图（END 是内置虚拟终点）
    builder.add_conditional_edges(
        "llm", should_continue, {"tools": "tools", END: END}
    )

    # 5) 再加一条固定边：工具执行完后，无条件回到 "llm"。
    #    这样大模型才能看到工具结果，决定下一步是继续调工具还是给最终答复。
    #    （llm → tools → llm → tools ... 的循环就是这样形成的）
    builder.add_edge("tools", "llm")

    # 6) compile：把上面"画"好的图编译成可执行对象。
    #    编译后会校验图的合法性（比如节点是否都连通），
    #    返回的对象提供 .invoke() / .stream() 等方法供外部驱动。
    return builder.compile()


# 模块加载时就把图编译好一次，之后所有请求共用这一个对象。
# 为什么能共用？因为图本身不存任何用户数据——
# 每次请求的对话消息、db 会话、用户 ID 都放在调用时传入的 AgentState 里，
# 图只是一张固定的"流程图模板"。
agent_graph = build_agent_graph()
