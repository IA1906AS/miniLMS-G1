"""Comprehensive test suite for Defensive Pattern #5: Circuit Breaker (C5-01 to C5-08)."""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app
from lms_project_1.plagiarism import (
    CircuitBreaker,
    CircuitState,
)


@pytest.fixture
def app_instance() -> Any:
    """Create fresh application instance with isolated seed data and fast cooldown breaker."""
    test_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.4, half_open_probes=1)
    app = create_app(
        {
            "JWT_SECRET": "pattern5_circuit_breaker_test_secret_key_32chars",
            "TOKEN_TTL_SECONDS": 900,
            "PLAGIARISM_BREAKER": test_breaker,
        }
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_instance: Any) -> FlaskClient:
    return app_instance.test_client()


def get_token(
    client: FlaskClient,
    email: str = "an.gv@lms.test",
    password: str = "Lms@2026",
) -> str:
    """Helper to authenticate and retrieve Bearer token."""
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.get_json()}"
    body = resp.get_json()
    token = body.get("accessToken") or body.get("access_token")
    assert isinstance(token, str)
    return token


def create_submission(
    client: FlaskClient,
    course_id: str = "c1",
    student_email: str = "chi.sv@lms.test",
) -> str:
    """Helper for student to submit an assignment in c1 to test plagiarism checker."""
    token = get_token(client, student_email)
    resp = client.post(
        "/assignments/submit",
        json={
            "course_id": course_id,
            "content": "Đây là bài thu hoạch phân tích an toàn thông tin và kiến trúc web.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Submission creation failed: {resp.get_json()}"
    data = resp.get_json()
    sub_id = data["submission"]["id"]
    return str(sub_id)


# C5-01: Happy Path - Normal Plagiarism Check succeeds (200 OK)
def test_c5_01_plagiarism_check_success(client: FlaskClient) -> None:
    sub_id = create_submission(client, "c1", "chi.sv@lms.test")
    chi_token = get_token(client, "chi.sv@lms.test")

    resp = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["submissionId"] == sub_id
    assert "similarityScore" in data
    assert data["status"] in ("CLEAN", "FLAGGED")


# C5-02 & C5-03: Upstream failures trip breaker from CLOSED to OPEN, leading to fast-fail 503
def test_c5_02_and_03_breaker_trips_to_open_and_fast_fails(client: FlaskClient) -> None:
    sub_id = create_submission(client, "c1", "chi.sv@lms.test")
    chi_token = get_token(client, "chi.sv@lms.test")

    # Trip the breaker by inducing 3 consecutive upstream failures
    for _ in range(3):
        fail_resp = client.post(
            f"/courses/c1/submissions/{sub_id}/plagiarism-check",
            json={"simulate_error": "timeout"},
            headers={"Authorization": f"Bearer {chi_token}"},
        )
        assert fail_resp.status_code in (502, 503)

    # Breaker should now be OPEN: 4th request must immediately FAST-FAIL with 503
    fast_fail_resp = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert fast_fail_resp.status_code == 503
    data = fast_fail_resp.get_json()
    assert data["circuitState"] == "OPEN"
    assert "Retry-After" in fast_fail_resp.headers
    assert float(fast_fail_resp.headers["Retry-After"]) >= 0


# C5-04: Cooldown expires -> transitions to HALF_OPEN -> trial probe succeeds -> CLOSED
def test_c5_04_cooldown_and_recovery_to_closed(client: FlaskClient, app_instance: Any) -> None:
    import time

    sub_id = create_submission(client, "c1", "chi.sv@lms.test")
    chi_token = get_token(client, "chi.sv@lms.test")

    # 1. Trip breaker to OPEN
    for _ in range(3):
        client.post(
            f"/courses/c1/submissions/{sub_id}/plagiarism-check",
            json={"simulate_error": "timeout"},
            headers={"Authorization": f"Bearer {chi_token}"},
        )

    status_resp = client.get(
        f"/courses/c1/submissions/{sub_id}/plagiarism-breaker/status",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert status_resp.get_json()["state"] == "OPEN"

    # 2. Wait for fast cooldown (0.4s configured in app_instance fixture)
    time.sleep(0.45)

    # 3. Next call acts as probe in HALF_OPEN: with no error, probe succeeds and resets to CLOSED
    probe_resp = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert probe_resp.status_code == 200

    # 4. Check circuit state is back to CLOSED
    status_recovered = client.get(
        f"/courses/c1/submissions/{sub_id}/plagiarism-breaker/status",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert status_recovered.get_json()["state"] == "CLOSED"


# C5-05: In HALF_OPEN, if probe fails -> immediately returns to OPEN
def test_c5_05_half_open_probe_failure_re_opens_circuit(client: FlaskClient) -> None:
    import time

    sub_id = create_submission(client, "c1", "chi.sv@lms.test")
    chi_token = get_token(client, "chi.sv@lms.test")

    # Trip breaker
    for _ in range(3):
        client.post(
            f"/courses/c1/submissions/{sub_id}/plagiarism-check",
            json={"simulate_error": "timeout"},
            headers={"Authorization": f"Bearer {chi_token}"},
        )

    # Wait for cooldown
    time.sleep(0.45)

    # Probe fails with error
    fail_probe = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        json={"simulate_error": "down"},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert fail_probe.status_code in (502, 503)

    # Verify breaker is immediately back to OPEN
    status_resp = client.get(
        f"/courses/c1/submissions/{sub_id}/plagiarism-breaker/status",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert status_resp.get_json()["state"] == "OPEN"


# C5-06: Authorization and Business 4xx errors do NOT trip breaker
def test_c5_06_authorization_and_business_errors_do_not_trip_breaker(client: FlaskClient) -> None:
    sub_id = create_submission(client, "c1", "chi.sv@lms.test")

    # 1. Binh (instructor of c2, NOT c1) tries to check Chi's submission in c1 -> 403
    binh_token = get_token(client, "binh.gv@lms.test")
    resp_binh = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert resp_binh.status_code == 403

    # 2. Another student Dung tries to check Chi's submission -> 403
    dung_token = get_token(client, "dung.sv@lms.test")
    resp_dung = client.post(
        f"/courses/c1/submissions/{sub_id}/plagiarism-check",
        headers={"Authorization": f"Bearer {dung_token}"},
    )
    assert resp_dung.status_code == 403

    # 3. Repeated 403s should NOT trip the circuit breaker (circuit remains CLOSED)
    status_resp = client.get(
        f"/courses/c1/submissions/{sub_id}/plagiarism-breaker/status",
        headers={"Authorization": f"Bearer {dung_token}"},
    )
    assert status_resp.get_json()["state"] == "CLOSED"
    assert status_resp.get_json()["consecutiveFailures"] == 0


# C5-07: Admin manual reset endpoint restores circuit to CLOSED
def test_c5_07_admin_reset_breaker(client: FlaskClient) -> None:
    sub_id = create_submission(client, "c1", "chi.sv@lms.test")
    admin_token = get_token(client, "admin@lms.test")

    # Trip breaker
    for _ in range(3):
        client.post(
            f"/courses/c1/submissions/{sub_id}/plagiarism-check",
            json={"simulate_error": "timeout"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    # Admin calls reset
    reset_resp = client.post(
        "/api/lab/plagiarism-breaker/reset",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.get_json()["status"]["state"] == "CLOSED"


# C5-08: Unit test of CircuitBreaker with deterministic mock clock
def test_c5_08_circuit_breaker_unit_state_machine() -> None:
    current_time = 1000.0

    def mock_time() -> float:
        return current_time

    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0, time_fn=mock_time)
    assert breaker.state == CircuitState.CLOSED

    def failing_call() -> None:
        raise TimeoutError("provider timeout")

    def successful_call() -> str:
        return "success"

    # 1. First failure
    with pytest.raises(TimeoutError):
        breaker.call(failing_call)
    assert breaker.state == CircuitState.CLOSED

    # 2. Second failure -> trips to OPEN
    with pytest.raises(TimeoutError):
        breaker.call(failing_call)
    assert breaker.state == CircuitState.OPEN

    # 3. Fast fail while cooldown active
    current_time = 1005.0
    with pytest.raises(Exception) as exc_info:
        breaker.call(successful_call)
    assert "Circuit is OPEN" in str(exc_info.value)

    # 4. Advance time past cooldown (1000 + 11 = 1011) -> transitions to HALF_OPEN & probe succeeds
    current_time = 1012.0
    result = breaker.call(successful_call)
    assert result == "success"
    assert breaker.state == CircuitState.CLOSED
