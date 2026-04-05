"""Tests for student CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app

client = TestClient(app, raise_server_exceptions=True)

# Sample student payload
STUDENT_PAYLOAD = {
    "student_name": "Emma",
    "school_district": "mdusd",
    "aeries_email": "parent@example.com",
    "aeries_password": "secret123",
    "school_code": "001",
    "student_number": "123456",
    "student_id": "789",
}


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import app.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    db_mod.engine = engine
    db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    from app.database import create_tables
    create_tables()
    yield


@pytest.fixture
def auth_headers():
    """Signup a user and return Authorization headers."""
    res = client.post(
        "/api/auth/signup",
        json={"email": "parent@test.com", "password": "password123"},
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAddStudent:
    def test_add_student_returns_201(self, auth_headers):
        res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        assert data["student_name"] == "Emma"
        assert data["school_code"] == "001"
        assert "id" in data

    def test_add_student_requires_auth(self):
        res = client.post("/api/students", json=STUDENT_PAYLOAD)
        assert res.status_code == 401

    def test_add_student_encrypts_credentials(self, auth_headers):
        """Credentials should not appear as plaintext in the response."""
        res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        assert res.status_code == 201
        data = res.json()
        # The response schema omits credentials entirely
        assert "aeries_email" not in data
        assert "aeries_password" not in data


class TestListStudents:
    def test_list_empty_initially(self, auth_headers):
        res = client.get("/api/students", headers=auth_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_shows_added_student(self, auth_headers):
        client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        res = client.get("/api/students", headers=auth_headers)
        assert res.status_code == 200
        students = res.json()
        assert len(students) == 1
        assert students[0]["student_name"] == "Emma"

    def test_users_cannot_see_each_others_students(self, auth_headers):
        # Add student as user 1
        client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)

        # Sign up as user 2
        res2 = client.post(
            "/api/auth/signup",
            json={"email": "other@test.com", "password": "password123"},
        )
        token2 = res2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        res = client.get("/api/students", headers=headers2)
        assert res.status_code == 200
        assert res.json() == []


class TestDeleteStudent:
    def test_delete_student(self, auth_headers):
        add_res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        student_id = add_res.json()["id"]

        del_res = client.delete(f"/api/students/{student_id}", headers=auth_headers)
        assert del_res.status_code == 204

        list_res = client.get("/api/students", headers=auth_headers)
        assert list_res.json() == []

    def test_delete_nonexistent_returns_404(self, auth_headers):
        res = client.delete("/api/students/nonexistent-id", headers=auth_headers)
        assert res.status_code == 404

    def test_cannot_delete_other_users_student(self, auth_headers):
        add_res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        student_id = add_res.json()["id"]

        # Different user
        res2 = client.post(
            "/api/auth/signup",
            json={"email": "attacker@test.com", "password": "password123"},
        )
        token2 = res2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        del_res = client.delete(f"/api/students/{student_id}", headers=headers2)
        assert del_res.status_code == 404


class TestTestConnection:
    def test_test_connection_returns_success_when_scrape_ok(self, auth_headers):
        add_res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        student_id = add_res.json()["id"]

        mock_result = {
            "status": "success",
            "grades": [{"CourseName": "Math", "CurrentMark": "A", "CurrentMarkPercent": 95}],
            "changes": [],
            "sms_text": "📋 Emma Daily Grades:\n  Math: A (95%)",
            "timestamp": 1234567890.0,
        }

        with patch("app.services.scraper.run_scrape", return_value=mock_result):
            res = client.post(
                f"/api/students/{student_id}/test-connection", headers=auth_headers
            )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "1 courses" in data["message"]

    def test_test_connection_returns_failure_on_bad_creds(self, auth_headers):
        add_res = client.post("/api/students", json=STUDENT_PAYLOAD, headers=auth_headers)
        student_id = add_res.json()["id"]

        mock_result = {"status": "error", "reason": "login_failed"}

        with patch("app.services.scraper.run_scrape", return_value=mock_result):
            res = client.post(
                f"/api/students/{student_id}/test-connection", headers=auth_headers
            )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
