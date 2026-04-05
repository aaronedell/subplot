"""Student CRUD routes."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app import encryption
from app.database import get_db
from app.models import Student, User
from app.schemas import StudentCreate, StudentResponse, TestConnectionResponse
from app.services import scraper as scraper_service

router = APIRouter(prefix="/api/students", tags=["students"])


@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def add_student(
    body: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    student = Student(
        user_id=current_user.id,
        student_name=body.student_name,
        school_district=body.school_district,
        aeries_email=encryption.encrypt(body.aeries_email),
        aeries_password=encryption.encrypt(body.aeries_password),
        school_code=body.school_code,
        student_number=body.student_number,
        student_id=body.student_id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("", response_model=list[StudentResponse])
def list_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    return db.query(Student).filter(Student.user_id == current_user.id).all()


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    student = db.query(Student).filter(
        Student.id == student_id, Student.user_id == current_user.id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    db.delete(student)
    db.commit()


@router.post("/{student_id}/test-connection", response_model=TestConnectionResponse)
def test_connection(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_lib.get_current_user),
):
    student = db.query(Student).filter(
        Student.id == student_id, Student.user_id == current_user.id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    try:
        result = scraper_service.run_scrape(student)
        if result.get("status") == "success":
            # Update last scrape info
            student.last_scrape_at = datetime.now(timezone.utc)
            student.last_scrape_status = "success"
            db.commit()
            return TestConnectionResponse(
                success=True,
                message=f"Connected successfully. Found {len(result.get('grades', []))} courses.",
            )
        else:
            reason = result.get("reason", "unknown error")
            student.last_scrape_at = datetime.now(timezone.utc)
            student.last_scrape_status = "failed"
            db.commit()
            return TestConnectionResponse(success=False, message=f"Scrape failed: {reason}")
    except Exception as exc:
        student.last_scrape_at = datetime.now(timezone.utc)
        student.last_scrape_status = "failed"
        db.commit()
        return TestConnectionResponse(success=False, message=str(exc))
