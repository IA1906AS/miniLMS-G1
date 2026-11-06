"""Comprehensive test suite for Defensive Pattern #7: Quiz State Machine (S7-01 to S7-07)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app


@pytest.fixture
def app_instance() -> Any:
    """Create fresh application instance with isolated seed data."""
    app = create_app(
        {
            "JWT_SECRET": "pattern7_quiz_state_machine_secret_key_32chars",
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


# S7-01: Normal Lifecycle: CREATED -> IN_PROGRESS -> SUBMITTED
def test_s7_01_normal_quiz_attempt_lifecycle(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    # 1. Start Attempt (CREATED)
    start_resp = client.post(
        "/quizzes/q1/attempts",
        json={"duration_seconds": 60},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert start_resp.status_code == 201
    attempt = start_resp.get_json()
    attempt_id = attempt["id"]
    assert attempt["state"] == "CREATED"
    assert attempt["quiz_id"] == "q1"

    # 2. Save Answers (transitions to IN_PROGRESS)
    save_resp = client.put(
        f"/quizzes/q1/attempts/{attempt_id}/answers",
        json={"answers": {"q1": "A", "q2": "B"}},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert save_resp.status_code == 200
    saved_attempt = save_resp.get_json()
    assert saved_attempt["state"] == "IN_PROGRESS"
    assert saved_attempt["answers"]["q1"] == "A"

    # 3. Final Submit (transitions to terminal SUBMITTED)
    submit_resp = client.post(
        f"/quizzes/q1/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert submit_resp.status_code == 200
    sub_data = submit_resp.get_json()["attempt"]
    assert sub_data["state"] == "SUBMITTED"
    assert sub_data["submitted_at"] is not None
    assert sub_data["score"] is not None


# S7-02: Modifying answers after submission is rejected with 409 Conflict
def test_s7_02_modify_answers_after_submission_blocked(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    # Start and submit attempt
    start = client.post(
        "/quizzes/q2/attempts",
        json={"duration_seconds": 60},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    client.post(
        f"/quizzes/q2/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {chi_token}"},
    )

    # Try modifying answers post-submission
    tamper_resp = client.put(
        f"/quizzes/q2/attempts/{attempt_id}/answers",
        json={"answers": {"q1": "C"}},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert tamper_resp.status_code == 409
    assert tamper_resp.get_json()["error"] == "CONFLICT"


# S7-03: Double submission is rejected with 409 Conflict
def test_s7_03_double_submit_rejected(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    start = client.post(
        "/quizzes/q3/attempts",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    # First submit succeeds
    sub1 = client.post(
        f"/quizzes/q3/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert sub1.status_code == 200

    # Second submit must fail with 409
    sub2 = client.post(
        f"/quizzes/q3/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert sub2.status_code == 409
    assert sub2.get_json()["error"] == "CONFLICT"


# S7-04: Submitting or saving after duration expires transitions to EXPIRED & 409 Conflict
def test_s7_04_expired_attempt_blocked(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    # Start with short duration (1 second)
    start = client.post(
        "/quizzes/q4/attempts",
        json={"duration_seconds": 1},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    # Wait for expiry
    time.sleep(1.2)

    # Try submitting expired attempt
    submit_resp = client.post(
        f"/quizzes/q4/attempts/{attempt_id}/submit",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert submit_resp.status_code == 409
    assert submit_resp.get_json()["error"] == "CONFLICT"

    # Details inspection shows EXPIRED state
    detail = client.get(
        f"/quizzes/q4/attempts/{attempt_id}",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert detail.get_json()["state"] == "EXPIRED"


# S7-05: IDOR Protection: Student B cannot view or tamper with Student A's attempt
def test_s7_05_idor_protection_between_students(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    dung_token = get_token(client, "dung.sv@lms.test")

    # Chi starts attempt
    start = client.post(
        "/quizzes/q5/attempts",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    # Dung tries to view Chi's attempt
    view_resp = client.get(
        f"/quizzes/q5/attempts/{attempt_id}",
        headers={"Authorization": f"Bearer {dung_token}"},
    )
    assert view_resp.status_code == 403
    assert view_resp.get_json()["error"] == "FORBIDDEN"

    # Dung tries to save answers into Chi's attempt
    tamper_resp = client.put(
        f"/quizzes/q5/attempts/{attempt_id}/answers",
        json={"answers": {"hacked": "true"}},
        headers={"Authorization": f"Bearer {dung_token}"},
    )
    assert tamper_resp.status_code == 403
    assert tamper_resp.get_json()["error"] == "FORBIDDEN"


# S7-06: Instructor and Admin can view attempts for oversight
def test_s7_06_instructor_and_admin_view_attempt(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")
    an_token = get_token(client, "an.gv@lms.test")
    admin_token = get_token(client, "admin@lms.test")

    start = client.post(
        "/quizzes/q6/attempts",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    # Instructor views
    inst_resp = client.get(
        f"/quizzes/q6/attempts/{attempt_id}",
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert inst_resp.status_code == 200
    assert inst_resp.get_json()["id"] == attempt_id

    # Admin views
    admin_resp = client.get(
        f"/quizzes/q6/attempts/{attempt_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.get_json()["id"] == attempt_id


# S7-07: Validation Error for malformed payloads
def test_s7_07_validation_error_on_invalid_answers_payload(client: FlaskClient) -> None:
    chi_token = get_token(client, "chi.sv@lms.test")

    start = client.post(
        "/quizzes/q7/attempts",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    attempt_id = start.get_json()["id"]

    # Missing answers field or wrong type
    invalid_resp = client.put(
        f"/quizzes/q7/attempts/{attempt_id}/answers",
        json={"answers": "not_a_dictionary"},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert invalid_resp.status_code == 400
    assert invalid_resp.get_json()["error"] == "VALIDATION_ERROR"
