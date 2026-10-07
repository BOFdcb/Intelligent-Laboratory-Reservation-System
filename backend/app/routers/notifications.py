"""站内消息路由（B-定时提醒 / 人机协同结果触达）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..schemas import ok
from ..security import get_current_user
from .. import services as svc

router = APIRouter(prefix="/api/notifications", tags=["站内消息"])


@router.get("")
def my_notifications(unread_only: bool = False, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    items = svc.list_notifications(db, current_user, unread_only=unread_only)
    return ok({"items": items})


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).count()
    return ok({"count": count})


@router.post("/{notification_id}/read")
def read_one(notification_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    try:
        svc.mark_notification_read(db, current_user, notification_id)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(None, "已读")


@router.post("/read-all")
def read_all(db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    count = svc.mark_all_read(db, current_user)
    return ok({"updated": count}, f"已全部已读（{count} 条）")
