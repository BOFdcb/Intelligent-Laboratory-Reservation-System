from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Booking, BookingMember, User
from ..schemas import (
    BookingCreate, BookingOut, BookingReschedule, ok,
)
from ..security import get_current_user, require_admin
from .. import services as svc

router = APIRouter(prefix="/api/bookings", tags=["预约"])


def _to_out(b: Booking) -> dict:
    """ORM -> 前端结构；members 的 BookingMember->用户名转换由
    BookingOut 的 field_validator 自动完成。"""
    return BookingOut.model_validate(b).model_dump(mode="json")


@router.post("")
def create_booking(payload: BookingCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    try:
        result = svc.create_lab_booking(
            db, current_user,
            lab_id=payload.lab_id,
            booking_date=payload.booking_date.isoformat(),
            start_time=payload.start_time.strftime("%H:%M"),
            end_time=payload.end_time.strftime("%H:%M"),
            purpose=payload.purpose or "",
            members=payload.members,
        )
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"booking_id": result["booking_id"],
               "participant_count": result["participant_count"]},
              result["message"])


@router.put("/{booking_id}")
def reschedule_booking(booking_id: int, payload: BookingReschedule,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """用户改约：改时间/实验室/用途/团队成员；已通过的预约改后重新审核。"""
    changes = payload.model_dump(exclude_none=True)
    if "booking_date" in changes:
        changes["booking_date"] = changes["booking_date"].isoformat()
    for key in ("start_time", "end_time"):
        if key in changes:
            changes[key] = changes[key].strftime("%H:%M")
    try:
        result = svc.update_lab_booking(db, current_user, booking_id, **changes)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"booking_id": result["booking_id"], "status": result["status"]},
              result["message"])


@router.get("/mine")
def my_bookings(page: int = 1, size: int = 20, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = (db.query(Booking).options(
            joinedload(Booking.lab),
            joinedload(Booking.members).joinedload(BookingMember.user))
         .filter(Booking.user_id == current_user.id)
         .order_by(Booking.id.desc()))
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [_to_out(b) for b in items],
        "total": total, "page": page, "size": size,
    })


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    try:
        result = svc.cancel_lab_booking(db, current_user, booking_id)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"credit_score": result["credit_score"]}, result["message"])


@router.post("/{booking_id}/confirm")
def confirm_booking(booking_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """到场签到（B-人机协同）：开始前后 15 分钟内确认使用。"""
    try:
        result = svc.confirm_booking_usage(db, current_user, booking_id)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"booking_id": result["booking_id"], "status": result["status"]},
              result["message"])


# ---- 管理员 ----
@router.get("")
def list_bookings(page: int = 1, size: int = 20, status: str = "",
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = (db.query(Booking).options(
            joinedload(Booking.lab), joinedload(Booking.user),
            joinedload(Booking.members).joinedload(BookingMember.user))
         .order_by(Booking.id.desc()))
    if status:
        q = q.filter(Booking.status == status)
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [_to_out(b) for b in items],
        "total": total, "page": page, "size": size,
    })


@router.post("/{booking_id}/approve")
def approve_booking(booking_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    try:
        result = svc.approve_booking(db, booking_id)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(None, result["message"])


@router.post("/{booking_id}/reject")
def reject_booking(booking_id: int, payload: dict = None, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    note = (payload or {}).get("review_note", "")
    try:
        result = svc.reject_booking(db, booking_id, review_note=note)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(None, result["message"])
