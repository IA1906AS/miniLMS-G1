"""Grade Reports & Bulkhead Concurrency Isolation Module.

Protects critical API endpoints from resource starvation caused by heavy
CPU/IO tasks (such as CSV/JSON grade exports) by bounding worker concurrency
with a strict semaphore limiter (Bulkhead Pattern).
"""

from __future__ import annotations

import csv
import io
import threading
import time
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, make_response, request

from lms_project_1.errors import Forbidden, NotFound, Unauthenticated, ValidationError
from lms_project_1.guards import require_role
from lms_project_1.store import Store


class BulkheadFullError(Exception):
    """Raised when bulkhead capacity is saturated and cannot accept new tasks."""

    def __init__(self, message: str, retry_after: int = 2) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BulkheadLimiter:
    """Thread-safe bounded capacity concurrency limiter."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self.max_concurrent = max_concurrent
        self._semaphore = threading.BoundedSemaphore(value=max_concurrent)
        self._lock = threading.Lock()
        self._active_count = 0
        self._total_rejected = 0
        self._total_processed = 0

    def try_acquire(self) -> bool:
        """Attempt to acquire a bulkhead execution slot without blocking."""
        acquired = self._semaphore.acquire(blocking=False)
        with self._lock:
            if acquired:
                self._active_count += 1
                self._total_processed += 1
            else:
                self._total_rejected += 1
        return acquired

    def release(self) -> None:
        """Release the acquired slot back to the bulkhead pool."""
        with self._lock:
            if self._active_count > 0:
                self._active_count -= 1
                self._semaphore.release()

    def get_metrics(self) -> dict[str, Any]:
        """Inspect current bulkhead utilization metrics."""
        with self._lock:
            return {
                "maxConcurrent": self.max_concurrent,
                "activeWorkers": self._active_count,
                "availableSlots": max(0, self.max_concurrent - self._active_count),
                "totalProcessed": self._total_processed,
                "totalRejected": self._total_rejected,
            }


_GLOBAL_EXPORT_BULKHEAD = BulkheadLimiter(max_concurrent=2)


class GradeExportService:
    """Service handling grade export isolation under the bulkhead pattern."""

    @classmethod
    def export_grades(
        cls,
        actor: dict[str, Any],
        course_id: str,
        store: Store,
        bulkhead: BulkheadLimiter | None = None,
        file_format: str = "json",
        simulated_delay: float = 0.0,
    ) -> Any:
        """Execute protected grade export with capacity bounds and authorization checks."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        role = str(actor.get("role", "")).upper()
        actor_id = str(actor.get("id", ""))

        if role == "ADMIN":
            pass
        elif role in ("INSTRUCTOR", "TEACHER"):
            inst_id = course.get("instructorId") or course.get("instructor_id")
            if inst_id != actor_id:
                raise Forbidden("Chỉ giảng viên phụ trách khóa học mới có quyền xuất bảng điểm")
        else:
            raise Forbidden("Sinh viên không được phép xuất báo cáo điểm toàn khóa học")

        limiter = bulkhead or _GLOBAL_EXPORT_BULKHEAD

        if not limiter.try_acquire():
            raise BulkheadFullError(
                "Hệ thống xuất bảng điểm đang ở công suất tối đa. Vui lòng thử lại sau.",
                retry_after=2,
            )

        try:
            if simulated_delay > 0.0:
                time.sleep(simulated_delay)

            enrollments = store.get_enrollments(course_id)
            records = []
            for e in enrollments:
                student = store.get_user_by_id(e.get("studentId", ""))
                student_name = student.get("fullName", "") if student else ""
                student_email = student.get("email", "") if student else ""
                records.append(
                    {
                        "studentId": e.get("studentId"),
                        "studentName": student_name,
                        "studentEmail": student_email,
                        "score": e.get("score", 0.0),
                    }
                )

            if file_format == "csv":
                output = io.StringIO()
                writer = csv.DictWriter(
                    output,
                    fieldnames=["studentId", "studentName", "studentEmail", "score"],
                )
                writer.writeheader()
                for r in records:
                    writer.writerow(r)
                return output.getvalue()

            return {
                "courseId": course_id,
                "courseTitle": course.get("title", ""),
                "totalStudents": len(records),
                "grades": records,
            }

        finally:
            limiter.release()


# Blueprint registration
reports_bp = Blueprint("reports", __name__)
p9_bulkhead_bp = reports_bp  # Backward compatibility alias


@reports_bp.route("/courses/<course_id>/grades/export", methods=["GET"])
@require_role("ADMIN", "admin", "INSTRUCTOR", "instructor", "teacher")
def get_export_course_grades(course_id: str) -> tuple[Response, int] | Response:
    """Export course grades with Bulkhead bounded concurrency protection."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]
    file_format = request.args.get("format", "json").lower()
    if file_format not in ("json", "csv"):
        raise ValidationError("Tham số format chỉ hỗ trợ 'json' hoặc 'csv'")

    delay_ms = request.args.get("delay_ms")
    delay_sec = 0.0
    if delay_ms is not None:
        try:
            delay_sec = max(0.0, float(delay_ms) / 1000.0)
        except ValueError as exc:
            raise ValidationError("delay_ms phải là số") from exc

    bulkhead: BulkheadLimiter = current_app.config.get("EXPORT_BULKHEAD", _GLOBAL_EXPORT_BULKHEAD)

    try:
        result = GradeExportService.export_grades(
            actor=actor,
            course_id=course_id,
            store=store,
            bulkhead=bulkhead,
            file_format=file_format,
            simulated_delay=delay_sec,
        )

        if file_format == "csv":
            response = make_response(result, 200)
            response.headers["Content-Type"] = "text/csv; charset=utf-8"
            response.headers["Content-Disposition"] = f"attachment; filename=grades_{course_id}.csv"
            return response

        return jsonify(result), 200

    except BulkheadFullError as exc:
        resp = make_response(
            jsonify(
                {
                    "error": "BULKHEAD_CAPACITY_EXCEEDED",
                    "message": str(exc),
                    "retryAfterSeconds": exc.retry_after,
                    "bulkheadMetrics": bulkhead.get_metrics(),
                }
            ),
            429,
        )
        resp.headers["Retry-After"] = str(exc.retry_after)
        return resp


@reports_bp.route("/courses/<course_id>/grades/export/bulkhead-status", methods=["GET"])
@require_role("ADMIN", "admin", "INSTRUCTOR", "instructor", "teacher")
def get_export_bulkhead_status(course_id: str) -> tuple[Response, int]:
    """Inspect current capacity metrics of the export bulkhead limiter."""
    bulkhead: BulkheadLimiter = current_app.config.get("EXPORT_BULKHEAD", _GLOBAL_EXPORT_BULKHEAD)
    return jsonify(bulkhead.get_metrics()), 200
