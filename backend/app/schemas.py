from datetime import datetime, date, time
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, field_validator


# 统一响应
class R(BaseModel):
    code: int = 200
    message: str = "ok"
    data: Optional[object] = None


def ok(data=None, message="ok"):
    return {"code": 200, "message": message, "data": data}


def fail(message, code=400):
    return {"code": code, "message": message, "data": None}


# 用户
class UserBase(BaseModel):
    username: str
    nickname: Optional[str] = ""
    avatar: Optional[str] = ""
    email: Optional[str] = ""


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    credit_score: int = 100
    created_at: Optional[datetime] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# 实验室
class LaboratoryBase(BaseModel):
    name: str
    location: Optional[str] = ""
    capacity: Optional[int] = 0
    open_time: Optional[time] = time(8, 0)
    close_time: Optional[time] = time(22, 0)
    rules: Optional[str] = ""
    status: Optional[str] = "enabled"


class LaboratoryCreate(LaboratoryBase):
    pass


class LaboratoryUpdate(LaboratoryBase):
    pass


class LaboratoryOut(LaboratoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# 设备
class EquipmentBase(BaseModel):
    name: str
    model: Optional[str] = ""
    quantity: Optional[int] = 1
    status: Optional[str] = "available"


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(EquipmentBase):
    pass


class EquipmentOut(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lab_id: int


# 预约
class BookingBase(BaseModel):
    booking_date: date
    start_time: time
    end_time: time
    purpose: Optional[str] = ""


class BookingCreate(BookingBase):
    lab_id: int
    # 团队预约：成员用户名列表（不含预约人本人）
    members: List[str] = []


class BookingUpdate(BaseModel):
    status: Optional[str] = None
    review_note: Optional[str] = None


class BookingReschedule(BaseModel):
    """用户改约请求：所有字段可选，传了什么改什么。"""
    lab_id: Optional[int] = None
    booking_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    purpose: Optional[str] = None
    members: Optional[List[str]] = None


class BookingOut(BookingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    lab_id: int
    status: str
    review_note: Optional[str] = ""
    auto_reviewed: bool = False
    participant_count: int = 1
    # 团队成员用户名。ORM 同名为 BookingMember 对象列表，
    # 用 before 校验器把对象转成用户名，否则 from_attributes 会报 string_type 错误
    members: List[str] = []
    created_at: Optional[datetime] = None
    lab: Optional[LaboratoryOut] = None
    user: Optional[UserOut] = None

    @field_validator("members", mode="before")
    @classmethod
    def _members_to_usernames(cls, value):
        if not value:
            return []
        return [m if isinstance(m, str) else (m.user.username if m.user else "")
                for m in value]


# 设备级预约
class EquipmentBookingCreate(BaseModel):
    equipment_id: int
    booking_date: date
    start_time: time
    end_time: time
    purpose: Optional[str] = ""


class EquipmentBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    equipment_id: int
    booking_date: date
    start_time: time
    end_time: time
    purpose: Optional[str] = ""
    status: str
    created_at: Optional[datetime] = None


# 列表分页包装
class Paged(BaseModel):
    items: List[object]
    total: int
    page: int = 1
    size: int = 20
