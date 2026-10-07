from datetime import datetime, date, time

from sqlalchemy import (
    Column, Integer, String, Text, Date, Time, DateTime, ForeignKey, UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="student")  # student / admin
    nickname = Column(String(64), default="")
    avatar = Column(String(255), default="")
    email = Column(String(128), default="")
    # 信用分（D-防放鸽子）：初始 100，临近开始取消等行为扣分，低于阈值禁止新预约
    credit_score = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime, default=datetime.now)

    bookings = relationship("Booking", back_populates="user")
    booking_members = relationship("BookingMember", back_populates="user",
                                   cascade="all, delete-orphan")
    equipment_bookings = relationship("EquipmentBooking", back_populates="user")
    notifications = relationship("Notification", back_populates="user",
                                 cascade="all, delete-orphan")


class Laboratory(Base):
    __tablename__ = "laboratories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    location = Column(String(255), default="")
    capacity = Column(Integer, default=0)
    open_time = Column(Time, default=time(8, 0))
    close_time = Column(Time, default=time(22, 0))
    rules = Column(Text, default="")
    status = Column(String(16), default="enabled")  # enabled / disabled

    equipment = relationship("Equipment", back_populates="lab", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="lab")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lab_id = Column(Integer, ForeignKey("laboratories.id"), nullable=False)
    name = Column(String(128), nullable=False)
    model = Column(String(128), default="")
    quantity = Column(Integer, default=1)
    status = Column(String(16), default="available")  # available / maintenance

    lab = relationship("Laboratory", back_populates="equipment")
    reservations = relationship("EquipmentBooking", back_populates="equipment",
                                cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint(
            "lab_id", "booking_date", "start_time", "end_time",
            name="uq_lab_slot",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lab_id = Column(Integer, ForeignKey("laboratories.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    purpose = Column(String(255), default="")
    # pending（待人工终审）/ approved（已通过待签到）/ rejected（驳回）
    # / cancelled（用户取消）/ confirmed（已签到使用中）/ used（已完成）
    # / released（超时未确认，系统自动释放）
    status = Column(String(16), nullable=False, default="pending")
    review_note = Column(String(255), default="")
    # 团队预约：参与总人数（含预约人本人），用于实验室容量校验
    participant_count = Column(Integer, nullable=False, default=1)
    # B-人机协同：是否由审核 Agent 直接给出终局结论（自动通过/自动驳回）
    auto_reviewed = Column(Boolean, nullable=False, default=False)
    # B-定时提醒：开始前提醒、待审核催办的去重标记
    reminder_sent = Column(Boolean, nullable=False, default=False)
    urge_sent = Column(Boolean, nullable=False, default=False)
    # B-签到确认：用户到场签到时间；未签到超时由调度器自动释放
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="bookings")
    lab = relationship("Laboratory", back_populates="bookings")
    members = relationship("BookingMember", back_populates="booking",
                           cascade="all, delete-orphan")


class BookingMember(Base):
    """团队预约成员表：一条记录代表"某用户加入了某预约"。"""
    __tablename__ = "booking_members"
    __table_args__ = (
        UniqueConstraint("booking_id", "user_id", name="uq_booking_member"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    booking = relationship("Booking", back_populates="members")
    user = relationship("User", back_populates="booking_members")


class EquipmentBooking(Base):
    """设备级预约：设备数量 >1 时，允许同一时段存在不超过 quantity 条有效预约。"""
    __tablename__ = "equipment_bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    purpose = Column(String(255), default="")
    # active / cancelled
    status = Column(String(16), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="equipment_bookings")
    equipment = relationship("Equipment", back_populates="reservations")


class ToolAuditLog(Base):
    """Agent 工具调用审计日志（D-安全治理）：谁、在什么时候、以什么角色、
    调用了哪个工具、传了什么参数、是否成功。"""
    __tablename__ = "tool_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    username = Column(String(64), default="")
    role = Column(String(16), default="student")
    tool_name = Column(String(64), nullable=False, index=True)
    arguments_json = Column(Text, default="{}")
    success = Column(Boolean, default=True)
    # 结果摘要：失败时存 error，成功时截断后的 JSON，避免日志无限膨胀
    result_summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now, index=True)


class Notification(Base):
    """站内消息（B-定时提醒 / 人机协同）。

    覆盖场景：审核结果通知、预约开始前提醒、待审核催办（发给管理员）、
    超时未确认自动释放通知。前端轮询拉取并支持单条/全部已读。
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # booking_result / reminder / urge / system
    category = Column(String(32), nullable=False, default="system")
    title = Column(String(128), nullable=False, default="")
    content = Column(String(500), default="")
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    # 关联预约 ID（前端点击可跳转），无关联时为空
    related_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", back_populates="notifications")
