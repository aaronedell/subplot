"""Build human-readable SMS grade reports from Aeries gradebook data."""
from __future__ import annotations

from typing import Any


def build_report(
    student_name: str,
    current_grades: list[dict[str, Any]],
    previous_grades: list[dict[str, Any]] | None = None,
) -> str:
    """
    Compare *current_grades* to *previous_grades* and return a formatted SMS string.

    Grade dicts are expected to contain at least:
        CourseName, CurrentMark, CurrentMarkPercent
    """
    changes = _diff_grades(current_grades, previous_grades or [])

    if changes:
        lines = [f"📚 {student_name} Grade Update:"]
        for change in changes:
            direction = change.get("direction", "new")
            emoji = "📈" if direction == "up" else "📉" if direction == "down" else "🆕"
            if "old_grade" in change:
                lines.append(
                    f"  {emoji} {change['course']}: {change['old_grade']} → {change['new_grade']}"
                )
            else:
                lines.append(f"  {emoji} {change['course']}: {change['new_grade']}")
    else:
        lines = [f"📋 {student_name} Daily Grades:"]
        for g in current_grades:
            course = g.get("CourseName", "Unknown")
            mark = g.get("CurrentMark", "—")
            pct = g.get("CurrentMarkPercent", 0)
            lines.append(f"  {course}: {mark} ({pct}%)")

    if not current_grades and not changes:
        lines = [f"📋 {student_name}: No grade data available yet."]

    return "\n".join(lines)


def _diff_grades(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a list of change dicts for courses whose grade letter changed."""
    changes: list[dict[str, Any]] = []

    for course in current:
        course_name = course.get("CourseName", "Unknown")
        current_mark = course.get("CurrentMark", "")
        current_pct = course.get("CurrentMarkPercent", 0)

        prev_course = next(
            (p for p in previous if p.get("CourseName") == course_name), None
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
            # New course not seen before
            changes.append(
                {
                    "course": course_name,
                    "new_grade": f"{current_mark} ({current_pct}%)",
                    "direction": "new",
                }
            )

    return changes
