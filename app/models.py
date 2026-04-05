"""SQLAlchemy ORM models for all five tables."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    timezone = Column(String, default="America/Los_Angeles")
    created_at = Column(DateTime(timezone=True), default=_now)

    students = relationship("Student", back_populates="user", cascade="all, delete-orphan")
    phone_numbers = relationship("PhoneNumber", back_populates="user", cascade="all, delete-orphan")
    schedule = relationship("Schedule", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_name = Column(String, nullable=False)
    school_district = Column(String, default="mdusd")
    # Credentials stored encrypted (Fernet ciphertext as base64 string)
    aeries_email = Column(Text, nullable=False)
    aeries_password = Column(Text, nullable=False)
    school_code = Column(String, nullable=False)
    student_number = Column(String, nullable=False)
    student_id = Column(String, nullable=False)
    last_scrape_at = Column(DateTime(timezone=True), nullable=True)
    last_scrape_status = Column(String, default="pending")  # pending/success/failed
    created_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="students")
    snapshots = relationship("GradeSnapshot", back_populates="student", cascade="all, delete-orphan")


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    phone_number = Column(String, nullable=False)  # E.164 format
    verified = Column(Boolean, default=False)
    verification_code = Column(String, nullable=True)  # 6-digit code
    verification_sent_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="phone_numbers")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    delivery_time = Column(String, default="16:00")  # "HH:MM" 24-hour
    timezone = Column(String, default="America/Los_Angeles")
    enabled = Column(Boolean, default=True)
    # JSON array stored as text, e.g. '["mon","tue","wed","thu","fri"]'
    days_of_week = Column(Text, default='["mon","tue","wed","thu","fri"]')

    user = relationship("User", back_populates="schedule")


class GradeSnapshot(Base):
    __tablename__ = "grade_snapshots"

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    scraped_at = Column(DateTime(timezone=True), default=_now)
    data = Column(Text, nullable=False)         # JSON blob of full gradebook response
    summary_text = Column(Text, nullable=True)  # Human-readable SMS text

    student = relationship("Student", back_populates="snapshots")
