"""Layer 4: Object-Level Authorization & Business Logic (services.py).

Strictly decoupled from Flask: MUST NOT import flask.
Exceptions are raised from app.errors / lms_project_1.errors.
"""

from __future__ import annotations

import math
from typing import Any, cast

from lms_project_1.errors import Forbidden, NotFound, ValidationError

_current_store: Any = None


def set_store(store: Any) -> None:
    """Register the active Store instance with the service layer."""
    global _current_store
    _current_store = store


def _resolve_store(store: Any = None) -> Any:
    if store is not None:
        return store
    if _current_store is not None:
        return _current_store
    from lms_project_1.store import Store

    return Store()


def _validate_score(score: Any) -> float:
    """Validate score domain in range [0, 10] as Defense in Depth."""
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValidationError("'score' must be a numeric value")
    if math.isnan(score) or math.isinf(score) or score < 0.0 or score > 10.0:
        raise ValidationError("'score' must be within [0, 10]")
    return float(score)


def get_grades(actor: dict[str, Any], course_id: str, store: Any = None) -> list[dict[str, Any]]:
    """Retrieve grades for a course following the object authorization matrix.

    - ADMIN: Sees all enrolled students.
    - INSTRUCTOR (assigned to course): Sees all enrolled students.
    - INSTRUCTOR (other courses): 403 Forbidden.
    - STUDENT (enrolled): Sees strictly their own record [{"studentId", "score"}].
    - STUDENT (not enrolled): 403 Forbidden.
    - Course not found: 404 NotFound.
    """
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    role = actor.get("role")
    actor_id = actor.get("id")

    if role == "ADMIN":
        return cast(list[dict[str, Any]], s.get_enrollments(course_id))

    if role == "INSTRUCTOR":
        if course.get("instructorId") != actor_id:
            raise Forbidden("Instructor does not teach this course")
        return cast(list[dict[str, Any]], s.get_enrollments(course_id))

    if role == "STUDENT":
        enrollment = s.get_enrollment(course_id, str(actor_id))
        if enrollment is None:
            raise Forbidden(f"Student '{actor_id}' is not enrolled in course '{course_id}'")
        return [{"studentId": enrollment["studentId"], "score": enrollment["score"]}]

    raise Forbidden("Unauthorized role")


def update_grade(
    actor: dict[str, Any],
    course_id: str,
    student_id: str,
    score: Any,
    store: Any = None,
) -> dict[str, Any]:
    """Update student grade in a course following the object authorization matrix.

    - Course must exist (otherwise 404 NotFound).
    - Only INSTRUCTOR assigned to course is allowed (otherwise 403 Forbidden).
    - Student must be enrolled in course (otherwise 404 NotFound).
    - Score must be in [0, 10] (otherwise 400 ValidationError).
    """
    s = _resolve_store(store)

    # 1. Check course existence (404 môn)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    # 2. Permission check (403)
    role = actor.get("role")
    actor_id = actor.get("id")

    if role != "INSTRUCTOR" or course.get("instructorId") != actor_id:
        raise Forbidden("Only the assigned instructor may update grades for this course")

    # 3. Domain validation (400)
    score_val = _validate_score(score)

    # 4. Enrollment check (404 ghi danh)
    enrollment = s.get_enrollment(course_id, student_id)
    if enrollment is None:
        raise NotFound(f"Student '{student_id}' is not enrolled in course '{course_id}'")

    updated_rec, old_score = s.update_score(course_id, student_id, score_val)

    # Keep track of old_score for audit logging convenience
    result: dict[str, Any] = {
        "courseId": updated_rec["courseId"],
        "studentId": updated_rec["studentId"],
        "score": updated_rec["score"],
    }
    result["_old_score"] = old_score
    return result


def get_home_dashboard(actor: dict[str, Any], store: Any = None) -> dict[str, Any]:
    """Retrieve home dashboard data for authenticated actor."""
    s = _resolve_store(store)
    user_id = actor.get("id", "")
    return cast(dict[str, Any], s.get_home_dashboard(user_id))


def get_account_data(actor: dict[str, Any], store: Any = None) -> dict[str, Any]:
    """Retrieve account profile, history, and notifications for authenticated actor."""
    s = _resolve_store(store)
    user_id = actor.get("id", "")
    return cast(dict[str, Any], s.get_account_data(user_id))


def update_profile(
    actor: dict[str, Any], payload: dict[str, Any], store: Any = None
) -> dict[str, Any]:
    """Update profile fields for authenticated actor (prevents IDOR)."""
    s = _resolve_store(store)
    user_id = actor.get("id", "")
    return cast(dict[str, Any], s.update_user_profile(user_id, payload))


def change_password(
    actor: dict[str, Any], old_password: str, new_password: str, store: Any = None
) -> None:
    """Safely change user password for authenticated actor."""
    s = _resolve_store(store)
    user_id = actor.get("id", "")
    s.update_user_password(user_id, old_password, new_password)


def update_notifications(
    actor: dict[str, Any], settings: dict[str, Any], store: Any = None
) -> dict[str, bool]:
    """Update notification settings for authenticated actor."""
    s = _resolve_store(store)
    user_id = actor.get("id", "")
    return cast(dict[str, bool], s.update_user_notifications(user_id, settings))
