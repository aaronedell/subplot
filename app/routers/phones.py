"""Phone number management: add, verify, list, delete."""
import random
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app.database import get_db
from app.models import PhoneNumber, User
from app.schemas import PhoneNumberCreate, PhoneNumberResponse, PhoneVerifyRequest
from app.services.sms import get_sms_service

router = APIRouter(prefix="/api/phone-numbers", tags=["phones"])


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


@router.post("", response_model=PhoneNumberResponse, status_code=status.HTTP_201_CREATED)
def add_phone_number(
    body: PhoneNumberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    # Check for duplicate (same user, same number)
    existing = db.query(PhoneNumber).filter(
        PhoneNumber.user_id == current_user.id,
        PhoneNumber.phone_number == body.phone_number,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already added")

    code = _generate_code()
    phone = PhoneNumber(
        user_id=current_user.id,
        phone_number=body.phone_number,
        verified=False,
        verification_code=code,
        verification_sent_at=datetime.now(timezone.utc),
    )
    db.add(phone)
    db.commit()
    db.refresh(phone)

    # Send verification SMS
    sms = get_sms_service()
    sms.send_verification_code(body.phone_number, code)

    return phone


@router.post("/verify", response_model=PhoneNumberResponse)
def verify_phone_number(
    body: PhoneVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    phone = db.query(PhoneNumber).filter(
        PhoneNumber.user_id == current_user.id,
        PhoneNumber.phone_number == body.phone_number,
    ).first()
    if not phone:
        raise HTTPException(status_code=404, detail="Phone number not found")
    if phone.verified:
        return phone
    if phone.verification_code != body.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    phone.verified = True
    phone.verification_code = None
    db.commit()
    db.refresh(phone)
    return phone


@router.get("", response_model=list[PhoneNumberResponse])
def list_phone_numbers(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    return db.query(PhoneNumber).filter(PhoneNumber.user_id == current_user.id).all()


@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phone_number(
    phone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    phone = db.query(PhoneNumber).filter(
        PhoneNumber.id == phone_id,
        PhoneNumber.user_id == current_user.id,
    ).first()
    if not phone:
        raise HTTPException(status_code=404, detail="Phone number not found")
    db.delete(phone)
    db.commit()
