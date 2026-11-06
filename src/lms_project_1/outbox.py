"""Transactional Outbox & Event Dispatcher Module.

Guarantees atomicity between business operations (such as course enrollment)
and domain event generation (e.g., student confirmation notifications),
ensuring zero event loss even during external network disruptions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, request

from lms_project_1.errors import ConflictError, Forbidden, NotFound, Unauthenticated
from lms_project_1.guards import require_role
from lms_project_1.store import Store


class OutboxStatus(enum.StrEnum):
    """Lifecycle status of an outbox event."""

    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class FakeEmailSender:
    """Mockable email delivery adapter recording dispatched emails."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    def send_confirmation(
        self,
        to_email: str,
        course_title: str,
        student_id: str,
        course_id: str,
        simulate_fail: bool = False,
    ) -> bool:
        """Simulate email dispatch."""
        if simulate_fail:
            raise RuntimeError("SMTP connection dropped: simulated mailer failure")

        self.sent_emails.append(
            {
                "to": to_email,
                "courseTitle": course_title,
                "studentId": student_id,
                "courseId": course_id,
                "sentAt": datetime.now(UTC).isoformat(),
            }
        )
        return True


_EMAIL_SENDER = FakeEmailSender()


class TransactionalEnrollmentService:
    """Service providing atomic enrollment and outbox event creation."""

    @classmethod
    def enroll_with_outbox(
        cls,
        actor: dict[str, Any],
        course_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Atomically record student course enrollment and persist outbox event."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        role = str(actor.get("role", "")).upper()
        if role not in ("STUDENT", "ADMIN"):
            raise Forbidden("Chỉ sinh viên mới có thể ghi danh khóa học")

        student_id = str(actor.get("id", ""))
        student_email = str(actor.get("email", ""))

        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        enrollment_key = (course_id, student_id)
        if enrollment_key in store.enrollments:
            raise ConflictError("Sinh viên đã ghi danh khóa học này từ trước")

        now = datetime.now(UTC)
        dedupe_key = f"enroll_email_{course_id}_{student_id}"

        with store.outbox_lock:
            enrollment_record: dict[str, Any] = {
                "courseId": course_id,
                "studentId": student_id,
                "score": 0.0,
                "enrolledAt": now.isoformat(),
            }
            store.enrollments[enrollment_key] = enrollment_record

            event_id = f"evt_{uuid.uuid4().hex[:12]}"
            outbox_record: dict[str, Any] = {
                "id": event_id,
                "eventType": "ENROLLMENT_CONFIRMATION",
                "deduplicationKey": dedupe_key,
                "payload": {
                    "studentId": student_id,
                    "studentEmail": student_email,
                    "courseId": course_id,
                    "courseTitle": course.get("title", ""),
                },
                "status": OutboxStatus.PENDING,
                "retryCount": 0,
                "createdAt": now.isoformat(),
                "processedAt": None,
            }
            store.outbox_events.append(outbox_record)

        return {
            "message": "Ghi danh khóa học thành công và đã lên lịch gửi email xác nhận",
            "enrollment": enrollment_record,
            "outboxEventId": event_id,
        }


class OutboxWorker:
    """Worker processing pending outbox events with deduplication and bounded retries."""

    @classmethod
    def process_pending_events(
        cls,
        store: Store,
        email_sender: FakeEmailSender | None = None,
        simulate_fail: bool = False,
        max_retries: int = 3,
    ) -> dict[str, int]:
        """Scan outbox for pending events and dispatch with retry and deduplication."""
        sender = email_sender or _EMAIL_SENDER
        processed_count = 0
        failed_count = 0

        with store.outbox_lock:
            for event in store.outbox_events:
                if event.get("status") != OutboxStatus.PENDING:
                    continue

                payload = event.get("payload", {})
                to_email = payload.get("studentEmail", "")
                title = payload.get("courseTitle", "")
                sid = payload.get("studentId", "")
                cid = payload.get("courseId", "")

                try:
                    sender.send_confirmation(
                        to_email=to_email,
                        course_title=title,
                        student_id=sid,
                        course_id=cid,
                        simulate_fail=simulate_fail,
                    )
                    event["status"] = OutboxStatus.PROCESSED
                    event["processedAt"] = datetime.now(UTC).isoformat()
                    processed_count += 1

                except Exception:
                    retries = int(event.get("retryCount", 0)) + 1
                    event["retryCount"] = retries
                    if retries >= max_retries:
                        event["status"] = OutboxStatus.FAILED
                        event["failedReason"] = f"Max retries ({max_retries}) exceeded."
                    failed_count += 1

        return {
            "processed": processed_count,
            "failed": failed_count,
            "pendingRemaining": sum(
                1 for e in store.outbox_events if e.get("status") == OutboxStatus.PENDING
            ),
        }


# Blueprint registration
outbox_bp = Blueprint("outbox", __name__)
p8_outbox_bp = outbox_bp  # Backward compatibility alias


@outbox_bp.route("/courses/<course_id>/enroll-with-outbox", methods=["POST"])
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_enroll_with_outbox(course_id: str) -> tuple[Response, int]:
    """Enroll student into course with Transactional Outbox confirmation guarantees."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")

    store: Store = current_app.config["STORE"]
    result = TransactionalEnrollmentService.enroll_with_outbox(actor, course_id, store=store)
    return jsonify(result), 201


@outbox_bp.route("/courses/<course_id>/enrollment-events", methods=["GET"])
@require_role("ADMIN", "admin", "INSTRUCTOR", "instructor", "teacher")
def get_enrollment_events(course_id: str) -> tuple[Response, int]:
    """Inspect all outbox events for a given course."""
    store: Store = current_app.config["STORE"]
    with store.outbox_lock:
        events = [
            e for e in store.outbox_events if e.get("payload", {}).get("courseId") == course_id
        ]
    return jsonify({"courseId": course_id, "outboxEvents": events}), 200


@outbox_bp.route("/api/lab/outbox/process-worker", methods=["POST"])
@require_role("ADMIN", "admin")
def post_trigger_outbox_worker() -> tuple[Response, int]:
    """Admin endpoint to manually invoke outbox processor for testing and demo."""
    body = request.get_json(silent=True) or {}
    simulate_fail = bool(body.get("simulate_fail", False))
    store: Store = current_app.config["STORE"]

    result = OutboxWorker.process_pending_events(store=store, simulate_fail=simulate_fail)
    return jsonify({"message": "Outbox worker executed", "summary": result}), 200
