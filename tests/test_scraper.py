"""Tests for scraper logic: diff_grades, format_sms, and output parsing."""
import json
import sys
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure scraper/ is on sys.path so we can import scrape directly
SCRAPER_DIR = Path(__file__).parent.parent / "scraper"
sys.path.insert(0, str(SCRAPER_DIR))

import scrape  # noqa: E402 — scraper/scrape.py


# ── Fixtures ──────────────────────────────────────────────────────────────────

COURSES_A = [
    {"CourseName": "Math", "CurrentMark": "A", "CurrentMarkPercent": 95},
    {"CourseName": "English", "CurrentMark": "B+", "CurrentMarkPercent": 87},
    {"CourseName": "History", "CurrentMark": "A-", "CurrentMarkPercent": 92},
]

COURSES_B = [
    # Math grade dropped
    {"CourseName": "Math", "CurrentMark": "B+", "CurrentMarkPercent": 88},
    # English grade improved
    {"CourseName": "English", "CurrentMark": "A-", "CurrentMarkPercent": 91},
    # History unchanged
    {"CourseName": "History", "CurrentMark": "A-", "CurrentMarkPercent": 92},
]


# ── diff_grades ────────────────────────────────────────────────────────────────

class TestDiffGrades:
    def test_no_changes_returns_empty_list(self):
        changes = scrape.diff_grades(COURSES_A, COURSES_A)
        assert changes == []

    def test_detects_grade_drop(self):
        changes = scrape.diff_grades(COURSES_B, COURSES_A)
        math_change = next(c for c in changes if c["course"] == "Math")
        assert math_change["direction"] == "down"
        assert "A" in math_change["old_grade"]
        assert "B+" in math_change["new_grade"]

    def test_detects_grade_increase(self):
        changes = scrape.diff_grades(COURSES_B, COURSES_A)
        eng_change = next(c for c in changes if c["course"] == "English")
        assert eng_change["direction"] == "up"

    def test_unchanged_course_not_in_changes(self):
        changes = scrape.diff_grades(COURSES_B, COURSES_A)
        history_changes = [c for c in changes if c["course"] == "History"]
        assert history_changes == []

    def test_new_course_detected(self):
        new_course = COURSES_A + [{"CourseName": "Art", "CurrentMark": "A", "CurrentMarkPercent": 98}]
        changes = scrape.diff_grades(new_course, COURSES_A)
        art_change = next((c for c in changes if c["course"] == "Art"), None)
        assert art_change is not None
        assert art_change["direction"] == "new"

    def test_previous_as_json_string(self):
        """diff_grades should accept a JSON string for previous."""
        changes = scrape.diff_grades(COURSES_B, json.dumps(COURSES_A))
        assert len(changes) == 2  # Math and English changed

    def test_empty_previous_marks_all_new(self):
        changes = scrape.diff_grades(COURSES_A, [])
        assert len(changes) == 3
        for c in changes:
            assert c["direction"] == "new"

    def test_empty_current_returns_empty(self):
        changes = scrape.diff_grades([], COURSES_A)
        assert changes == []


# ── format_sms ────────────────────────────────────────────────────────────────

class TestFormatSms:
    def test_daily_summary_when_no_changes(self):
        msg = scrape.format_sms("Emma", [], COURSES_A)
        assert "📋" in msg
        assert "Emma" in msg
        assert "Daily Grades" in msg
        assert "Math" in msg
        assert "English" in msg

    def test_update_message_when_changes(self):
        changes = scrape.diff_grades(COURSES_B, COURSES_A)
        msg = scrape.format_sms("Emma", changes, COURSES_B)
        assert "📚" in msg
        assert "Grade Update" in msg
        assert "Emma" in msg

    def test_up_arrow_for_improvement(self):
        up_change = [{"course": "Math", "old_grade": "B (80%)", "new_grade": "A (95%)", "direction": "up"}]
        msg = scrape.format_sms("Jake", up_change, COURSES_A)
        assert "📈" in msg

    def test_down_arrow_for_drop(self):
        down_change = [{"course": "Math", "old_grade": "A (95%)", "new_grade": "B (80%)", "direction": "down"}]
        msg = scrape.format_sms("Jake", down_change, COURSES_A)
        assert "📉" in msg

    def test_new_course_emoji(self):
        new_change = [{"course": "Art", "new_grade": "A (98%)", "direction": "new"}]
        msg = scrape.format_sms("Jake", new_change, COURSES_A)
        assert "🆕" in msg

    def test_format_includes_arrow_separator_for_changes(self):
        changes = scrape.diff_grades(COURSES_B, COURSES_A)
        msg = scrape.format_sms("Emma", changes, COURSES_B)
        # Should have old → new format for grade changes
        assert "→" in msg


# ── Scraper output parsing ────────────────────────────────────────────────────

class TestScraperOutputParsing:
    """Test that the orchestrator correctly parses scraper subprocess output."""

    def test_success_output_parsed(self):
        """Simulate valid JSON on stdout and verify parsing."""
        expected = {
            "status": "success",
            "student_id": "789",
            "grades": COURSES_A,
            "changes": [],
            "sms_text": "📋 Emma Daily Grades:\n  Math: A (95%)",
            "timestamp": 1234567890.0,
        }
        stdout_bytes = (json.dumps(expected) + "\n").encode()
        result = json.loads(stdout_bytes.decode().strip())
        assert result["status"] == "success"
        assert len(result["grades"]) == 3

    def test_error_output_parsed(self):
        error_output = json.dumps({"status": "error", "reason": "login_failed"})
        result = json.loads(error_output)
        assert result["status"] == "error"
        assert result["reason"] == "login_failed"

    def test_run_scrape_via_smolvm_success(self):
        """Test that run_scrape correctly handles a mocked smolvm subprocess call."""
        from app.services import scraper as scraper_service

        mock_output = json.dumps({
            "status": "success",
            "student_id": "789",
            "grades": COURSES_A,
            "changes": [],
            "sms_text": "📋 Daily",
            "timestamp": 1234567890.0,
        })

        mock_student = MagicMock()
        mock_student.student_id = "789"
        mock_student.student_number = "123456"
        mock_student.school_code = "001"
        mock_student.student_name = "Emma"
        # Encrypt with a real Fernet key so decrypt works
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        f = Fernet(key)
        mock_student.aeries_email = f.encrypt(b"parent@example.com").decode()
        mock_student.aeries_password = f.encrypt(b"secret").decode()

        with patch.dict(os.environ, {"SUBPLOT_ENCRYPTION_KEY": key.decode()}):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout=mock_output,
                        stderr="",
                    )
                    result = scraper_service.run_scrape(mock_student)

        assert result["status"] == "success"
        assert len(result["grades"]) == 3

    def test_run_scrape_timeout_returns_error(self):
        """Test that a timeout returns an error dict rather than raising."""
        from app.services import scraper as scraper_service

        mock_student = MagicMock()
        mock_student.student_id = "789"
        mock_student.student_number = "123456"
        mock_student.school_code = "001"
        mock_student.student_name = "Emma"
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        f = Fernet(key)
        mock_student.aeries_email = f.encrypt(b"parent@example.com").decode()
        mock_student.aeries_password = f.encrypt(b"secret").decode()

        with patch.dict(os.environ, {"SUBPLOT_ENCRYPTION_KEY": key.decode()}):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="smolvm", timeout=30)):
                    result = scraper_service.run_scrape(mock_student)

        assert result["status"] == "error"
        assert result["reason"] == "timeout"


# ── Log output goes to stderr, not stdout ─────────────────────────────────────

class TestLogOutput:
    def test_log_writes_to_stderr_not_stdout(self, capsys):
        scrape.log("test message")
        captured = capsys.readouterr()
        assert captured.out == ""  # nothing on stdout
        assert "test message" in captured.err

    def test_log_is_valid_json(self, capsys):
        scrape.log("hello world")
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed["msg"] == "hello world"
        assert "ts" in parsed
