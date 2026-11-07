"""Enrollment, lesson access, progress, notification and certificate services."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from flask import Blueprint, Response, current_app, g, jsonify, make_response, request

from lms_project_1.errors import Conflict, Forbidden, NotFound, Unauthenticated, ValidationError
from lms_project_1.guards import require_role
from lms_project_1.models import Certificate, Enrollment, LessonProgress, Notification

learning_bp = Blueprint("learning", __name__)


def _store() -> Any:
    return current_app.config["STORE"]


def _actor() -> dict[str, Any]:
    actor = getattr(g, "actor", None)
    if not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    return actor


def _json() -> dict[str, Any]:
    if not request.is_json:
        raise ValidationError("Request body must be JSON")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    return body


def _course(course_id: str) -> dict[str, Any]:
    course = _store().courses.get(course_id)
    if course is None:
        raise NotFound("Course not found")
    return cast(dict[str, Any], course)


def _lesson(course: dict[str, Any], lesson_id: str) -> dict[str, Any]:
    for lesson in course.get("lessons", []):
        if lesson["id"] == lesson_id:
            return cast(dict[str, Any], lesson)
    raise NotFound("Lesson not found")


def _is_owner(actor: dict[str, Any], course: dict[str, Any]) -> bool:
    return str(actor.get("role", "")).upper() == "ADMIN" or (
        str(actor.get("role", "")).upper() in {"TEACHER", "INSTRUCTOR"}
        and course.get("instructorId") == actor.get("id")
    )


def _require_owner(course: dict[str, Any]) -> dict[str, Any]:
    actor = _actor()
    if not _is_owner(actor, course):
        raise Forbidden("Only the assigned instructor or admin may view this report")
    return actor


def _notify(user_id: str, kind: str, title: str, message: str) -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "kind": kind,
        "title": title,
        "message": message,
        "isRead": False,
        "createdAt": datetime.now(UTC).isoformat(),
    }
    store = _store()
    if store.db_session is not None:
        store.db_session.add(
            Notification(
                id=item["id"],
                user_id=user_id,
                kind=kind,
                title=title,
                message=message,
            )
        )
        store.db_session.commit()
    store.notifications[item["id"]] = item
    return item


def _completed_lesson_ids(course_id: str, student_id: str) -> set[str]:
    store = _store()
    result = {
        lesson_id
        for (cid, lesson_id, sid), _item in store.lesson_progress.items()
        if cid == course_id and sid == student_id
    }
    enrollment = store.enrollments.get((course_id, student_id))
    if enrollment:
        result.update(str(value) for value in enrollment.get("completedLessons", []))
    return result


def _progress(course: dict[str, Any], student_id: str) -> dict[str, Any]:
    lessons = course.get("lessons", [])
    lesson_ids = {str(item["id"]) for item in lessons}
    completed = _completed_lesson_ids(course["id"], student_id) & lesson_ids
    percent = round(len(completed) / len(lesson_ids) * 100) if lesson_ids else 0
    chapter_totals: dict[str, dict[str, int]] = {}
    for lesson in lessons:
        chapter_id = str(lesson.get("chapterId") or "unassigned")
        stats = chapter_totals.setdefault(chapter_id, {"completed": 0, "total": 0})
        stats["total"] += 1
        if lesson["id"] in completed:
            stats["completed"] += 1
    return {
        "courseId": course["id"],
        "studentId": student_id,
        "completedLessonIds": sorted(completed),
        "completedLessons": len(completed),
        "totalLessons": len(lesson_ids),
        "percent": percent,
        "chapters": chapter_totals,
    }


def _enroll(course: dict[str, Any], student_id: str, order_id: str | None = None) -> dict[str, Any]:
    store = _store()
    if store.get_enrollment(course["id"], student_id) is not None:
        raise Conflict("Student is already enrolled")
    item = cast(dict[str, Any], store.enroll_student(course["id"], student_id))
    item["status"] = "ACTIVE"
    item["activatedByOrderId"] = order_id
    store.enrollments[(course["id"], student_id)].update(item)
    if store.db_session is not None:
        row = store.db_session.get(Enrollment, (course["id"], student_id))
        if row is not None:
            row.status = "ACTIVE"
            row.activated_by_order_id = order_id
            store.db_session.commit()
    _notify(
        student_id, "ENROLLMENT", "Enrollment activated", f"You can now learn {course['title']}."
    )
    return item


@learning_bp.post("/api/courses/<course_id>/enroll")
@require_role("STUDENT")
def enroll_free_course(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    if course.get("status") != "PUBLISHED" or not course.get("isVisible", False):
        raise NotFound("Course not found")
    if float(course.get("price", 0)) > 0:
        raise Conflict("Paid courses require a completed order")
    item = _enroll(course, str(_actor()["id"]))
    return jsonify(item), 201


@learning_bp.post("/api/admin/courses/<course_id>/activate-enrollment")
@require_role("ADMIN")
def activate_paid_enrollment(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    body = _json()
    student_id = str(body.get("studentId", "")).strip()
    order_id = str(body.get("orderId", "")).strip()
    user = _store().get_user_by_id(student_id)
    if not student_id or user is None or str(user.get("role", "")).upper() != "STUDENT":
        raise ValidationError("A valid student is required")
    if not order_id or len(order_id) > 36:
        raise ValidationError("A valid orderId is required")
    return jsonify(_enroll(course, student_id, order_id)), 201


@learning_bp.get("/api/courses/<course_id>/lessons/<lesson_id>")
def lesson_player(course_id: str, lesson_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    lesson = _lesson(course, lesson_id)
    actor = _actor()
    if (
        not _is_owner(actor, course)
        and _store().get_enrollment(course_id, str(actor["id"])) is None
    ):
        raise Forbidden("Enrollment is required")
    result = dict(lesson)
    result["resources"] = [
        dict(item) for item in _store().lesson_resources.values() if item["lessonId"] == lesson_id
    ]
    return jsonify(result), 200


@learning_bp.put("/api/courses/<course_id>/lessons/<lesson_id>/progress")
@require_role("STUDENT")
def complete_lesson(course_id: str, lesson_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    _lesson(course, lesson_id)
    student_id = str(_actor()["id"])
    if _store().get_enrollment(course_id, student_id) is None:
        raise Forbidden("Enrollment is required")
    key = (course_id, lesson_id, student_id)
    store = _store()
    was_new = key not in store.lesson_progress
    if was_new and store.db_session is not None:
        existing = store.db_session.get(LessonProgress, key)
        if existing is not None:
            store.lesson_progress[key] = {"completedAt": existing.completed_at.isoformat()}
            was_new = False
    if was_new:
        completed_at = datetime.now(UTC)
        if store.db_session is not None:
            store.db_session.add(
                LessonProgress(
                    course_id=course_id,
                    lesson_id=lesson_id,
                    student_id=student_id,
                    completed_at=completed_at,
                )
            )
            store.db_session.commit()
        store.lesson_progress[key] = {"completedAt": completed_at.isoformat()}
        enrollment = store.enrollments.get((course_id, student_id))
        if enrollment is not None:
            completed = enrollment.setdefault("completedLessons", [])
            if lesson_id not in completed:
                completed.append(lesson_id)
    result = _progress(course, student_id)
    if was_new and result["percent"] == 100:
        _notify(
            student_id, "COURSE_COMPLETED", "Course completed", f"You completed {course['title']}."
        )
    return jsonify(result), 200


@learning_bp.get("/api/courses/<course_id>/progress")
@require_role("STUDENT")
def own_progress(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    student_id = str(_actor()["id"])
    if _store().get_enrollment(course_id, student_id) is None:
        raise Forbidden("Enrollment is required")
    return jsonify(_progress(course, student_id)), 200


@learning_bp.get("/api/notifications")
def list_notifications() -> tuple[Response, int]:
    user_id = str(_actor()["id"])
    items = sorted(
        (dict(item) for item in _store().notifications.values() if item["userId"] == user_id),
        key=lambda item: item["createdAt"],
        reverse=True,
    )
    return jsonify({"items": items, "unread": sum(not item["isRead"] for item in items)}), 200


@learning_bp.patch("/api/notifications/<notification_id>/read")
def mark_notification_read(notification_id: str) -> tuple[Response, int]:
    item = _store().notifications.get(notification_id)
    if item is None or item["userId"] != str(_actor()["id"]):
        raise NotFound("Notification not found")
    item["isRead"] = True
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(Notification, notification_id)
        if row is not None:
            row.is_read = True
            store.db_session.commit()
    return jsonify(dict(item)), 200


@learning_bp.post("/api/courses/<course_id>/certificate")
@require_role("STUDENT")
def issue_certificate(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    student_id = str(_actor()["id"])
    if _store().get_enrollment(course_id, student_id) is None:
        raise Forbidden("Enrollment is required")
    if _progress(course, student_id)["percent"] != 100:
        raise Conflict("Course completion is required")
    store = _store()
    existing = next(
        (
            x
            for x in store.certificates.values()
            if x["courseId"] == course_id and x["studentId"] == student_id
        ),
        None,
    )
    if existing:
        return jsonify(dict(existing)), 200
    certificate_id = str(uuid.uuid4())
    verification_code = hashlib.sha256(
        f"{certificate_id}:{course_id}:{student_id}".encode()
    ).hexdigest()
    item = {
        "id": certificate_id,
        "courseId": course_id,
        "studentId": student_id,
        "courseTitle": course["title"],
        "verificationCode": verification_code,
        "issuedAt": datetime.now(UTC).isoformat(),
    }
    if store.db_session is not None:
        store.db_session.add(
            Certificate(
                id=certificate_id,
                course_id=course_id,
                student_id=student_id,
                verification_code=verification_code,
            )
        )
        store.db_session.commit()
    store.certificates[certificate_id] = item
    return jsonify(item), 201


@learning_bp.get("/api/certificates/<certificate_id>/download")
def download_certificate(certificate_id: str) -> Response:
    item = _store().certificates.get(certificate_id)
    if item is None or item["studentId"] != str(_actor()["id"]):
        raise NotFound("Certificate not found")
    user = _store().get_user_by_id(item["studentId"])
    content = (
        "EduShield Certificate of Completion\n"
        f"Student: {(user or {}).get('fullName') or (user or {}).get('email', '')}\n"
        f"Course: {item['courseTitle']}\n"
        f"Issued: {item['issuedAt']}\n"
        f"Verification: {item['verificationCode']}\n"
    )
    response = make_response(content, 200)
    response.mimetype = "text/plain"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="certificate-{certificate_id}.txt"'
    )
    return response


@learning_bp.get("/api/teacher/courses/<course_id>/students")
def course_roster(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    _require_owner(course)
    items = []
    for enrollment in _store().get_enrollments(course_id):
        user = _store().get_user_by_id(str(enrollment["studentId"]))
        items.append(
            {
                "id": enrollment["studentId"],
                "name": (user or {}).get("fullName") or (user or {}).get("full_name", ""),
                "email": (user or {}).get("email", ""),
                "status": enrollment.get("status", "ACTIVE"),
            }
        )
    return jsonify({"courseId": course_id, "items": items, "total": len(items)}), 200


@learning_bp.get("/api/teacher/courses/<course_id>/progress")
def course_progress_report(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    _require_owner(course)
    rows = [
        _progress(course, str(enrollment["studentId"]))
        for enrollment in _store().get_enrollments(course_id)
    ]
    average = round(sum(row["percent"] for row in rows) / len(rows), 2) if rows else 0
    return jsonify({"courseId": course_id, "students": rows, "averagePercent": average}), 200
