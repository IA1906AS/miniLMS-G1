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

    role = str(actor.get("role", "")).upper()
    actor_id = actor.get("id")

    if role == "ADMIN":
        return cast(list[dict[str, Any]], s.get_enrollments(course_id))

    if role in ("INSTRUCTOR", "TEACHER"):
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


def create_course(
    actor: dict[str, Any], payload: dict[str, Any], store: Any = None
) -> dict[str, Any]:
    """Create a new course (Instructor or Admin)."""
    s = _resolve_store(store)
    role = str(actor.get("role", "")).upper()
    if role not in ("ADMIN", "INSTRUCTOR", "TEACHER"):
        raise Forbidden("Only instructors and admins can create courses")

    instructor_id = actor.get("id", "")
    if role == "ADMIN" and payload.get("instructorId"):
        instructor_id = payload["instructorId"]

    cid = f"c{len(s.courses) + 1}"
    return cast(
        dict[str, Any],
        s.create_course(
            course_id=cid,
            title=payload["title"],
            instructor_id=instructor_id,
            description=payload.get("description", ""),
            duration_hours=payload.get("durationHours", 30),
        ),
    )


def get_course(actor: dict[str, Any], course_id: str, store: Any = None) -> dict[str, Any]:
    """Get full course detail and enrollment status for actor."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    course_data = dict(course)
    instructor = s.get_user_by_id(course.get("instructorId", ""))
    course_data["instructorEmail"] = instructor.get("email", "") if instructor else ""
    course_data["instructorName"] = (
        instructor.get("fullName") or instructor.get("full_name") or "" if instructor else ""
    )

    actor_id = actor.get("id", "")
    enr = s.get_enrollment(course_id, actor_id)
    course_data["isEnrolled"] = enr is not None
    if enr:
        course_data["studentScore"] = enr["score"]
        course_data["completedLessons"] = enr.get("completedLessons", [])

    return course_data


def enroll_in_course(actor: dict[str, Any], course_id: str, store: Any = None) -> dict[str, Any]:
    """Enroll student in a course (Defense in Depth: Student only)."""
    s = _resolve_store(store)
    role = str(actor.get("role", "")).upper()
    if role != "STUDENT":
        raise Forbidden("Only students can enroll in courses")

    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    actor_id = str(actor.get("id", ""))
    existing = s.get_enrollment(course_id, actor_id)
    if existing is not None:
        raise ValidationError(f"Student '{actor_id}' is already enrolled in course '{course_id}'")

    return cast(dict[str, Any], s.enroll_student(course_id, actor_id))


def add_course_lesson(
    actor: dict[str, Any], course_id: str, title: str, store: Any = None
) -> dict[str, Any]:
    """Add a lesson to a course (Defense in Depth: assigned instructor or Admin)."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    role = str(actor.get("role", "")).upper()
    actor_id = actor.get("id")
    if role not in ("ADMIN", "INSTRUCTOR", "TEACHER"):
        raise Forbidden("Insufficient permissions")

    if role in ("INSTRUCTOR", "TEACHER") and course.get("instructorId") != actor_id:
        raise Forbidden("Instructor does not teach this course")

    return cast(dict[str, Any], s.add_lesson(course_id, title))


def complete_course_lesson(
    actor: dict[str, Any], course_id: str, lesson_id: str, store: Any = None
) -> dict[str, Any]:
    """Mark a lesson complete for enrolled student."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    role = str(actor.get("role", "")).upper()
    if role != "STUDENT":
        raise Forbidden("Only students can complete lessons")

    actor_id = str(actor.get("id", ""))
    enr = s.get_enrollment(course_id, actor_id)
    if enr is None:
        raise Forbidden(f"Student is not enrolled in course '{course_id}'")

    lessons = course.get("lessons", [])
    if not any(les.get("id") == lesson_id for les in lessons):
        raise NotFound(f"Lesson '{lesson_id}' not found in course '{course_id}'")

    return cast(dict[str, Any], s.complete_lesson(course_id, actor_id, lesson_id))


def create_course_assignment(
    actor: dict[str, Any],
    course_id: str,
    payload: dict[str, Any],
    store: Any = None,
) -> dict[str, Any]:
    """Create an assignment for a course (assigned instructor or Admin)."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    role = str(actor.get("role", "")).upper()
    actor_id = actor.get("id")
    if role not in ("ADMIN", "INSTRUCTOR", "TEACHER"):
        raise Forbidden("Insufficient permissions to create assignments")

    if role in ("INSTRUCTOR", "TEACHER") and course.get("instructorId") != actor_id:
        raise Forbidden("Instructor does not teach this course")

    return cast(
        dict[str, Any],
        s.create_assignment(
            course_id=course_id,
            title=payload["title"],
            description=payload.get("description", ""),
            max_score=payload.get("maxScore", 10.0),
        ),
    )


def get_course_assignments(
    actor: dict[str, Any], course_id: str, store: Any = None
) -> list[dict[str, Any]]:
    """Get assignments for a course following object-level authorization."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    role = str(actor.get("role", "")).upper()
    actor_id = str(actor.get("id", ""))

    if role == "ADMIN":
        return cast(list[dict[str, Any]], s.get_assignments(course_id))

    if role in ("INSTRUCTOR", "TEACHER"):
        if course.get("instructorId") != actor_id:
            raise Forbidden("Instructor does not teach this course")
        return cast(list[dict[str, Any]], s.get_assignments(course_id))

    if role == "STUDENT":
        enr = s.get_enrollment(course_id, actor_id)
        if enr is None:
            raise Forbidden(f"Student is not enrolled in course '{course_id}'")
        return cast(list[dict[str, Any]], s.get_assignments(course_id))

    raise Forbidden("Unauthorized role")


def submit_course_assignment(
    actor: dict[str, Any],
    course_id: str,
    assignment_id: str,
    content: str,
    store: Any = None,
) -> dict[str, Any]:
    """Student submits an assignment."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    assignment = s.get_assignment_by_id(assignment_id)
    if assignment is None or assignment.get("courseId") != course_id:
        raise NotFound(f"Assignment '{assignment_id}' not found in course '{course_id}'")

    role = str(actor.get("role", "")).upper()
    if role != "STUDENT":
        raise Forbidden("Only enrolled students can submit assignments")

    actor_id = str(actor.get("id", ""))
    enr = s.get_enrollment(course_id, actor_id)
    if enr is None:
        raise Forbidden(f"Student is not enrolled in course '{course_id}'")

    return cast(dict[str, Any], s.submit_assignment(assignment_id, actor_id, content))


def get_assignment_submissions(
    actor: dict[str, Any],
    course_id: str,
    assignment_id: str,
    store: Any = None,
) -> list[dict[str, Any]]:
    """View submissions for an assignment (Instructor or Admin)."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    assignment = s.get_assignment_by_id(assignment_id)
    if assignment is None or assignment.get("courseId") != course_id:
        raise NotFound(f"Assignment '{assignment_id}' not found in course '{course_id}'")

    role = str(actor.get("role", "")).upper()
    actor_id = actor.get("id")

    if role not in ("ADMIN", "INSTRUCTOR", "TEACHER"):
        raise Forbidden("Insufficient permissions to view submissions")

    if role in ("INSTRUCTOR", "TEACHER") and course.get("instructorId") != actor_id:
        raise Forbidden("Instructor does not teach this course")

    return cast(list[dict[str, Any]], s.get_submissions(assignment_id))


def grade_assignment_submission(
    actor: dict[str, Any],
    course_id: str,
    assignment_id: str,
    student_id: str,
    score: float,
    feedback: str = "",
    store: Any = None,
) -> dict[str, Any]:
    """Grade a student submission (assigned instructor only)."""
    s = _resolve_store(store)
    course = s.get_course_by_id(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")

    assignment = s.get_assignment_by_id(assignment_id)
    if assignment is None or assignment.get("courseId") != course_id:
        raise NotFound(f"Assignment '{assignment_id}' not found in course '{course_id}'")

    role = str(actor.get("role", "")).upper()
    actor_id = actor.get("id")

    if role not in ("INSTRUCTOR", "TEACHER") or course.get("instructorId") != actor_id:
        raise Forbidden("Only the assigned instructor may grade submissions for this course")

    max_score = float(assignment.get("maxScore", 10.0))
    if score < 0.0 or score > max_score:
        raise ValidationError(f"'score' must be within [0, {max_score}]")

    sub, old_score = s.grade_submission(assignment_id, student_id, score, feedback)
    res = dict(sub)
    res["_old_score"] = old_score
    return res
