"""Tests for signup, login, and authentication flows."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Point the database at a temp file so tests don't share state."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Re-initialize the engine/session for the temp path
    import app.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    db_mod.engine = engine
    db_mod.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.database import create_tables
    create_tables()
    yield


def _signup(email="test@example.com", password="password123", timezone="America/Los_Angeles"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "timezone": timezone},
    )


def _login(email="test@example.com", password="password123"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSignup:
    def test_signup_creates_user_and_returns_token(self):
        res = _signup()
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_signup_duplicate_email_fails(self):
        _signup()
        res = _signup()
        assert res.status_code == 400
        assert "already registered" in res.json()["detail"].lower()

    def test_signup_stores_timezone(self):
        res = _signup(timezone="America/New_York")
        assert res.status_code == 201
        token = res.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["timezone"] == "America/New_York"


class TestLogin:
    def test_login_returns_token(self):
        _signup()
        res = _login()
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data

    def test_login_wrong_password_fails(self):
        _signup()
        res = _login(password="wrongpassword")
        assert res.status_code == 401

    def test_login_unknown_email_fails(self):
        res = _login(email="nobody@example.com")
        assert res.status_code == 401

    def test_login_token_is_valid_for_me_endpoint(self):
        _signup(email="user@test.com")
        res = _login(email="user@test.com")
        token = res.json()["access_token"]

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "user@test.com"


class TestAuthRequired:
    def test_me_requires_token(self):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_invalid_token_rejected(self):
        res = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert res.status_code == 401
