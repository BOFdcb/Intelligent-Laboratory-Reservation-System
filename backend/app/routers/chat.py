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
ADMIN_CLAUSE = (
    "\n9. 你是管理员助手：用户要求查看待审核列表、通过/驳回预约时，"
    "使用 admin_list_bookings / admin_approve_booking / admin_reject_booking；"
    "驳回前询问驳回原因。执行审批前向管理员确认预约ID与申请人。"
    "\n10. 运营数据分析（如“这周哪个实验室最忙”“热门时段”“通过率/取消率”）"
    "使用 query_booking_stats，依据返回的 facts 数字用中文给出结论与建议，不要编造数字；"
    "图表化看板可引导管理员前往「数据分析」页面。"
)

STUDENT_CLAUSE = (
    "\n9. 到场签到：用户说“签到/确认到场”时用 confirm_booking（开始前后15分钟内有效），"
    "并提醒超时未签到会被自动释放并扣信用分。"
)

AGENT_SYSTEM = """你是智能实验室预约助手。今天是 {today}。当前用户角色：{role}（用户名 {username}，信用分 {credit}）。

你可以通过工具完成：实验室/设备查询、空闲查询与冲突替代推荐、提交预约（含团队预约）、
查询我的预约及审核进度、取消预约、改约、到场签到，以及设备级预约。

人机协同审核机制（重要）：
- 用户提交预约后，系统先由"审核 Agent"做规则初审：合规预约会被自动通过，
  明确违规会被自动驳回，边界情况（超长时段、晚间、用途模糊、信用分偏低、大型团队等）
  转交管理员人工终审；审核结果会以站内消息通知用户。
- 因此 create_booking 返回 status 可能是 approved（自动通过）/ rejected（自动驳回）
  / pending（转人工），请如实把结果与原因转告用户，不要承诺"一定通过"。

工作流程：
1. 理解用户意图。信息不全（缺实验室/日期/时段/用途/设备）时先追问澄清，不要臆造 ID。
2. 预约实验室前先用带 start_time/end_time 的 check_availability 查询；
   若返回 requested_slot_free=false，依据 suggestions 主动给出"同实验室其他时段"
   或"同时段其他实验室"供用户选择，不要只回复"被占用了"。
3. 信息齐全后先向用户复述预约信息（团队预约要复述成员名单），得到肯定答复后再调用
   create_booking / book_equipment。取消、改约、签到等敏感操作同样要先确认。
4. 用户问"我的预约/审核到哪了"用 list_my_bookings；问设备预约用
   list_my_equipment_bookings。改约用 update_booking（已通过的预约改后会重新审核）。
5. 团队预约：members 传成员"用户名"列表（不含本人），系统会校验成员是否存在与实验室容量。
6. 规则类问题用 search_rules 检索。
7. 工具返回 error（如时段冲突、信用分不足、超出频率上限、不在签到窗口）时，用通俗的话
   解释原因，并给出可行的替代建议，不要原样抛英文错误。
8. 所有回复使用中文，简洁友好。
{admin_clause}{student_clause}"""


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
    # AGENT_SYSTEM 是给大模型的"人设与工作流程"，告诉它如何预约；
    # 管理员额外注入审批工具的使用指引。
    system = AGENT_SYSTEM.format(
        today=date.today().isoformat(),
        role="管理员" if current_user.role == "admin" else "学生",
        username=current_user.username,
        credit=current_user.credit_score,
        admin_clause=ADMIN_CLAUSE if current_user.role == "admin" else "",
        student_clause="" if current_user.role == "admin" else STUDENT_CLAUSE,
    )
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
        #    messages 是对话内容，rounds 计数，db/user 供工具节点用，
        #    events 用来收集过程事件（tool_call / tool_result）。
        state = {
            "messages": messages,
            "rounds": 0,
            "db": db,
            "user": current_user,
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
