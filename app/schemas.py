"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    timezone: str = "America/Los_Angeles"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    timezone: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Students ──────────────────────────────────────────────────────────────────

class StudentCreate(BaseModel):
    student_name: str
    school_district: str = "mdusd"
    aeries_email: str
    aeries_password: str
    school_code: str
    student_number: str
    student_id: str


class StudentResponse(BaseModel):
    id: str
    user_id: str
    student_name: str
    school_district: str
    school_code: str
    student_number: str
    student_id: str
    last_scrape_at: datetime | None
    last_scrape_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


# ── Phone Numbers ─────────────────────────────────────────────────────────────

class PhoneNumberCreate(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def must_be_e164(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("+"):
            raise ValueError("Phone number must be in E.164 format (e.g. +15551234567)")
        return v


class PhoneVerifyRequest(BaseModel):
    phone_number: str
    code: str


class PhoneNumberResponse(BaseModel):
    id: str
    user_id: str
    phone_number: str
    verified: bool
    verification_sent_at: datetime | None

    model_config = {"from_attributes": True}


# ── Schedule ──────────────────────────────────────────────────────────────────

class ScheduleUpdate(BaseModel):
    delivery_time: str = "16:00"       # "HH:MM"
    timezone: str = "America/Los_Angeles"
    days_of_week: list[str] = ["mon", "tue", "wed", "thu", "fri"]
    enabled: bool = True

    @field_validator("delivery_time")
    @classmethod
    def must_be_hhmm(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("delivery_time must be HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("delivery_time hours 0-23, minutes 0-59")
        return v

    @field_validator("days_of_week")
    @classmethod
    def must_be_valid_days(cls, v: list[str]) -> list[str]:
        valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        for d in v:
            if d not in valid:
                raise ValueError(f"Invalid day: {d}. Use mon/tue/wed/thu/fri/sat/sun")
        return v


class ScheduleResponse(BaseModel):
    id: str
    user_id: str
    delivery_time: str
    timezone: str
    enabled: bool
    days_of_week: list[str]

    model_config = {"from_attributes": True}


# ── Reports ───────────────────────────────────────────────────────────────────

class GradeSnapshotResponse(BaseModel):
    id: str
    student_id: str
    scraped_at: datetime
    summary_text: str | None
    data: Any  # parsed JSON

    model_config = {"from_attributes": True}
