"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import create_tables
from app.services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    create_tables()
    start_scheduler(app)
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(title="Subplot", version="0.1.0", lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── API Routers ───────────────────────────────────────────────────────────────
from app.routers import auth, phones, reports, schedule, students  # noqa: E402

app.include_router(auth.router)
app.include_router(students.router)
app.include_router(phones.router)
app.include_router(schedule.router)
app.include_router(reports.router)


# ── HTML Template Routes ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "signup.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    from app.auth import verify_token
    from app.database import SessionLocal
    from app.models import User
    from jose import JWTError

    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

    try:
        payload = verify_token(token)
        user_id = payload["sub"]
    except (JWTError, Exception):
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"current_user": user, "token": token},
    )


@app.get("/logout")
async def logout_page():
    from fastapi.responses import RedirectResponse as RR
    response = RR("/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response
