"""Scraper orchestrator: tries smolvm binary, falls back to direct in-process scraping."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_scrape(student: Any, previous_snapshot: list | None = None) -> dict[str, Any]:
    """
    Run a grade scrape for *student*.

    Returns a dict with at minimum:
        { "status": "success"|"error", "grades": [...], "changes": [...],
          "sms_text": "...", "timestamp": float }
    """
    from app.config import settings
    from app import encryption

    aeries_email = encryption.decrypt(student.aeries_email)
    aeries_password = encryption.decrypt(student.aeries_password)

    smolvm_path = Path(os.path.expanduser(settings.SMOLVM_BINARY))
    agent_path = os.path.expanduser(settings.SMOLVM_PACKED_AGENT)

    if smolvm_path.exists():
        return _run_via_smolvm(
            smolvm_path=str(smolvm_path),
            agent_path=agent_path,
            aeries_email=aeries_email,
            aeries_password=aeries_password,
            student_id=student.student_id,
            student_num=student.student_number,
            school_code=student.school_code,
            previous_snapshot=previous_snapshot,
        )

    logger.info("smolvm not found at %s — falling back to direct scrape mode", smolvm_path)
    return _run_direct(
        aeries_email=aeries_email,
        aeries_password=aeries_password,
        student_id=student.student_id,
        student_num=student.student_number,
        school_code=student.school_code,
        student_name=student.student_name,
        previous_snapshot=previous_snapshot,
    )


# ── smolvm path ───────────────────────────────────────────────────────────────

def _run_via_smolvm(
    smolvm_path: str,
    agent_path: str,
    aeries_email: str,
    aeries_password: str,
    student_id: str,
    student_num: str,
    school_code: str,
    previous_snapshot: list | None,
) -> dict[str, Any]:
    prev_json = json.dumps(previous_snapshot or [])

    cmd = [
        smolvm_path,
        "run",
        "-e", f"AERIES_EMAIL={aeries_email}",
        "-e", f"AERIES_PASSWORD={aeries_password}",
        "-e", f"STUDENT_ID={student_id}",
        "-e", f"STUDENT_NUM={student_num}",
        "-e", f"SCHOOL_CODE={school_code}",
        "-e", f"PREVIOUS_SNAPSHOT={prev_json}",
        agent_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.error("smolvm timed out after 30s")
        return {"status": "error", "reason": "timeout"}
    except Exception as exc:
        logger.error("smolvm subprocess error: %s", exc)
        return {"status": "error", "reason": str(exc)}

    if proc.returncode != 0:
        logger.error("smolvm exited %d: %s", proc.returncode, proc.stderr)
        return {"status": "error", "reason": f"exit_code_{proc.returncode}"}

    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse smolvm output: %s", exc)
        return {"status": "error", "reason": "invalid_json_output"}


# ── direct (in-process) path ──────────────────────────────────────────────────

def _run_direct(
    aeries_email: str,
    aeries_password: str,
    student_id: str,
    student_num: str,
    school_code: str,
    student_name: str,
    previous_snapshot: list | None,
) -> dict[str, Any]:
    """Run the scraper logic directly in-process (no VM isolation)."""
    # Add the scraper directory to sys.path so we can import scrape.py
    scraper_dir = Path(__file__).parent.parent.parent / "scraper"
    if str(scraper_dir) not in sys.path:
        sys.path.insert(0, str(scraper_dir))

    try:
        import importlib
        scrape_mod = importlib.import_module("scrape")
    except ImportError as exc:
        logger.error("Could not import scraper/scrape.py: %s", exc)
        return {"status": "error", "reason": "scraper_import_failed"}

    # Temporarily set env vars so the module-level constants are available
    # (the scraper reads from os.environ at function call time via the module globals)
    old_env = {}
    env_overrides = {
        "AERIES_EMAIL": aeries_email,
        "AERIES_PASSWORD": aeries_password,
        "STUDENT_ID": student_id,
        "STUDENT_NUM": student_num,
        "SCHOOL_CODE": school_code,
        "PREVIOUS_SNAPSHOT": json.dumps(previous_snapshot or []),
    }
    for k, v in env_overrides.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        # Reload module to pick up fresh env vars
        importlib.reload(scrape_mod)

        opener, _ = scrape_mod.login_aeries(aeries_email, aeries_password)
        if not opener:
            return {"status": "error", "reason": "login_failed"}

        grades = scrape_mod.scrape_grades(opener, school_code, student_num)
        if not grades:
            return {"status": "error", "reason": "scrape_failed"}

        changes = scrape_mod.diff_grades(grades, previous_snapshot or [])
        sms_text = scrape_mod.format_sms(student_name, changes, grades)

        return {
            "status": "success",
            "student_id": student_id,
            "grades": grades,
            "changes": changes,
            "sms_text": sms_text,
            "timestamp": time.time(),
        }
    except Exception as exc:
        logger.exception("Direct scrape failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
    finally:
        # Restore env
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
