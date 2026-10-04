from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Booking, Laboratory, User
from ..schemas import BookingCreate, BookingOut, ok
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/bookings", tags=["预约"])

ACTIVE_STATUSES = ("pending", "approved")


def _check_conflict(db: Session, lab_id: int, booking_date: date, start_time, end_time, exclude_id=None):
    q = db.query(Booking).filter(
        Booking.lab_id == lab_id,
        Booking.booking_date == booking_date,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_time < end_time,
        Booking.end_time > start_time,
    )
    if exclude_id:
        q = q.filter(Booking.id != exclude_id)
    return q.first()


@router.post("")
def create_booking(payload: BookingCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    lab = db.query(Laboratory).filter(Laboratory.id == payload.lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="实验室不存在")
    if lab.status != "enabled":
        raise HTTPException(status_code=400, detail="实验室已停用")
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")
    if payload.start_time < lab.open_time or payload.end_time > lab.close_time:
        raise HTTPException(status_code=400, detail="预约时段超出实验室开放时间")
    if _check_conflict(db, payload.lab_id, payload.booking_date, payload.start_time, payload.end_time):
        raise HTTPException(status_code=400, detail="该时段已被占用，请选择其他时段")

    booking = Booking(user_id=current_user.id, status="pending", **payload.model_dump())
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return ok(BookingOut.model_validate(booking).model_dump(mode="json"), "预约已提交，等待审核")


@router.get("/mine")
def my_bookings(page: int = 1, size: int = 20, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = (db.query(Booking).options(joinedload(Booking.lab))
         .filter(Booking.user_id == current_user.id)
         .order_by(Booking.id.desc()))
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [BookingOut.model_validate(b).model_dump(mode="json") for b in items],
        "total": total, "page": page, "size": size,
    })


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能取消本人的预约")
    if booking.status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="当前状态不可取消")
    booking.status = "cancelled"
    db.commit()
    return ok(None, "已取消")


# ---- 管理员 ----
@router.get("")
def list_bookings(page: int = 1, size: int = 20, status: str = "",
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = (db.query(Booking).options(joinedload(Booking.lab), joinedload(Booking.user))
         .order_by(Booking.id.desc()))
    if status:
        q = q.filter(Booking.status == status)
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return ok({
        "items": [BookingOut.model_validate(b).model_dump(mode="json") for b in items],
        "total": total, "page": page, "size": size,
    })


@router.post("/{booking_id}/approve")
def approve_booking(booking_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    if booking.status != "pending":
        raise HTTPException(status_code=400, detail="仅待审核预约可审核")
    # 审批前再校验一次时段冲突（防止并发/重复审批导致超卖）
    if _check_conflict(db, booking.lab_id, booking.booking_date,
                       booking.start_time, booking.end_time, exclude_id=booking.id):
        raise HTTPException(status_code=400, detail="该时段已被其他已通过预约占用")
    booking.status = "approved"
    db.commit()
    return ok(None, "已通过")


@router.post("/{booking_id}/reject")
def reject_booking(booking_id: int, payload: dict = None, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="预约不存在")
    if booking.status != "pending":
        raise HTTPException(status_code=400, detail="仅待审核预约可审核")
    booking.status = "rejected"
    booking.review_note = (payload or {}).get("review_note", "")
    db.commit()
    return ok(None, "已驳回")
