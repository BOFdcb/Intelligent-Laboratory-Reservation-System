"""数据分析 Agent 路由（B-数据分析 Agent）：自然语言提问 -> SSE 推送图表与洞察。"""
import json
from datetime import date
from typing import Generator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..analytics_agent import analytics_graph
from ..database import get_db
from ..models import User
from ..security import require_admin

router = APIRouter(prefix="/api/admin/analytics", tags=["数据分析Agent"])


class AnalyticsRequest(BaseModel):
    question: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/ask")
def ask_analytics(payload: AnalyticsRequest, db: Session = Depends(get_db),
                  _: User = Depends(require_admin)):
    """驱动数据分析状态图，按节点把 解析计划/图表数据/文字洞察 推给前端。"""
    question = (payload.question or "").strip()

    def stream() -> Generator[str, None, None]:
        if not question:
            yield _sse({"type": "error", "content": "请输入要分析的问题"})
            yield _sse({"type": "done"})
            return

        state = {
            "question": question, "db": db, "today": date.today().isoformat(),
            "plan": {}, "result": {}, "summary": "",
        }
        yield _sse({"type": "thinking", "content": "数据分析 Agent 正在解析问题…"})
        try:
            for update in analytics_graph.stream(state, stream_mode="updates"):
                node_name, node_state = next(iter(update.items()))
                if node_name == "parse" and node_state.get("plan"):
                    yield _sse({"type": "plan", "plan": node_state["plan"]})
                    yield _sse({"type": "thinking",
                                "content": "正在查询数据库并计算指标…"})
                elif node_name == "compute" and node_state.get("result"):
                    result = node_state["result"]
                    yield _sse({
                        "type": "charts",
                        "range": result["range"],
                        "charts": result["charts"],
                        "facts": result["facts"],
                    })
                    yield _sse({"type": "thinking", "content": "正在生成运营洞察…"})
                elif node_name == "summarize":
                    yield _sse({"type": "summary",
                                "content": node_state.get("summary", "")})
        except Exception as e:
            yield _sse({"type": "error", "content": f"数据分析失败: {e}"})
        yield _sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
