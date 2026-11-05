"""Comprehensive test suite for Defensive Pattern #8: Transactional Outbox (O8-01 to O8-07)."""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app
from lms_project_1.patterns.p8_outbox import FakeEmailSender, OutboxWorker


@pytest.fixture
def app_instance() -> Any:
    """Create fresh application instance with isolated seed data."""
    app = create_app(
        {
            "JWT_SECRET": "pattern8_outbox_transaction_secret_key_32chars",
            "TOKEN_TTL_SECONDS": 900,
        }
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_instance: Any) -> FlaskClient:
    return app_instance.test_client()


def get_token(
    client: FlaskClient,
    email: str = "chi.sv@lms.test",
    password: str = "Lms@2026",
) -> str:
    """Helper to authenticate and retrieve Bearer token."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.get_json()}"
    body = resp.get_json()
    token = body.get("accessToken") or body.get("access_token")
    assert isinstance(token, str)
    return token


# O8-01: Atomic enrollment & outbox event creation
def test_o8_01_atomic_enrollment_and_outbox_event(client: FlaskClient, app_instance: Any) -> None:
    # Chi (u4) is not enrolled in c2 in seed.json
    chi_token = get_token(client, "chi.sv@lms.test")

    resp = client.post(
        "/courses/c2/enroll-with-outbox",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "outboxEventId" in data
    assert data["enrollment"]["courseId"] == "c2"

    # Verify both enrollment and outbox event are present in Store
    store = app_instance.config["STORE"]
    assert ("c2", "u4") in store.enrollments
    events = [e for e in store.outbox_events if e.get("id") == data["outboxEventId"]]
    assert len(events) == 1
    assert events[0]["status"] == "PENDING"
    assert events[0]["eventType"] == "ENROLLMENT_CONFIRMATION"


# O8-02: Duplicate enrollment blocked with 409; no duplicate outbox event added
def test_o8_02_duplicate_enrollment_rejected(client: FlaskClient, app_instance: Any) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    # First enrollment succeeds
    resp1 = client.post(
        "/courses/c2/enroll-with-outbox",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert resp1.status_code == 201

    store = app_instance.config["STORE"]
    initial_event_count = len(store.outbox_events)

    # Second enrollment must fail with 409 Conflict
    resp2 = client.post(
        "/courses/c2/enroll-with-outbox",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert resp2.status_code == 409
    assert resp2.get_json()["error"] == "CONFLICT"

    # No additional outbox events created
    assert len(store.outbox_events) == initial_event_count


# O8-03: Outbox worker processes pending events to PROCESSED
def test_o8_03_outbox_worker_processes_pending_events(
    client: FlaskClient, app_instance: Any
) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    client.post("/courses/c2/enroll-with-outbox", headers={"Authorization": f"Bearer {chi_token}"})

    store = app_instance.config["STORE"]
    custom_mailer = FakeEmailSender()

    summary = OutboxWorker.process_pending_events(store=store, email_sender=custom_mailer)
    assert summary["processed"] >= 1
    assert summary["pendingRemaining"] == 0

    # Verify email was actually dispatched
    assert len(custom_mailer.sent_emails) >= 1
    sent = custom_mailer.sent_emails[0]
    assert sent["to"] == "chi.sv@lms.test"
    assert sent["courseId"] == "c2"


# O8-04: Outbox worker handles mailer failures with retry and marks FAILED on max retries
def test_o8_04_worker_retry_and_dead_letter_on_failure(
    client: FlaskClient, app_instance: Any
) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    client.post(
        "/courses/c2/enroll-with-outbox",
        headers={"Authorization": f"Bearer {chi_token}"},
    )

    store = app_instance.config["STORE"]
    failing_mailer = FakeEmailSender()

    # Process with simulated failure 3 times (max_retries=3)
    for _ in range(3):
        OutboxWorker.process_pending_events(
            store=store,
            email_sender=failing_mailer,
            simulate_fail=True,
            max_retries=3,
        )

    # Event should transition to FAILED
    failed_events = [e for e in store.outbox_events if e.get("status") == "FAILED"]
    assert len(failed_events) >= 1
    assert failed_events[0]["retryCount"] >= 3
    assert "Max retries" in failed_events[0]["failedReason"]


# O8-05: Deduplication: re-running worker does not re-process already PROCESSED events
def test_o8_05_deduplication_processed_events_not_re_sent(
    client: FlaskClient, app_instance: Any
) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    client.post("/courses/c2/enroll-with-outbox", headers={"Authorization": f"Bearer {chi_token}"})

    store = app_instance.config["STORE"]
    custom_mailer = FakeEmailSender()

    # Run 1: processes the event
    summary1 = OutboxWorker.process_pending_events(store=store, email_sender=custom_mailer)
    assert summary1["processed"] == 1
    assert len(custom_mailer.sent_emails) == 1

    # Run 2: no pending events remain, no duplicate emails dispatched
    summary2 = OutboxWorker.process_pending_events(store=store, email_sender=custom_mailer)
    assert summary2["processed"] == 0
    assert len(custom_mailer.sent_emails) == 1


# O8-06: Secret redaction: event payload contains no passwords or secret tokens
def test_o8_06_secret_redaction_in_outbox_payload(client: FlaskClient, app_instance: Any) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    client.post("/courses/c2/enroll-with-outbox", headers={"Authorization": f"Bearer {chi_token}"})

    store = app_instance.config["STORE"]
    import json

    for event in store.outbox_events:
        payload_str = json.dumps(event.get("payload", {}))
        assert "password" not in payload_str
        assert "password_hash" not in payload_str
        assert "secret" not in payload_str.lower()
        assert "token" not in payload_str.lower()


# O8-07: Authorization: non-student or unauthenticated cannot trigger enrollment outbox
def test_o8_07_authorization_restrictions(client: FlaskClient) -> None:
    # 1. Instructor cannot enroll as student -> 403
    an_token = get_token(client, "an.gv@lms.test")
    resp_inst = client.post(
        "/courses/c2/enroll-with-outbox",
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert resp_inst.status_code == 403

    # 2. Unauthenticated request -> 401
    resp_unauth = client.post("/courses/c2/enroll-with-outbox")
    assert resp_unauth.status_code == 401
