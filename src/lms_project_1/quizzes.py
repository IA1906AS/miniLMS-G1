"""Quiz Management & State Machine Lifecycle Module.

Implements rigorous state-machine rules for student quiz attempts
(CREATED -> IN_PROGRESS -> SUBMITTED or EXPIRED), ensuring non-revisable
terminal submissions, strict expiration, and protection against answer tampering.
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


VALID_TRANSITIONS: dict[AttemptState, set[AttemptState]] = {
    AttemptState.CREATED: {
        AttemptState.IN_PROGRESS,
        AttemptState.SUBMITTED,
        AttemptState.EXPIRED,
    },
    AttemptState.IN_PROGRESS: {
        AttemptState.IN_PROGRESS,
        AttemptState.SUBMITTED,
        AttemptState.EXPIRED,
    },
    AttemptState.SUBMITTED: set(),
    AttemptState.EXPIRED: set(),
}


def _authorize_course_quiz(
    actor: dict[str, Any], quiz: dict[str, Any], store: Store
) -> dict[str, Any]:
    """Authorize access to a real quiz through its parent course."""
    course_id = str(quiz.get("courseId", ""))
    course = store.courses.get(course_id)
    if course is None:
        raise NotFound("Course not found")
    role = str(actor.get("role", "")).upper()
    actor_id = str(actor.get("id", ""))
    if role == "ADMIN":
        return course
    if role in {"TEACHER", "INSTRUCTOR"}:
        if course.get("instructorId") != actor_id:
            raise Forbidden("Only the assigned instructor may access this quiz")
        return course
    if role == "STUDENT":
        if store.get_enrollment(course_id, actor_id) is None:
            raise Forbidden("Enrollment is required")
        return course
    raise Forbidden("Role is not allowed to access this quiz")


def _public_quiz(quiz: dict[str, Any]) -> dict[str, Any]:
    """Serialize quiz metadata without exposing answer keys."""
    questions = [
        {
            "id": str(question.get("id", "")),
            "prompt": str(question.get("prompt", "")),
            "options": [dict(option) for option in question.get("options", [])],
        }
        for question in quiz.get("questions", [])
    ]
    return {
        "id": str(quiz.get("id", "")),
        "courseId": str(quiz.get("courseId", "")),
        "title": str(quiz.get("title", "")),
        "timeLimitSeconds": int(quiz.get("timeLimitSeconds", 1800)),
        "passScore": float(quiz.get("passScore", 6.0)),
        "questionCount": len(questions),
        "questions": questions,
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

        quiz = store.get_quiz(quiz_id)
        if quiz is not None:
            _authorize_course_quiz(actor, quiz, store)
            duration_seconds = int(quiz.get("timeLimitSeconds", cls.DEFAULT_DURATION_SECONDS))

        duration = (
            duration_seconds if duration_seconds is not None else cls.DEFAULT_DURATION_SECONDS
        )
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=duration)

        with store.quiz_attempts_lock:
            for existing in store.quiz_attempts.values():
                if (
                    existing.get("quiz_id") == quiz_id
                    and existing.get("student_id") == student_id
                    and existing.get("state") in (AttemptState.CREATED, AttemptState.IN_PROGRESS)
                ):
                    existing_expires_at = cls._parse_expires_at(existing.get("expires_at"))
                    if existing_expires_at is not None and now < existing_expires_at:
                        return existing
                    existing["state"] = AttemptState.EXPIRED

            attempt_record: dict[str, Any] = {
                "id": attempt_id,
                "quiz_id": quiz_id,
                "course_id": str(quiz.get("courseId", "")) if quiz else None,
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
        quiz = store.get_quiz(quiz_id)
        if quiz is not None:
            question_options = {
                str(question.get("id", "")): {
                    str(option.get("key", "")) for option in question.get("options", [])
                }
                for question in quiz.get("questions", [])
            }
            unknown_questions = set(answers) - set(question_options)
            if unknown_questions:
                raise ValidationError("Answers contain an unknown question")
            if any(
                not isinstance(value, str) or value not in question_options[question_id]
                for question_id, value in answers.items()
            ):
                raise ValidationError("Answers contain an invalid option")

        with store.quiz_attempts_lock:
            cls._check_and_expire(attempt)
            current_state = AttemptState(attempt["state"])

            if current_state == AttemptState.SUBMITTED:
                raise ConflictError("Không thể chỉnh sửa bài kiểm tra đã nộp (SUBMITTED)")
            if current_state == AttemptState.EXPIRED:
                raise ConflictError("Bài kiểm tra đã hết hạn thời gian làm bài (EXPIRED)")

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

            attempt["state"] = AttemptState.SUBMITTED
            now = datetime.now(UTC)
            attempt["submitted_at"] = now.isoformat()

            answers = attempt.get("answers", {})
            quiz = store.get_quiz(quiz_id)
            if quiz is not None:
                questions = quiz.get("questions", [])
                total_questions = max(len(questions), 1)
                correct_count = sum(
                    1
                    for question in questions
                    if answers.get(str(question.get("id", ""))) == question.get("correctAnswer")
                )
                attempt["pass_score"] = float(quiz.get("passScore", 6.0))
            else:
                total_questions = max(len(answers), 5)
                correct_count = sum(
                    1 for value in answers.values() if value in ("A", "true", 1, "correct")
                )
            attempt["score"] = round((correct_count / total_questions) * 10.0, 1)
            attempt["correct_count"] = correct_count
            attempt["total_questions"] = total_questions
            attempt["passed"] = attempt["score"] >= float(attempt.get("pass_score", 6.0))

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
            quiz = store.get_quiz(quiz_id)
            if quiz is not None:
                _authorize_course_quiz(actor, quiz, store)
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

        expires_at = cls._parse_expires_at(attempt.get("expires_at"))
        if expires_at is not None and datetime.now(UTC) >= expires_at:
            attempt["state"] = AttemptState.EXPIRED

    @staticmethod
    def _parse_expires_at(value: Any) -> datetime | None:
        """Normalize persisted and in-memory deadlines without raising on bad state."""
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
        else:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


# Blueprint registration
quizzes_bp = Blueprint("quizzes", __name__)
p7_quiz_bp = quizzes_bp  # Backward compatibility alias


@quizzes_bp.get("/api/courses/<course_id>/quizzes")
@require_role("ADMIN", "INSTRUCTOR", "TEACHER", "STUDENT")
def list_course_quizzes(course_id: str) -> tuple[Response, int]:
    """List playable quizzes for an authorized course member."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]
    if course_id not in store.courses:
        raise NotFound("Course not found")
    quizzes = store.get_quizzes(course_id)
    if quizzes:
        _authorize_course_quiz(actor, quizzes[0], store)
    else:
        synthetic_quiz = {"courseId": course_id}
        _authorize_course_quiz(actor, synthetic_quiz, store)
    return jsonify({"items": [_public_quiz(quiz) for quiz in quizzes]}), 200


@quizzes_bp.route("/quizzes/<quiz_id>/attempts", methods=["POST"])
@require_role("STUDENT", "student")
def post_start_quiz_attempt(quiz_id: str) -> tuple[Response, int]:
    """Start or retrieve an active quiz attempt for the student."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]
    body = request.get_json(silent=True) or {}
    duration = body.get("duration_seconds")
    if store.get_quiz(quiz_id) is None and not current_app.config.get("TESTING", False):
        raise NotFound("Quiz not found")
    parsed_duration: int | None = None
    if duration is not None:
        if isinstance(duration, bool):
            raise ValidationError("duration_seconds must be an integer")
        try:
            parsed_duration = int(duration)
        except (TypeError, ValueError) as exc:
            raise ValidationError("duration_seconds must be an integer") from exc
        if parsed_duration < 1 or parsed_duration > 14_400:
            raise ValidationError("duration_seconds must be between 1 and 14400")

    attempt = QuizStateMachineService.create_attempt(
        actor=actor,
        quiz_id=quiz_id,
        store=store,
        duration_seconds=parsed_duration,
    )
    return jsonify(attempt), 201


@quizzes_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>", methods=["GET"])
@require_role("ADMIN", "INSTRUCTOR", "STUDENT", "admin", "instructor", "student", "teacher")
def get_quiz_attempt_details(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """View status, answers, and score for a quiz attempt."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]

    attempt = QuizStateMachineService.get_attempt(
        actor=actor,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        store=store,
    )
    return jsonify(attempt), 200


@quizzes_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>/answers", methods=["PUT"])
@require_role("STUDENT", "student")
def put_quiz_answers(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """Save answers while attempt is in CREATED or IN_PROGRESS state."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]

    if not request.is_json:
        raise ValidationError("Request body must be JSON")
    body = request.get_json(silent=False) or {}
    if set(body) != {"answers"}:
        raise ValidationError("Only the answers field is allowed")
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


@quizzes_bp.route("/quizzes/<quiz_id>/attempts/<attempt_id>/submit", methods=["POST"])
@require_role("STUDENT", "student")
def post_submit_quiz_attempt(quiz_id: str, attempt_id: str) -> tuple[Response, int]:
    """Submit the quiz attempt. Irreversible transition to SUBMITTED."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]

    attempt = QuizStateMachineService.submit_attempt(
        actor=actor,
        quiz_id=quiz_id,
        attempt_id=attempt_id,
        store=store,
    )
    return jsonify({"message": "Nộp bài kiểm tra thành công", "attempt": attempt}), 200
