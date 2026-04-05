"""APScheduler background scheduler for automated grade report delivery."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def start_scheduler(app=None) -> None:
    """Create and start the background scheduler. Call once on app startup."""
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running — skipping start")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _check_and_send,
        trigger="interval",
        minutes=1,
        id="grade_delivery",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started — checking every minute for scheduled deliveries")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


def _check_and_send() -> None:
    """Minute-tick job: find schedules due right now and dispatch scrape + SMS."""
    try:
        _do_check_and_send()
    except Exception:
        logger.exception("Unhandled error in scheduler job")


def _do_check_and_send() -> None:
    from app.database import SessionLocal
    from app.models import GradeSnapshot, PhoneNumber, Schedule, Student
    from app.services import scraper as scraper_service
    from app.services.report_builder import build_report
    from app.services.sms import get_sms_service

    db = SessionLocal()
    try:
        schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
        if not schedules:
            return

        now_utc = datetime.now(timezone.utc)

        for sched in schedules:
            try:
                tz = pytz.timezone(sched.timezone)
            except pytz.UnknownTimeZoneError:
                logger.warning("Unknown timezone %s for schedule %s", sched.timezone, sched.id)
                continue

            now_local = now_utc.astimezone(tz)
            current_hhmm = now_local.strftime("%H:%M")
            current_day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now_local.weekday()]

            try:
                days = json.loads(sched.days_of_week) if isinstance(sched.days_of_week, str) else sched.days_of_week
            except Exception:
                days = []

            if current_hhmm != sched.delivery_time or current_day not in days:
                continue

            logger.info(
                "Schedule %s matched for user %s at %s %s",
                sched.id, sched.user_id, current_hhmm, current_day,
            )

            students = db.query(Student).filter(Student.user_id == sched.user_id).all()
            phones = (
                db.query(PhoneNumber)
                .filter(PhoneNumber.user_id == sched.user_id, PhoneNumber.verified == True)
                .all()
            )

            if not students:
                logger.info("User %s has no students — skipping", sched.user_id)
                continue
            if not phones:
                logger.info("User %s has no verified phones — skipping", sched.user_id)
                continue

            sms = get_sms_service()

            for student in students:
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
                    logger.error("Scrape failed for student %s: %s", student.id, exc)
                    continue

                if result.get("status") != "success":
                    logger.warning("Scrape returned non-success for student %s: %s", student.id, result)
                    student.last_scrape_at = datetime.now(timezone.utc)
                    student.last_scrape_status = "failed"
                    db.commit()
                    continue

                grades = result.get("grades", [])
                summary = build_report(student.student_name, grades, prev_data)

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

                for phone in phones:
                    try:
                        sms.send_message(phone.phone_number, summary)
                    except Exception as exc:
                        logger.error("SMS send failed to %s: %s", phone.phone_number, exc)

    finally:
        db.close()
