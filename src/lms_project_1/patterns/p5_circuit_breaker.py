"""Defensive Pattern #5: Circuit Breaker for Assignment Plagiarism Checking.

This module implements:
1. CircuitBreaker: Self-implemented state machine (CLOSED, OPEN, HALF_OPEN)
   with thread-safe concurrency, failure threshold, cooldown timer, and probe testing.
2. FakePlagiarismProvider: Upstream checker adapter supporting fault/delay injection.
3. PlagiarismService: Enforces authentication, authorization, and fast-fail protection.
4. p5_circuit_breaker_bp: Blueprint exposing plagiarism check & circuit monitoring endpoints.
"""

from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, make_response, request

from lms_project_1.errors import Forbidden, NotFound, Unauthenticated, ValidationError
from lms_project_1.guards import require_role
from lms_project_1.store import Store


class CircuitState(enum.StrEnum):
    """The 3 states of the Circuit Breaker pattern."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class PlagiarismProviderError(Exception):
    """Base exception for external plagiarism provider issues."""


class PlagiarismProviderTimeout(PlagiarismProviderError):
    """Raised when external provider exceeds request deadline."""


class PlagiarismProviderDown(PlagiarismProviderError):
    """Raised when external provider returns 5xx or fails connection."""


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while circuit is in OPEN state."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CircuitBreaker:
    """Self-implemented, thread-safe Circuit Breaker state machine."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 5.0,
        half_open_probes: int = 1,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_probes = half_open_probes
        self._time_fn = time_fn or time.time

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.total_tripped_count = 0
        self.last_failure_time = 0.0
        self.successful_probes = 0
        self._lock = threading.Lock()

    def get_status(self) -> dict[str, Any]:
        """Inspect current circuit status safely."""
        with self._lock:
            # Check if cooldown has elapsed to show accurate anticipated state
            current_time = self._time_fn()
            effective_state = self.state
            if self.state == CircuitState.OPEN and (
                current_time - self.last_failure_time >= self.cooldown_seconds
            ):
                effective_state = CircuitState.HALF_OPEN

            remaining_cooldown = max(
                0.0,
                self.cooldown_seconds - (current_time - self.last_failure_time),
            )
            return {
                "state": effective_state.value,
                "consecutiveFailures": self.consecutive_failures,
                "failureThreshold": self.failure_threshold,
                "cooldownSeconds": self.cooldown_seconds,
                "remainingCooldown": round(remaining_cooldown, 2),
                "totalTrippedCount": self.total_tripped_count,
            }

    def reset(self) -> None:
        """Manually force reset the circuit breaker to CLOSED state."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
            self.successful_probes = 0
            self.last_failure_time = 0.0

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute protected function through the circuit breaker."""
        with self._lock:
            now = self._time_fn()

            # 1. State transition from OPEN to HALF_OPEN if cooldown expired
            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_failure_time
                if elapsed >= self.cooldown_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.successful_probes = 0
                else:
                    retry_after = round(self.cooldown_seconds - elapsed, 2)
                    raise CircuitBreakerOpenError(
                        "Circuit is OPEN (cooldown active). Fast failing call.",
                        retry_after=retry_after,
                    )

            # In HALF_OPEN, we only allow bounded probes
            if (
                self.state == CircuitState.HALF_OPEN
                and self.successful_probes >= self.half_open_probes
            ):
                raise CircuitBreakerOpenError(
                    "Circuit is HALF_OPEN and trial probe limit reached.",
                    retry_after=1.0,
                )

        # 2. Execute call outside lock to prevent blocking concurrent calls
        try:
            result = func(*args, **kwargs)
        except (PlagiarismProviderError, TimeoutError, ConnectionError) as exc:
            with self._lock:
                self.consecutive_failures += 1
                self.last_failure_time = self._time_fn()
                if (
                    self.state == CircuitState.HALF_OPEN
                    or self.consecutive_failures >= self.failure_threshold
                ):
                    self.state = CircuitState.OPEN
                    self.total_tripped_count += 1
            raise exc

        # 3. Handle success
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.successful_probes += 1
                if self.successful_probes >= self.half_open_probes:
                    # Recovery: return to CLOSED
                    self.state = CircuitState.CLOSED
                    self.consecutive_failures = 0
                    self.successful_probes = 0
            elif self.state == CircuitState.CLOSED:
                self.consecutive_failures = 0

        return result


class FakePlagiarismProvider:
    """Simulated external plagiarism detection provider."""

    def check_similarity(
        self,
        submission_id: str,
        content: str,
        simulate_error: str | None = None,
        delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """Run similarity analysis on submission text."""
        if delay_seconds > 0.0:
            time.sleep(delay_seconds)

        if simulate_error == "timeout":
            raise PlagiarismProviderTimeout("External plagiarism detection engine timed out")
        if simulate_error in ("down", "500", "error"):
            raise PlagiarismProviderDown("External plagiarism detection service returned HTTP 503")

        # Deterministic honest similarity score calculation
        content_len = len(content.strip())
        similarity = min(85.0, round((content_len % 37) * 2.1, 1))

        status = "FLAGGED" if similarity > 50.0 else "CLEAN"
        return {
            "submissionId": submission_id,
            "similarityScore": similarity,
            "status": status,
            "checkedAt": datetime.now(UTC).isoformat(),
            "provider": "MockPlagiarismEngine-v2",
        }


# Global singleton breaker instance for plagiarism checking
_PLAGIARISM_BREAKER = CircuitBreaker(failure_threshold=3, cooldown_seconds=5.0)
_PLAGIARISM_PROVIDER = FakePlagiarismProvider()


class PlagiarismService:
    """Service mediating plagiarism analysis with RBAC & Circuit Breaker."""

    @classmethod
    def check_submission(
        cls,
        actor: dict[str, Any],
        course_id: str,
        submission_id: str,
        store: Store,
        breaker: CircuitBreaker | None = None,
        provider: FakePlagiarismProvider | None = None,
        simulate_error: str | None = None,
        delay_seconds: float = 0.0,
    ) -> dict[str, Any]:
        """Validate permissions and invoke plagiarism checker via circuit breaker."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        # 1. Course Existence Check (404)
        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        # 2. Submission Existence Check (404)
        submission = store.get_submission_by_id(submission_id)
        if submission is None:
            raise NotFound(f"Submission '{submission_id}' not found")

        # Ensure submission belongs to course
        sub_course_id = submission.get("courseId") or submission.get("course_id")
        if sub_course_id and sub_course_id != course_id:
            raise NotFound(f"Submission '{submission_id}' does not belong to course '{course_id}'")

        # 3. Object-level Authorization (403)
        role = str(actor.get("role", "")).upper()
        actor_id = str(actor.get("id", ""))

        if role == "ADMIN":
            pass
        elif role in ("INSTRUCTOR", "TEACHER"):
            inst_id = course.get("instructorId") or course.get("instructor_id")
            if inst_id != actor_id:
                raise Forbidden("Giảng viên không phụ trách khóa học này")
        elif role == "STUDENT":
            student_id = submission.get("studentId") or submission.get("student_id")
            if student_id != actor_id:
                raise Forbidden("Sinh viên chỉ có thể kiểm tra đạo văn bài nộp của chính mình")
        else:
            raise Forbidden("Vai trò không có quyền kiểm tra đạo văn")

        # 4. Invoke through Circuit Breaker
        active_breaker = breaker or _PLAGIARISM_BREAKER
        active_provider = provider or _PLAGIARISM_PROVIDER
        content = str(submission.get("content", ""))

        return active_breaker.call(
            active_provider.check_similarity,
            submission_id=submission_id,
            content=content,
            simulate_error=simulate_error,
            delay_seconds=delay_seconds,
        )


# Blueprint definition
p5_circuit_breaker_bp = Blueprint("p5_circuit_breaker", __name__)


@p5_circuit_breaker_bp.route(
    "/courses/<course_id>/submissions/<submission_id>/plagiarism-check",
    methods=["POST"],
)
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def post_check_plagiarism(course_id: str, submission_id: str) -> tuple[Response, int]:
    """Endpoint for submission plagiarism analysis with circuit breaker fast-fail protection."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]

    # Read optional test/fault injection params
    body = request.get_json(silent=True) or {}
    simulate_error = body.get("simulate_error") or request.args.get("error")
    delay_ms = body.get("delay_ms") or request.args.get("delay_ms")
    delay_sec = 0.0
    if delay_ms is not None:
        try:
            delay_sec = max(0.0, float(delay_ms) / 1000.0)
        except ValueError as exc:
            raise ValidationError("delay_ms phải là số") from exc

    breaker: CircuitBreaker = current_app.config.get("PLAGIARISM_BREAKER", _PLAGIARISM_BREAKER)

    try:
        report = PlagiarismService.check_submission(
            actor=actor,
            course_id=course_id,
            submission_id=submission_id,
            store=store,
            breaker=breaker,
            simulate_error=simulate_error,
            delay_seconds=delay_sec,
        )
        return jsonify(report), 200

    except CircuitBreakerOpenError as exc:
        # Fast-fail response: 503 Service Unavailable with Retry-After
        resp = make_response(
            jsonify(
                {
                    "error": "SERVICE_UNAVAILABLE",
                    "circuitState": "OPEN",
                    "message": str(exc),
                    "retryAfterSeconds": exc.retry_after,
                }
            ),
            503,
        )
        resp.headers["Retry-After"] = str(int(max(1, exc.retry_after)))
        return resp

    except (PlagiarismProviderError, TimeoutError, ConnectionError) as exc:
        # Upstream fault captured before breaker tripped
        return (
            jsonify(
                {
                    "error": "UPSTREAM_FAILURE",
                    "message": f"Dịch vụ kiểm tra đạo văn gặp sự cố: {exc}",
                    "circuitStatus": breaker.get_status(),
                }
            ),
            502,
        )


@p5_circuit_breaker_bp.route(
    "/courses/<course_id>/submissions/<submission_id>/plagiarism-breaker/status",
    methods=["GET"],
)
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def get_breaker_status(course_id: str, submission_id: str) -> tuple[Response, int]:
    """Inspect the current health and metrics of the plagiarism circuit breaker."""
    breaker: CircuitBreaker = current_app.config.get("PLAGIARISM_BREAKER", _PLAGIARISM_BREAKER)
    return jsonify(breaker.get_status()), 200


@p5_circuit_breaker_bp.route("/api/lab/plagiarism-breaker/reset", methods=["POST"])
@require_role("ADMIN", "admin")
def post_reset_breaker() -> tuple[Response, int]:
    """Admin-only endpoint to reset the circuit breaker state for testing."""
    breaker: CircuitBreaker = current_app.config.get("PLAGIARISM_BREAKER", _PLAGIARISM_BREAKER)
    breaker.reset()
    return (
        jsonify(
            {
                "message": "Circuit breaker successfully reset to CLOSED",
                "status": breaker.get_status(),
            }
        ),
        200,
    )
