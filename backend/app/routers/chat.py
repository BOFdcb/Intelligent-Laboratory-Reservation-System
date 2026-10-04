import json
from datetime import date
from typing import Generator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agent import agent_graph
from ..database import get_db
from ..llm import get_llm_client
from ..models import User
from ..rag import search as rag_search
from ..schemas import ok
from ..security import get_current_user
from ..config import settings

router = APIRouter(prefix="/api/chat", tags=["AI助手"])

# 会话历史（内存存储，重启清空）
_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 20


class ChatRequest(BaseModel):
    message: str
    use_rag: bool = True


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _get_history(user_id: int) -> list[dict]:
    return _histories.setdefault(user_id, [])


def _trim(history: list[dict]):
    del history[:-MAX_HISTORY]


# ---------- 普通对话（SSE 流式 + RAG） ----------
@router.post("")
def chat(payload: ChatRequest, db: Session = Depends(get_db),
         current_user: User = Depends(get_current_user)):
    history = _get_history(current_user.id)

    rag_context = ""
    if payload.use_rag:
        docs = rag_search(payload.message, top_k=3)
        if docs:
            rag_context = "\n\n".join(f"【资料{i+1}】{d}" for i, d in enumerate(docs))

    system = (
        f"你是{settings.APP_NAME}的智能助手，负责解答实验室使用相关问题。"
        f"今天是 {date.today().isoformat()}。回答简洁准确。"
    )
    if rag_context:
        system += f"\n\n以下是与问题相关的参考资料，请优先依据资料回答：\n{rag_context}"

    messages = [{"role": "system", "content": system}] + history + [
        {"role": "user", "content": payload.message}
    ]

    def stream() -> Generator[str, None, None]:
        yield _sse({"type": "thinking", "content": "正在思考..."})
        answer_parts = []
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(
                model=settings.LLM_MODEL, messages=messages, stream=True,
            )
            for chunk in resp:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    answer_parts.append(delta.content)
                    yield _sse({"type": "answer", "content": delta.content})
        except Exception as e:
            yield _sse({"type": "error", "content": f"大模型调用失败: {e}"})
            yield _sse({"type": "done"})
            return
        answer = "".join(answer_parts)
        history.append({"role": "user", "content": payload.message})
        history.append({"role": "assistant", "content": answer})
        _trim(history)
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------- 智能预约 Agent（LangGraph 状态图 + SSE 过程节点可见） ----------
AGENT_SYSTEM = """你是智能实验室预约助手。今天是 {today}。

你可以使用工具查询实验室、设备、空闲时段、使用规则，并帮助用户提交预约。

工作流程：
1. 理解用户意图。若用户想预约但信息不全（缺实验室/日期/时段/用途），请追问澄清。
2. 预约前先用 check_availability 查询目标时段是否空闲；若冲突，建议其他时段。
3. 信息齐全后，先向用户复述预约信息请其确认，得到肯定答复后再调用 create_booking。
4. 规则类问题用 search_rules 检索。
5. 所有回复使用中文，简洁友好。"""


@router.post("/agent")
def chat_agent(payload: ChatRequest, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """智能预约 Agent 接口（SSE 流式，过程节点可见）。

    与上面的 chat()（普通对话）不同：
    - 普通对话：直接调大模型，一次性流式输出回答；
    - Agent 接口：把请求交给 LangGraph 状态图（agent_graph），
      由图自动决定要不要调工具、调几次，最终再把答案流式返回。
    """
    # 取当前用户的 Agent 会话历史，用负 ID 作为 key，
    # 是为了和普通对话（key=user.id）隔离开，互不干扰。
    history_key = -current_user.id
    history = _get_history(history_key)

    # 组装发往大模型的消息列表：
    #   [系统提示词] + [历史对话] + [本次用户消息]
    # AGENT_SYSTEM 是给大模型的"人设与工作流程"，告诉它如何预约。
    system = AGENT_SYSTEM.format(today=date.today().isoformat())
    messages = [{"role": "system", "content": system}] + history + [
        {"role": "user", "content": payload.message}
    ]

    def stream() -> Generator[str, None, None]:
        """生成器函数：每 yield 一个 _sse(...) 就向前端推一段 SSE 数据。

        关键点：调用 agent_graph.stream(state, stream_mode="updates")，
        它会按节点执行状态图，每执行完一个节点就 yield 一次该节点的状态更新，
        我们把这些更新转成 SSE 事件发给前端，前端就能实时看到
        "思考中 → 调用工具 → 工具结果 → 最终回答"的全过程。
        """
        # 1) 构造 Agent 初始状态（对应 agent.py 的 AgentState）：
        #    messages 是对话内容，rounds 计数，db/user_id 供工具节点用，
        #    events 用来收集过程事件（tool_call / tool_result）。
        state = {
            "messages": messages,
            "rounds": 0,
            "db": db,
            "user_id": current_user.id,
            "events": [],
        }
        answer = ""
        # 游标：events 是"只增"列表（每次工具调用只追加，不删旧的）。
        # 我们只需要把本轮新产生的事件发给前端，
        # 所以用游标记住上一次发到第几条，下一次只发游标之后的部分。
        event_cursor = 0
        final_state = None
        try:
            # 进入图之前先发一个"思考中"提示
            yield _sse({"type": "thinking", "content": "思考中（第1轮）..."})

            # 2) 驱动状态图：stream_mode="updates" 表示按节点产出更新。
            #    每执行完一个节点（llm 或 tools），这里就会拿到一次 update。
            #    update 的结构：{ 节点名: 该节点执行后返回的状态片段 }
            for update in agent_graph.stream(state, stream_mode="updates"):
                # 取出本次更新对应的节点名和它的状态
                node_name, node_state = next(iter(update.items()))

                # 3) 把该节点新产生的过程事件（tool_call / tool_result）推给前端
                events = node_state.get("events") or []
                for ev in events[event_cursor:]:   # 只发新增的
                    yield _sse(ev)
                event_cursor = max(event_cursor, len(events))

                # 4) 如果本次执行的是 tools 节点，说明工具刚跑完，
                #    接下来要把结果回喂给大模型再决策一轮，所以提示"继续思考"。
                if node_name == "tools":
                    yield _sse({"type": "thinking", "content": "思考中..."})

                # 记住最新状态，用于循环结束后取最终回答
                final_state = node_state

        except Exception as e:
            # 图执行中途出错（比如大模型调用失败），发错误事件并结束流
            yield _sse({"type": "error", "content": f"Agent 运行失败: {e}"})
            yield _sse({"type": "done"})
            return

        # 5) 图跑完后，最后一条 assistant 消息的 content 就是最终回答
        if final_state:
            answer = final_state["messages"][-1].get("content") or ""
        if answer:
            yield _sse({"type": "answer", "content": answer})

        # 6) 把本轮问答追加到历史（下次请求会作为上下文），并裁剪到 MAX_HISTORY
        history.append({"role": "user", "content": payload.message})
        history.append({"role": "assistant", "content": answer})
        _trim(history)

        # 7) 告诉前端本次回答已完成
        yield _sse({"type": "done"})

    # 把生成器包装成 SSE 响应，FastAPI 会边执行边推流
    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/history")
def chat_history(current_user: User = Depends(get_current_user)):
    return ok({
        "chat": _get_history(current_user.id),
        "agent": _get_history(-current_user.id),
    })
