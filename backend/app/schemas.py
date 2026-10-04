from datetime import datetime, date, time
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


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


class BookingUpdate(BaseModel):
    status: Optional[str] = None
    review_note: Optional[str] = None


class BookingOut(BookingBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    lab_id: int
    status: str
    review_note: Optional[str] = ""
    created_at: Optional[datetime] = None
    lab: Optional[LaboratoryOut] = None
    user: Optional[UserOut] = None


# 列表分页包装
class Paged(BaseModel):
    items: List[object]
    total: int
    page: int = 1
    size: int = 20
