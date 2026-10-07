"""管理员治理接口：Agent 工具调用审计日志（D）、定时任务手动触发（B）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ToolAuditLog, User
from ..schemas import ok
from ..security import require_admin
from .. import services as svc

router = APIRouter(prefix="/api/admin", tags=["管理治理"])


@router.get("/audit-logs")
def list_audit_logs(page: int = 1, size: int = 20, tool_name: str = "",
                    user_id: int = 0, success: str = "",
                    db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    """分页查询 Agent 工具调用审计日志，可按工具名/用户/是否成功过滤。"""
    q = db.query(ToolAuditLog).order_by(ToolAuditLog.id.desc())
    if tool_name:
        q = q.filter(ToolAuditLog.tool_name == tool_name)
    if user_id:
        q = q.filter(ToolAuditLog.user_id == user_id)
    if success in ("true", "false"):
        q = q.filter(ToolAuditLog.success == (success == "true"))
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "username": r.username,
                "role": r.role,
                "tool_name": r.tool_name,
                "arguments": r.arguments_json,
                "success": r.success,
                "result_summary": r.result_summary,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
            }
            for r in rows
        ],
        "total": total, "page": page, "size": size,
    })


@router.post("/scheduler/run")
def run_scheduler(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """立即执行一次全部定时任务（开始前提醒 / 待审催办 / 超时释放），用于演示与巡检。"""
    result = svc.run_scheduled_jobs(db)
    return ok(result, f"定时任务执行完成：{result}")
