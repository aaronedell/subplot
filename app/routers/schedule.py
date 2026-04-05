"""Delivery schedule routes."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app.database import get_db
from app.models import Schedule, User
from app.schemas import ScheduleResponse, ScheduleUpdate

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


def _schedule_to_response(s: Schedule) -> ScheduleResponse:
    days = json.loads(s.days_of_week) if isinstance(s.days_of_week, str) else s.days_of_week
    return ScheduleResponse(
        id=s.id,
        user_id=s.user_id,
        delivery_time=s.delivery_time,
        timezone=s.timezone,
        enabled=s.enabled,
        days_of_week=days,
    )


@router.get("", response_model=ScheduleResponse)
def get_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.user_id == current_user.id).first()
    if not schedule:
        # Return a default (not persisted yet)
        return ScheduleResponse(
            id="",
            user_id=current_user.id,
            delivery_time="16:00",
            timezone=current_user.timezone,
            enabled=True,
            days_of_week=["mon", "tue", "wed", "thu", "fri"],
        )
    return _schedule_to_response(schedule)


@router.put("", response_model=ScheduleResponse)
def upsert_schedule(
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    schedule = db.query(Schedule).filter(Schedule.user_id == current_user.id).first()
    if not schedule:
        schedule = Schedule(user_id=current_user.id)
        db.add(schedule)

    schedule.delivery_time = body.delivery_time
    schedule.timezone = body.timezone
    schedule.enabled = body.enabled
    schedule.days_of_week = json.dumps(body.days_of_week)

    db.commit()
    db.refresh(schedule)
    return _schedule_to_response(schedule)
