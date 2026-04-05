"""Grade report routes."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app.database import get_db
from app.models import GradeSnapshot, Student, User
from app.schemas import GradeSnapshotResponse
from app.services import scraper as scraper_service
from app.services.report_builder import build_report
from app.services.sms import get_sms_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _snapshot_to_response(snap: GradeSnapshot) -> GradeSnapshotResponse:
    try:
        data = json.loads(snap.data)
    except Exception:
        data = []
    return GradeSnapshotResponse(
        id=snap.id,
        student_id=snap.student_id,
        scraped_at=snap.scraped_at,
        summary_text=snap.summary_text,
        data=data,
    )


def _get_user_student_ids(db: Session, user: User) -> list[str]:
    students = db.query(Student).filter(Student.user_id == user.id).all()
    return [s.id for s in students]


@router.get("", response_model=list[GradeSnapshotResponse])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    student_ids = _get_user_student_ids(db, current_user)
    if not student_ids:
        return []
    snapshots = (
        db.query(GradeSnapshot)
        .filter(GradeSnapshot.student_id.in_(student_ids))
        .order_by(GradeSnapshot.scraped_at.desc())
        .limit(20)
        .all()
    )
    return [_snapshot_to_response(s) for s in snapshots]


@router.get("/latest", response_model=GradeSnapshotResponse | None)
def latest_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    student_ids = _get_user_student_ids(db, current_user)
    if not student_ids:
        return None
    snap = (
        db.query(GradeSnapshot)
        .filter(GradeSnapshot.student_id.in_(student_ids))
        .order_by(GradeSnapshot.scraped_at.desc())
        .first()
    )
    return _snapshot_to_response(snap) if snap else None


@router.post("/send-now", status_code=status.HTTP_202_ACCEPTED)
def send_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    """Trigger an immediate scrape for all of the current user's students and send SMS."""
    students = db.query(Student).filter(Student.user_id == current_user.id).all()
    if not students:
        raise HTTPException(status_code=400, detail="No students configured")

    from app.models import PhoneNumber
    phones = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.user_id == current_user.id, PhoneNumber.verified == True)
        .all()
    )

    sms = get_sms_service()
    results = []

    for student in students:
        # Get previous snapshot for diff
        prev_snap = (
            db.query(GradeSnapshot)
            .filter(GradeSnapshot.student_id == student.id)
            .order_by(GradeSnapshot.scraped_at.desc())
            .first()
        )
        prev_data = None
        if prev_snap:
            try:
                prev_data = json.loads(prev_snap.data)
            except Exception:
                prev_data = None

        try:
            result = scraper_service.run_scrape(student, previous_snapshot=prev_data)
        except Exception as exc:
            results.append({"student": student.student_name, "status": "error", "detail": str(exc)})
            continue

        if result.get("status") != "success":
            student.last_scrape_at = datetime.now(timezone.utc)
            student.last_scrape_status = "failed"
            db.commit()
            results.append({"student": student.student_name, "status": "failed"})
            continue

        grades = result.get("grades", [])
        changes = result.get("changes", [])
        summary = build_report(student.student_name, grades, prev_data)

        # Persist snapshot
        snapshot = GradeSnapshot(
            student_id=student.id,
            scraped_at=datetime.now(timezone.utc),
            data=json.dumps(grades),
            summary_text=summary,
        )
        db.add(snapshot)
        student.last_scrape_at = datetime.now(timezone.utc)
        student.last_scrape_status = "success"
        db.commit()

        # Send SMS to all verified phones
        for phone in phones:
            sms.send_message(phone.phone_number, summary)

        results.append({"student": student.student_name, "status": "success", "changes": len(changes)})

    return {"results": results}
