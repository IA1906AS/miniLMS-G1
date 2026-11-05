"""Defensive Pattern #7: State Machine for Quiz Attempt Lifecycle.

This module implements:
1. AttemptState: Finite state machine with valid transitions
   (CREATED -> IN_PROGRESS -> SUBMITTED / EXPIRED).
2. QuizStateMachineService: Enforces transition rules, atomic state updates,
   ownership checks, and strict deadline enforcement.
3. p7_quiz_bp: Blueprint exposing full quiz attempt lifecycle endpoints.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, request

from lms_project_1.errors import (
    ConflictError,
    Forbidden,
    NotFound,
    Unauthenticated,
    ValidationError,
)
from lms_project_1.guards import require_role
from lms_project_1.store import Store


class AttemptState(enum.StrEnum):
    """Permitted states for a quiz attempt."""

    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"


# Permitted transition table
VALID_TRANSITIONS: dict[AttemptState, set[AttemptState]] = {
    AttemptState.CREATED: {
        AttemptState.IN_PROGRESS,
        AttemptState.SUBMITTED,
        AttemptState.EXPIRED,
    },
    AttemptState.IN_PROGRESS: {
        AttemptState.IN_PROGRESS,  # idempotently updating answers
        AttemptState.SUBMITTED,
        AttemptState.EXPIRED,
    },
    AttemptState.SUBMITTED: set(),  # Terminal state
    AttemptState.EXPIRED: set(),  # Terminal state
}


class QuizStateMachineService:
    """Core service managing the lifecycle and security bounds of quiz attempts."""

    DEFAULT_DURATION_SECONDS = 1800  # 30 minutes

    @classmethod
    def create_attempt(
        cls,
        actor: dict[str, Any],
        quiz_id: str,
        store: Store,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Initialize a new quiz attempt for the authenticated student."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        role = str(actor.get("role", "")).upper()
        if role != "STUDENT":
            raise Forbidden("Chỉ sinh viên mới có thể bắt đầu làm bài kiểm tra")

        student_id = str(actor.get("id", ""))
        attempt_id = f"qa_{uuid.uuid4().hex[:12]}"

        duration = (
            duration_seconds if duration_seconds is not None else cls.DEFAULT_DURATION_SECONDS
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=duration)

        with store.quiz_attempts_lock:
            # Check for existing active attempt to prevent uncontrolled multi-attempt racing
            for existing in store.quiz_attempts.values():
                if (
                    existing.get("quiz_id") == quiz_id
                    and existing.get("student_id") == student_id
                    and existing.get("state") in (AttemptState.CREATED, AttemptState.IN_PROGRESS)
                ):
                    # Check if actually expired
                    if now < existing.get("expires_at", now):
                        return existing
                    else:
                        existing["state"] = AttemptState.EXPIRED

            attempt_record: dict[str, Any] = {
                "id": attempt_id,
                "quiz_id": quiz_id,
                "student_id": student_id,
                "state": AttemptState.CREATED,
                "answers": {},
                "score": None,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "submitted_at": None,
            }
            store.quiz_attempts[attempt_id] = attempt_record

        return attempt_record

    @classmethod
    def get_attempt(
        cls,
        actor: dict[str, Any],
        quiz_id: str,
        attempt_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Fetch attempt details, verifying ownership or instructor privileges."""
        attempt = cls._get_and_authorize(actor, quiz_id, attempt_id, store)
        cls._check_and_expire(attempt)
        return attempt

    @classmethod
    def save_answers(
        cls,
        actor: dict[str, Any],
        quiz_id: str,
        attempt_id: str,
        answers: dict[str, Any],
        store: Store,
    ) -> dict[str, Any]:
        """Save answers during IN_PROGRESS state. Disallows mutation after SUBMITTED or EXPIRED."""
        attempt = cls._get_and_authorize(actor, quiz_id, attempt_id, store)

        with store.quiz_attempts_lock:
            cls._check_and_expire(attempt)
            current_state = AttemptState(attempt["state"])

            if current_state == AttemptState.SUBMITTED:
                raise ConflictError("Không thể chỉnh sửa bài kiểm tra đã nộp (SUBMITTED)")
            if current_state == AttemptState.EXPIRED:
                raise ConflictError("Bài kiểm tra đã hết hạn thời gian làm bài (EXPIRED)")

            # Transition CREATED -> IN_PROGRESS on first answer submission
            if current_state == AttemptState.CREATED:
                attempt["state"] = AttemptState.IN_PROGRESS

            attempt["answers"].update(answers)
            attempt["updated_at"] = datetime.now(UTC).isoformat()

        return attempt

    @classmethod
    def submit_attempt(
        cls,
        actor: dict[str, Any],
        quiz_id: str,
        attempt_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Finalize and submit the quiz attempt. State becomes terminal SUBMITTED."""
        attempt = cls._get_and_authorize(actor, quiz_id, attempt_id, store)

        with store.quiz_attempts_lock:
            cls._check_and_expire(attempt)
            current_state = AttemptState(attempt["state"])

            if current_state == AttemptState.SUBMITTED:
                raise ConflictError("Bài kiểm tra này đã được nộp trước đó")
            if current_state == AttemptState.EXPIRED:
                raise ConflictError("Bài kiểm tra đã hết hạn (EXPIRED), không thể nộp bài")

            # Permitted transition to terminal SUBMITTED
            attempt["state"] = AttemptState.SUBMITTED
            now = datetime.now(UTC)
            attempt["submitted_at"] = now.isoformat()

            # Deterministic scoring based on answers count
            answers = attempt.get("answers", {})
            total_questions = max(len(answers), 5)
            correct_count = sum(1 for v in answers.values() if v in ("A", "true", 1, "correct"))
            attempt["score"] = round((correct_count / total_questions) * 10.0, 1)

        return attempt

    @classmethod
    def _get_and_authorize(
        cls,
        actor: dict[str, Any],
        quiz_id: str,
        attempt_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Retrieve attempt and verify user has permission to interact with it."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        with store.quiz_attempts_lock:
            attempt = store.quiz_attempts.get(attempt_id)

        if attempt is None or attempt.get("quiz_id") != quiz_id:
            raise NotFound(f"Lượt làm bài '{attempt_id}' không tồn tại cho bài quiz '{quiz_id}'")

        role = str(actor.get("role", "")).upper()
        actor_id = str(actor.get("id", ""))

        if role == "ADMIN":
            return attempt
        if role in ("INSTRUCTOR", "TEACHER"):
            return attempt
        if role == "STUDENT":
            if attempt.get("student_id") != actor_id:
                raise Forbidden("Sinh viên không thể thao tác trên bài thi của người khác")
            return attempt

        raise Forbidden("Vai trò không hợp lệ")

    @classmethod
    def _check_and_expire(cls, attempt: dict[str, Any]) -> None:
        """Mutate state to EXPIRED if wall-clock time passed deadline and not already SUBMITTED."""
        if attempt.get("state") == AttemptState.SUBMITTED:
            return

        expires_at_str = attempt.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(UTC) >= expires_at:
                attempt["state"] = AttemptState.EXPIRED


# Blueprint registration
p7_quiz_bp = Blueprint("p7_quiz", __name__)


@p7_quiz_bp.route("/quizzes/<quiz_id>/attempts", methods=["POST"])
@require_role("STUDENT", "student")
def post_start_quiz_attempt(quiz_id: str) -> tuple[Response, int]:
    """Start or retrieve an active quiz attempt for the student."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]
    body = request.get_json(silent=True) or {}
    duration = body.get("duration_seconds")

    attempt = QuizStateMachineService.create_attempt(
        actor=actor,
        quiz_id=quiz_id,
        store=store,
        duration_seconds=int(duration) if duration else None,
    )
    return jsonify(attempt), 201


@p7_quiz_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>", methods=["GET"])
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def get_quiz_attempt_details(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """View status, answers, and score for a quiz attempt."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    attempt = QuizStateMachineService.get_attempt(
        actor=actor,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        store=store,
    )
    return jsonify(attempt), 200


@p7_quiz_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>/answers", methods=["PUT"])
@require_role("STUDENT", "student")
def put_quiz_answers(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """Save answers while attempt is in CREATED or IN_PROGRESS state."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    if not request.is_json:
        raise ValidationError("Request body must be JSON")
    body = request.get_json(silent=False) or {}
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise ValidationError("Trường 'answers' phải là một dictionary/object câu trả lời")

    attempt = QuizStateMachineService.save_answers(
        actor=actor,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        answers=answers,
        store=store,
    )
    return jsonify(attempt), 200


@p7_quiz_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>/submit", methods=["POST"])
@require_role("STUDENT", "student")
def post_submit_quiz_attempt(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """Submit the quiz attempt. Irreversible transition to SUBMITTED."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    attempt = QuizStateMachineService.submit_attempt(
        actor=actor,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        store=store,
    )
    return jsonify({"message": "Nộp bài kiểm tra thành công", "attempt": attempt}), 200
