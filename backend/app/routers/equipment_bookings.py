"""设备级预约 REST 接口（与 Agent 的 book_equipment 等工具共用 services 规则）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EquipmentBooking, User
from ..schemas import EquipmentBookingCreate, ok
from ..security import get_current_user
from .. import services as svc

router = APIRouter(prefix="/api/equipment-bookings", tags=["设备预约"])


@router.post("")
def create_equipment_booking(payload: EquipmentBookingCreate,
                             db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    try:
        result = svc.book_equipment(
            db, current_user,
            equipment_id=payload.equipment_id,
            booking_date=payload.booking_date.isoformat(),
            start_time=payload.start_time.strftime("%H:%M"),
            end_time=payload.end_time.strftime("%H:%M"),
            purpose=payload.purpose or "",
        )
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"equipment_booking_id": result["equipment_booking_id"]}, result["message"])


@router.get("/mine")
def my_equipment_bookings(status: str = "", db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    q = db.query(EquipmentBooking).filter(EquipmentBooking.user_id == current_user.id)
    if status:
        q = q.filter(EquipmentBooking.status == status)
    rows = q.order_by(EquipmentBooking.id.desc()).limit(50).all()
    return ok({"items": [svc.equipment_booking_to_dict(r) for r in rows],
               "total": len(rows)})


@router.post("/{booking_id}/cancel")
def cancel_equipment_booking(booking_id: int, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    try:
        result = svc.cancel_equipment_booking(db, current_user, booking_id)
    except svc.ServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"credit_score": result["credit_score"]}, result["message"])
