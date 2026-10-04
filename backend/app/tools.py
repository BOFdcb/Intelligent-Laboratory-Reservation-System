"""Agent 可用工具：查实验室 / 查设备 / 查空闲 / 查规则 / 提交预约。"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from .models import Laboratory, Equipment, Booking
from . import rag

ACTIVE_STATUSES = ("pending", "approved")

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_labs",
            "description": "查询所有实验室列表（名称、位置、容量、开放时间、状态）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lab_equipment",
            "description": "查询指定实验室的设备列表",
            "parameters": {
                "type": "object",
                "properties": {"lab_id": {"type": "integer", "description": "实验室ID"}},
                "required": ["lab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "查询某实验室在某天的预约占用情况，判断哪些时段空闲",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_id": {"type": "integer", "description": "实验室ID"},
                    "booking_date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
                },
                "required": ["lab_id", "booking_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rules",
            "description": "检索实验室使用规则、开放时间、预约须知等知识库文档",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索问题"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "为当前用户提交实验室预约（进入待审核状态）。提交前必须已与用户确认实验室、日期、时段、用途。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab_id": {"type": "integer"},
                    "booking_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM"},
                    "end_time": {"type": "string", "description": "HH:MM"},
                    "purpose": {"type": "string", "description": "预约用途"},
                },
                "required": ["lab_id", "booking_date", "start_time", "end_time", "purpose"],
            },
        },
    },
]


def _lab_to_dict(lab: Laboratory) -> dict:
    return {
        "id": lab.id, "name": lab.name, "location": lab.location,
        "capacity": lab.capacity,
        "open_time": lab.open_time.strftime("%H:%M") if lab.open_time else None,
        "close_time": lab.close_time.strftime("%H:%M") if lab.close_time else None,
        "status": lab.status, "rules": lab.rules,
    }


def tool_list_labs(db: Session, **_) -> dict:
    labs = db.query(Laboratory).filter(Laboratory.status == "enabled").order_by(Laboratory.id).all()
    return {"labs": [_lab_to_dict(l) for l in labs]}


def tool_get_lab_equipment(db: Session, lab_id: int, **_) -> dict:
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        return {"error": "实验室不存在"}
    items = db.query(Equipment).filter(Equipment.lab_id == lab_id).all()
    return {
        "lab": _lab_to_dict(lab),
        "equipment": [
            {"id": e.id, "name": e.name, "model": e.model, "quantity": e.quantity, "status": e.status}
            for e in items
        ],
    }


def tool_check_availability(db: Session, lab_id: int, booking_date: str, **_) -> dict:
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        return {"error": "实验室不存在"}
    try:
        d = datetime.strptime(booking_date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "日期格式应为 YYYY-MM-DD"}
    bookings = db.query(Booking).filter(
        Booking.lab_id == lab_id,
        Booking.booking_date == d,
        Booking.status.in_(ACTIVE_STATUSES),
    ).all()
    return {
        "lab": _lab_to_dict(lab),
        "date": booking_date,
        "open_time": lab.open_time.strftime("%H:%M"),
        "close_time": lab.close_time.strftime("%H:%M"),
        "occupied_slots": [
            {"start_time": b.start_time.strftime("%H:%M"), "end_time": b.end_time.strftime("%H:%M"),
             "status": b.status}
            for b in bookings
        ],
    }


def tool_search_rules(db: Session, query: str, **_) -> dict:
    docs = rag.search(query, top_k=3)
    if not docs:
        return {"result": "知识库暂无相关内容（ChromaDB 可能未启动或未入库文档）"}
    return {"documents": docs}


def tool_create_booking(db: Session, user_id: int, lab_id: int, booking_date: str,
                        start_time: str, end_time: str, purpose: str, **_) -> dict:
    lab = db.query(Laboratory).filter(Laboratory.id == lab_id).first()
    if not lab:
        return {"error": "实验室不存在"}
    if lab.status != "enabled":
        return {"error": "实验室已停用"}
    try:
        d = datetime.strptime(booking_date, "%Y-%m-%d").date()
        st = datetime.strptime(start_time, "%H:%M").time()
        et = datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        return {"error": "日期或时间格式不正确（YYYY-MM-DD / HH:MM）"}
    if st >= et:
        return {"error": "开始时间必须早于结束时间"}
    if st < lab.open_time or et > lab.close_time:
        return {"error": f"预约时段超出开放时间（{lab.open_time.strftime('%H:%M')}-{lab.close_time.strftime('%H:%M')}）"}
    conflict = db.query(Booking).filter(
        Booking.lab_id == lab_id,
        Booking.booking_date == d,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_time < et,
        Booking.end_time > st,
    ).first()
    if conflict:
        return {"error": "该时段已被占用，请选择其他时段"}
    booking = Booking(user_id=user_id, lab_id=lab_id, booking_date=d,
                      start_time=st, end_time=et, purpose=purpose, status="pending")
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return {"booking_id": booking.id, "status": "pending", "message": "预约已提交，等待管理员审核"}


TOOL_DISPATCH = {
    "list_labs": tool_list_labs,
    "get_lab_equipment": tool_get_lab_equipment,
    "check_availability": tool_check_availability,
    "search_rules": tool_search_rules,
    "create_booking": tool_create_booking,
}
