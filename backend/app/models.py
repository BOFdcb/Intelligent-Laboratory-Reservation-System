from datetime import datetime, date, time

from sqlalchemy import (
    Column, Integer, String, Text, Date, Time, DateTime, ForeignKey, UniqueConstraint,
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
    created_at = Column(DateTime, default=datetime.now)

    bookings = relationship("Booking", back_populates="user")


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
    # pending / approved / rejected / cancelled / used
    status = Column(String(16), nullable=False, default="pending")
    review_note = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="bookings")
    lab = relationship("Laboratory", back_populates="bookings")
