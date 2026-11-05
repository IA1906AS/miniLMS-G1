"""Defensive Pattern #6: Timeout & Fallback for Course Statistics Dashboard.

This module implements:
1. FakeCourseStatsClient: Simulated upstream analytics service with configurable delay and faults.
2. DashboardService: Enforces strict authorization, deadline-bounded upstream calls,
   and last-known-good fallback caching without fabricating sensitive academic figures.
3. p6_dashboard_bp: Flask blueprint exposing both patched and baseline endpoints for lab comparison.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, request

from lms_project_1.errors import Forbidden, NotFound, Unauthenticated, ValidationError
from lms_project_1.guards import require_role
from lms_project_1.store import Store

# Thread pool for bounded asynchronous execution of upstream stats calls
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="stats_worker")

# Global lab configuration for dynamic delay/error injection in security audit & Burp Suite
_LAB_CONFIG: dict[str, Any] = {
    "default_delay_seconds": 0.0,
    "simulate_error": None,  # None, "timeout", "connection"
}
_LAB_LOCK = threading.Lock()


class StatsServiceError(Exception):
    """Base error for upstream statistics service failures."""


class StatsTimeoutError(StatsServiceError):
    """Raised when upstream statistics service exceeds deadline."""


class StatsConnectionError(StatsServiceError):
    """Raised when upstream statistics service encounters network connection failure."""


class FakeCourseStatsClient:
    """Mockable client for external course statistics aggregation."""

    def __init__(self, default_delay: float = 0.0) -> None:
        self.default_delay = default_delay

    def fetch_stats(
        self,
        course_id: str,
        store: Store,
        delay: float | None = None,
        simulate_error: str | None = None,
    ) -> dict[str, Any]:
        """Fetch course statistics with simulated network latency or upstream errors."""
        effective_delay = delay if delay is not None else self.default_delay

        with _LAB_LOCK:
            if delay is None and _LAB_CONFIG["default_delay_seconds"] > 0.0:
                effective_delay = _LAB_CONFIG["default_delay_seconds"]
            if simulate_error is None:
                simulate_error = _LAB_CONFIG["simulate_error"]

        if effective_delay > 0.0:
            time.sleep(effective_delay)

        if simulate_error == "timeout":
            raise StatsTimeoutError("Upstream analytics provider connection timed out")
        if simulate_error == "connection":
            raise StatsConnectionError("Failed to establish TCP handshake with analytics service")

        # Compute real statistics based on local store to remain consistent and honest
        course_enrollments = [
            rec for (cid, _sid), rec in store.enrollments.items() if cid == course_id
        ]
        enrolled_count = len(course_enrollments)
        scores = [float(e.get("score", 0.0)) for e in course_enrollments if "score" in e]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # Submissions count
        submissions_count = sum(
            1 for sub in store.all_submissions if sub.get("course_id") == course_id
        )

        passed_count = len([s for s in scores if s >= 5.0])
        completion_rate = round((passed_count / max(enrolled_count, 1)) * 100, 1)

        return {
            "courseId": course_id,
            "enrolledStudents": enrolled_count,
            "averageScore": avg_score,
            "totalSubmissions": submissions_count,
            "completionRate": completion_rate,
            "generatedAt": datetime.now(UTC).isoformat(),
        }


class DashboardService:
    """Core service applying defensive Timeout & Fallback pattern for Course Dashboard."""

    DEFAULT_TIMEOUT_SECONDS: float = 1.0

    @classmethod
    def get_course_dashboard(
        cls,
        actor: dict[str, Any],
        course_id: str,
        store: Store,
        stats_client: FakeCourseStatsClient | None = None,
        timeout_seconds: float | None = None,
        delay_seconds: float | None = None,
        simulate_error: str | None = None,
        baseline_unprotected: bool = False,
    ) -> dict[str, Any]:
        """Retrieve course statistics dashboard with strict authorization and fallback."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        # 1. Check Course Existence (404)
        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        # 2. Strict Authorization / RBAC Object Permissions (403)
        role = str(actor.get("role", "")).upper()
        actor_id = str(actor.get("id", ""))

        if role == "ADMIN":
            pass  # Admin has global oversight
        elif role in ("INSTRUCTOR", "TEACHER"):
            instructor_id = course.get("instructorId") or course.get("instructor_id")
            if instructor_id != actor_id:
                raise Forbidden("Giảng viên không phụ trách khóa học này không có quyền truy cập")
        elif role == "STUDENT":
            is_enrolled = (course_id, actor_id) in store.enrollments or any(
                cid == course_id and sid == actor_id for (cid, sid) in store.enrollments
            )
            if not is_enrolled:
                raise Forbidden("Sinh viên chưa ghi danh khóa học này không thể xem thống kê")
        else:
            raise Forbidden("Vai trò không được cấp phép truy cập thống kê")

        client = stats_client or FakeCourseStatsClient()

        # 3. BASELINE LAB MODE: Unprotected (no timeout, no fallback)
        if baseline_unprotected:
            # Direct blocking call that hangs if delay is large or crashes on error
            stats_data = client.fetch_stats(
                course_id=course_id,
                store=store,
                delay=delay_seconds,
                simulate_error=simulate_error,
            )
            return {
                "courseId": course_id,
                "title": course.get("title", ""),
                "stats": stats_data,
                "isFallback": False,
                "asOf": datetime.now(UTC).isoformat(),
                "reasonCode": None,
                "mode": "baseline_unprotected",
            }

        # 4. PATCHED MODE: Deadline Bound Execution with Fallback
        deadline = (
            timeout_seconds
            if timeout_seconds is not None
            else cls.DEFAULT_TIMEOUT_SECONDS
        )

        future = _EXECUTOR.submit(
            client.fetch_stats,
            course_id=course_id,
            store=store,
            delay=delay_seconds,
            simulate_error=simulate_error,
        )

        try:
            stats_data = future.result(timeout=deadline)
            # Update last-known-good cache for this specific course
            with store.dashboard_lock:
                store.dashboard_cache[course_id] = {
                    "data": stats_data,
                    "cached_at": datetime.now(UTC),
                }

            return {
                "courseId": course_id,
                "title": course.get("title", ""),
                "stats": stats_data,
                "isFallback": False,
                "asOf": datetime.now(UTC).isoformat(),
                "reasonCode": None,
                "mode": "patched_secure",
            }

        except (concurrent.futures.TimeoutError, StatsTimeoutError):
            # Upstream timed out: execute fallback
            return cls._resolve_fallback(
                course_id=course_id,
                course=course,
                store=store,
                reason_code="UPSTREAM_TIMEOUT",
                warning=(
                    "Dữ liệu thống kê được phục hồi từ bộ nhớ đệm (Fallback) "
                    "do dịch vụ phân tích phản hồi vượt quá thời hạn cho phép."
                ),
            )

        except (StatsConnectionError, Exception) as exc:
            # Upstream network/service failure: execute fallback
            return cls._resolve_fallback(
                course_id=course_id,
                course=course,
                store=store,
                reason_code="UPSTREAM_CONNECTION_ERROR",
                warning=(
                    f"Dịch vụ thống kê bị gián đoạn ({type(exc).__name__}), "
                    "hệ thống chuyển sang chế độ dữ liệu đệm an toàn."
                ),
            )

    @classmethod
    def _resolve_fallback(
        cls,
        course_id: str,
        course: dict[str, Any],
        store: Store,
        reason_code: str,
        warning: str,
    ) -> dict[str, Any]:
        """Retrieve last-known-good cache or return explicit safe degraded metadata."""
        with store.dashboard_lock:
            cached_entry = store.dashboard_cache.get(course_id)

        if cached_entry and isinstance(cached_entry, dict) and "data" in cached_entry:
            cached_at = cached_entry.get("cached_at")
            as_of_str = cached_at.isoformat() if isinstance(cached_at, datetime) else str(cached_at)
            return {
                "courseId": course_id,
                "title": course.get("title", ""),
                "stats": cached_entry["data"],
                "isFallback": True,
                "asOf": as_of_str,
                "reasonCode": reason_code,
                "warning": warning,
                "mode": "patched_fallback_cached",
            }

        # If no last-known-good cache exists, return honest degraded response without fake stats
        return {
            "courseId": course_id,
            "title": course.get("title", ""),
            "stats": None,
            "isFallback": True,
            "asOf": None,
            "reasonCode": reason_code,
            "warning": (
                f"{warning} Hiện chưa có dữ liệu đệm, "
                "hệ thống phản hồi ở mức suy giảm an toàn."
            ),
            "mode": "patched_fallback_degraded",
        }


# Blueprint registration
p6_dashboard_bp = Blueprint("p6_dashboard", __name__)


@p6_dashboard_bp.route("/courses/<course_id>/dashboard", methods=["GET"])
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def get_course_dashboard_endpoint(course_id: str) -> tuple[Response, int]:
    """Protected Dashboard endpoint applying Pattern #6: Timeout & Fallback.

    Accepts optional lab parameters:
    - baseline: 'true' to trigger unprotected mode (baseline lab for before-after testing)
    - delay_ms: simulated upstream delay in milliseconds
    - error: 'timeout' or 'connection' to simulate upstream faults
    """
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]

    # Read lab query params
    baseline_param = request.args.get("baseline", "").lower() in ("1", "true", "yes")
    delay_ms = request.args.get("delay_ms")
    delay_sec: float | None = None
    if delay_ms is not None:
        try:
            delay_sec = max(0.0, float(delay_ms) / 1000.0)
        except ValueError as exc:
            raise ValidationError("Tham số delay_ms phải là số nguyên hoặc số thực") from exc

    error_param = request.args.get("error")
    if error_param and error_param not in ("timeout", "connection"):
        raise ValidationError("Tham số error chỉ chấp nhận 'timeout' hoặc 'connection'")

    timeout_config = current_app.config.get("STATS_TIMEOUT_SECONDS", 1.0)

    dashboard_data = DashboardService.get_course_dashboard(
        actor=actor,
        course_id=course_id,
        store=store,
        timeout_seconds=float(timeout_config),
        delay_seconds=delay_sec,
        simulate_error=error_param,
        baseline_unprotected=baseline_param,
    )
    return jsonify(dashboard_data), 200


@p6_dashboard_bp.route("/courses/<course_id>/dashboard/baseline", methods=["GET"])
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def get_course_dashboard_baseline_endpoint(course_id: str) -> tuple[Response, int]:
    """Explicit baseline endpoint demonstrating vulnerable behavior without timeout/fallback."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]

    delay_ms = request.args.get("delay_ms", "3000")
    try:
        delay_sec = max(0.0, float(delay_ms) / 1000.0)
    except ValueError as exc:
        raise ValidationError("Tham số delay_ms phải là số") from exc

    dashboard_data = DashboardService.get_course_dashboard(
        actor=actor,
        course_id=course_id,
        store=store,
        delay_seconds=delay_sec,
        baseline_unprotected=True,
    )
    return jsonify(dashboard_data), 200


@p6_dashboard_bp.route("/api/lab/stats-mock/configure", methods=["POST"])
@require_role("ADMIN", "admin")
def configure_lab_stats_mock() -> tuple[Response, int]:
    """Admin-only endpoint to configure mock delay and faults for Burp Suite security audit."""
    if not request.is_json:
        raise ValidationError("Request body must be JSON")

    body = request.get_json(silent=False) or {}
    delay_ms = body.get("delay_ms")
    simulate_error = body.get("simulate_error")

    with _LAB_LOCK:
        if delay_ms is not None:
            _LAB_CONFIG["default_delay_seconds"] = max(0.0, float(delay_ms) / 1000.0)
        if "simulate_error" in body:
            _LAB_CONFIG["simulate_error"] = simulate_error

    return jsonify({"message": "Lab Stats Mock updated successfully", "config": _LAB_CONFIG}), 200
