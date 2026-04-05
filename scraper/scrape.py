#!/usr/bin/env python3
"""
Subplot Scraper Agent — runs inside a SmolVM or directly in-process.

Flow:
1. Boot VM with customer config (injected via env vars)
2. Log into Aeries parent portal
3. Scrape gradebook summary via API
4. Compare to previous snapshot (if provided)
5. Write structured JSON result to STDOUT (captured by orchestrator)
6. All log/diagnostic output goes to STDERR only

Env vars consumed:
    AERIES_URL            Base URL, default https://mtdiablousd.aeries.net
    AERIES_EMAIL          Parent portal email
    AERIES_PASSWORD       Parent portal password
    STUDENT_ID            Aeries student ID
    STUDENT_NUM           Student number (for API params)
    SCHOOL_CODE           School code (for API params)
    PREVIOUS_SNAPSHOT     JSON string of prior gradebook (for diff), default "{}"
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

# ── Configuration from env vars ───────────────────────────────────────────────

AERIES_URL = os.environ.get("AERIES_URL", "https://mtdiablousd.aeries.net")
AERIES_EMAIL = os.environ.get("AERIES_EMAIL", "")
AERIES_PASSWORD = os.environ.get("AERIES_PASSWORD", "")
STUDENT_ID = os.environ.get("STUDENT_ID", "")
STUDENT_NUM = os.environ.get("STUDENT_NUM", "")
SCHOOL_CODE = os.environ.get("SCHOOL_CODE", "")
PREVIOUS_SNAPSHOT = os.environ.get("PREVIOUS_SNAPSHOT", "[]")


# ── Logging to STDERR (never stdout — that's reserved for the result JSON) ────

def log(msg: str) -> None:
    """Structured log to stderr so the orchestrator can separate it from stdout JSON."""
    print(json.dumps({"ts": time.time(), "msg": msg}), file=sys.stderr, flush=True)


# ── Aeries login ──────────────────────────────────────────────────────────────

def login_aeries(email: str, password: str):
    """
    Authenticate to the Aeries parent portal.

    Returns (opener, cookiejar) on success, or (None, None) on failure.
    The opener is a urllib OpenerDirector with a persistent CookieJar attached.
    """
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    login_url = f"{AERIES_URL}/student/LoginParent.aspx"
    log(f"Fetching login page: {login_url}")

    try:
        resp = opener.open(login_url)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log(f"ERROR: Could not fetch login page: {exc}")
        return None, None

    # Extract CSRF token
    token_match = re.search(
        r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html
    )
    if not token_match:
        # Try alternate attribute order
        token_match = re.search(
            r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', html
        )
    if not token_match:
        log("ERROR: Could not find __RequestVerificationToken CSRF token in login page")
        return None, None

    csrf_token = token_match.group(1)
    log("CSRF token extracted")

    # POST credentials
    post_data = urllib.parse.urlencode(
        {
            "__RequestVerificationToken": csrf_token,
            "porlogin_Email": email,
            "porlogin_Password": password,
            "porlogin_RememberMe": "false",
        }
    ).encode("utf-8")

    req = urllib.request.Request(login_url, data=post_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", login_url)

    try:
        resp = opener.open(req)
        _ = resp.read()  # consume response body
    except Exception as exc:
        log(f"ERROR: Login POST failed: {exc}")
        return None, None

    log("Login POST submitted successfully")
    return opener, cj


# ── Grade scraping ────────────────────────────────────────────────────────────

def scrape_grades(opener, school_code: str, student_num: str):
    """
    Fetch the gradebook summary from Aeries mobile API.

    Returns a list of course dicts or None on failure.
    Each dict typically contains: CourseName, CurrentMark, CurrentMarkPercent, etc.
    """
    api_url = (
        f"{AERIES_URL}/student/m/api/MobileViewJSON/GetGradebookSummary"
        f"?s={urllib.parse.quote(school_code)}&n={urllib.parse.quote(student_num)}"
    )
    log(f"Fetching grades: {api_url}")

    req = urllib.request.Request(api_url)
    req.add_header("Accept", "application/json")
    req.add_header("X-Requested-With", "XMLHttpRequest")

    try:
        resp = opener.open(req)
        raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        log(f"Grades fetched — {len(data)} courses found")
        return data
    except json.JSONDecodeError as exc:
        log(f"ERROR: Could not parse grades JSON: {exc}")
        return None
    except Exception as exc:
        log(f"ERROR: Grades request failed: {exc}")
        return None


# ── Grade diffing ─────────────────────────────────────────────────────────────

def diff_grades(current: list, previous) -> list:
    """
    Compare *current* gradebook to *previous* snapshot.

    *previous* may be a JSON string or a list of course dicts.
    Returns a list of change dicts.
    """
    changes = []

    if isinstance(previous, str):
        try:
            prev_list = json.loads(previous)
        except json.JSONDecodeError:
            prev_list = []
    else:
        prev_list = list(previous) if previous else []

    for course in current:
        course_name = course.get("CourseName", "Unknown")
        current_mark = course.get("CurrentMark", "")
        current_pct = course.get("CurrentMarkPercent", 0)

        prev_course = next(
            (p for p in prev_list if p.get("CourseName") == course_name), None
        )

        if prev_course:
            prev_mark = prev_course.get("CurrentMark", "")
            prev_pct = prev_course.get("CurrentMarkPercent", 0)

            if current_mark != prev_mark:
                changes.append(
                    {
                        "course": course_name,
                        "old_grade": f"{prev_mark} ({prev_pct}%)",
                        "new_grade": f"{current_mark} ({current_pct}%)",
                        "direction": "up" if current_pct > prev_pct else "down",
                    }
                )
        else:
            # Course not seen before
            changes.append(
                {
                    "course": course_name,
                    "new_grade": f"{current_mark} ({current_pct}%)",
                    "direction": "new",
                }
            )

    return changes


# ── SMS formatting ────────────────────────────────────────────────────────────

def format_sms(student_name: str, changes: list, all_grades: list) -> str:
    """Format a parent-friendly SMS message."""
    if changes:
        lines = [f"📚 {student_name} Grade Update:"]
        for c in changes:
            direction = c.get("direction", "new")
            emoji = "📈" if direction == "up" else "📉" if direction == "down" else "🆕"
            if "old_grade" in c:
                lines.append(f"{emoji} {c['course']}: {c['old_grade']} → {c['new_grade']}")
            else:
                lines.append(f"{emoji} {c['course']}: {c['new_grade']}")
    else:
        # Daily summary when nothing changed
        lines = [f"📋 {student_name} Daily Grades:"]
        for g in all_grades:
            course = g.get("CourseName", "?")
            mark = g.get("CurrentMark", "?")
            pct = g.get("CurrentMarkPercent", 0)
            lines.append(f"  {course}: {mark} ({pct}%)")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log("Subplot agent starting")
    log(f"Student: {STUDENT_ID}, School: {SCHOOL_CODE}")

    if not AERIES_EMAIL or not AERIES_PASSWORD:
        log("ERROR: No credentials provided")
        print(json.dumps({"status": "error", "reason": "no_credentials"}), flush=True)
        sys.exit(1)

    # 1. Login
    opener, _cookies = login_aeries(AERIES_EMAIL, AERIES_PASSWORD)
    if not opener:
        print(json.dumps({"status": "error", "reason": "login_failed"}), flush=True)
        sys.exit(1)

    # 2. Scrape grades
    grades = scrape_grades(opener, SCHOOL_CODE, STUDENT_NUM)
    if not grades:
        print(json.dumps({"status": "error", "reason": "scrape_failed"}), flush=True)
        sys.exit(1)

    # 3. Diff against previous
    changes = diff_grades(grades, PREVIOUS_SNAPSHOT)

    # 4. Format SMS
    sms_text = format_sms(f"Student {STUDENT_ID}", changes, grades)

    # 5. Output result JSON to STDOUT (this is what the orchestrator captures)
    result = {
        "status": "success",
        "student_id": STUDENT_ID,
        "grades": grades,
        "changes": changes,
        "sms_text": sms_text,
        "timestamp": time.time(),
    }
    print(json.dumps(result), flush=True)

    log(f"Agent complete. {len(changes)} grade changes detected.")


if __name__ == "__main__":
    main()
