from __future__ import annotations

from typing import Any

from app.audit import write_audit_log
from app.errors import Forbidden, NotFound
from app.schemas import validate_score_value
from app.store import store


def _validate_actor(actor: Any) -> tuple[str, str]:
    if not isinstance(actor, dict):
        raise Forbidden()
    actor_id = actor.get("id")
    actor_role = str(actor.get("role", "")).upper()
    if actor_role == "TEACHER":
        actor_role = "INSTRUCTOR"
    if not actor_id or not isinstance(actor_id, str) or not actor_role:
        raise Forbidden()
    return store.resolve_user_id(actor_id), actor_role


def assert_can_update_course(actor: dict[str, Any], course_id: str) -> dict[str, Any]:
    """Check order: 404 (môn không tồn tại) -> 403 (không phải GV dạy môn đó)."""
    actor_id, actor_role = _validate_actor(actor)
    course = store.courses_by_id.get(course_id)
    if not course:
        raise NotFound()

    if actor_role != "INSTRUCTOR" or course.get("instructorId") != actor_id:
        write_audit_log(
            actor_id=actor_id,
            action="UPDATE_GRADE",
            resource=f"/courses/{course_id}/grades",
            result="FORBIDDEN",
        )
        raise Forbidden()

    return course


def get_grades(actor: dict[str, Any], course_id: str) -> list[dict[str, Any]]:
    actor_id, actor_role = _validate_actor(actor)

    course = store.courses_by_id.get(course_id)
    if not course:
        raise NotFound()

    if actor_role == "ADMIN":
        return [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id
        ]

    if actor_role == "INSTRUCTOR":
        if course.get("instructorId") != actor_id:
            write_audit_log(
                actor_id=actor_id,
                action="GET_GRADES",
                resource=f"/courses/{course_id}/grades",
                result="FORBIDDEN",
            )
            raise Forbidden()
        return [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id
        ]

    if actor_role == "STUDENT":
        own_records = [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id
            and (e["studentId"] == actor_id or store.resolve_user_id(e["studentId"]) == actor_id)
        ]
        if not own_records:
            write_audit_log(
                actor_id=actor_id,
                action="GET_GRADES",
                resource=f"/courses/{course_id}/grades",
                result="FORBIDDEN",
            )
            raise Forbidden()
        return own_records

    write_audit_log(
        actor_id=actor_id,
        action="GET_GRADES",
        resource=f"/courses/{course_id}/grades",
        result="FORBIDDEN",
    )
    raise Forbidden()


def update_grade(
    actor: dict[str, Any],
    course_id: str,
    student_id: str,
    score: Any,
) -> dict[str, Any]:
    actor_id, _ = _validate_actor(actor)

    # 1 & 2: 404 (môn) -> 403 (quyền đối tượng)
    assert_can_update_course(actor, course_id)

    # 3: 400 (Service tự kiểm tra miền giá trị)
    validated_score = validate_score_value(score)

    # 4: 404 (Kiểm tra sinh viên có ghi danh)
    resolved_student_id = store.resolve_user_id(student_id)
    target_enrollment = None
    for e in store.enrollments:
        if e["courseId"] == course_id and (
            e["studentId"] == resolved_student_id or e["studentId"] == student_id
        ):
            target_enrollment = e
            break

    if target_enrollment is None:
        raise NotFound()

    old_score = target_enrollment["score"]
    target_enrollment["score"] = validated_score

    # 5: Ghi Audit Log (Lớp 8)
    write_audit_log(
        actor_id=actor_id,
        action="UPDATE_GRADE",
        resource=f"/courses/{course_id}/grades/{target_enrollment['studentId']}",
        result="SUCCESS",
        old_score=old_score,
        new_score=validated_score,
    )

    return {
        "courseId": course_id,
        "studentId": target_enrollment["studentId"],
        "score": validated_score,
    }
