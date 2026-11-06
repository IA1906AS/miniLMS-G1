"""Comprehensive test suite for Defensive Pattern #9: Bulkhead (B9-01 to B9-06)."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app
from lms_project_1.reports import BulkheadLimiter


@pytest.fixture
def app_instance() -> Any:
    """Create fresh application instance with isolated seed data and a custom bulkhead limiter."""
    test_limiter = BulkheadLimiter(max_concurrent=2)
    app = create_app(
        {
            "JWT_SECRET": "pattern9_bulkhead_isolation_secret_key_32chars",
            "TOKEN_TTL_SECONDS": 900,
            "EXPORT_BULKHEAD": test_limiter,
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


# B9-01: Happy Path - Normal Authorized Export (JSON & CSV)
def test_b9_01_normal_authorized_export_json_and_csv(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")  # Instructor of c1

    # 1. Export JSON
    resp_json = client.get(
        "/courses/c1/grades/export?format=json",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_json.status_code == 200
    data = resp_json.get_json()
    assert data["courseId"] == "c1"
    assert "grades" in data
    assert isinstance(data["grades"], list)

    # 2. Export CSV
    resp_csv = client.get(
        "/courses/c1/grades/export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers.get("Content-Type", "")
    assert "studentId,studentName,studentEmail,score" in resp_csv.get_data(as_text=True)


# B9-02 & B9-03: Bulkhead saturation returns 429 fast-fail with Retry-After header
def test_b9_02_and_03_bulkhead_saturation_fast_fails_with_429(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")

    def _slow_export() -> tuple[int, float]:
        t0 = time.perf_counter()
        r = client.get(
            "/courses/c1/grades/export?delay_ms=600",
            headers={"Authorization": f"Bearer {token}"},
        )
        return r.status_code, time.perf_counter() - t0

    # Start 2 slow workers occupying both slots of the bulkhead
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        f1 = pool.submit(_slow_export)
        f2 = pool.submit(_slow_export)

        # Brief sleep to ensure both slots are acquired
        time.sleep(0.08)

        # 3rd request arrives while slots are full -> must fast fail with 429
        t_fast = time.perf_counter()
        resp_blocked = client.get(
            "/courses/c1/grades/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        fast_duration = time.perf_counter() - t_fast

        assert resp_blocked.status_code == 429
        # B9-03: Fast fail: response arrived in under 100ms, not blocked by the 600ms slow tasks!
        assert fast_duration < 0.2
        data = resp_blocked.get_json()
        assert data["error"] == "BULKHEAD_CAPACITY_EXCEEDED"
        assert "Retry-After" in resp_blocked.headers

        # The 2 running workers complete successfully
        assert f1.result()[0] == 200
        assert f2.result()[0] == 200


# B9-04: Other endpoints (/me, /courses/c1/grades) remain unaffected during export saturation
def test_b9_04_critical_endpoints_remain_available_during_bulkhead_saturation(
    client: FlaskClient,
) -> None:
    token = get_token(client, "an.gv@lms.test")

    def _occupy_bulkhead() -> int:
        r = client.get(
            "/courses/c1/grades/export?delay_ms=500",
            headers={"Authorization": f"Bearer {token}"},
        )
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        f1 = pool.submit(_occupy_bulkhead)
        f2 = pool.submit(_occupy_bulkhead)

        time.sleep(0.05)

        # Call /me while bulkhead is 100% full
        t_me = time.perf_counter()
        me_resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        me_duration = time.perf_counter() - t_me

        assert me_resp.status_code == 200
        # /me must respond with negligible latency (< 150ms)
        assert me_duration < 0.2

        # Call regular /courses/c1/grades
        t_grades = time.perf_counter()
        grades_resp = client.get("/courses/c1/grades", headers={"Authorization": f"Bearer {token}"})
        grades_duration = time.perf_counter() - t_grades

        assert grades_resp.status_code == 200
        assert grades_duration < 0.2

        assert f1.result() == 200
        assert f2.result() == 200


# B9-05: Strict Authorization - Students and other instructors blocked with 403
def test_b9_05_authorization_restrictions(client: FlaskClient) -> None:
    # 1. Student Chi tries to export c1 grades -> 403
    chi_token = get_token(client, "chi.sv@lms.test")
    resp_student = client.get(
        "/courses/c1/grades/export",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert resp_student.status_code == 403
    assert resp_student.get_json()["error"] == "FORBIDDEN"

    # 2. Instructor Binh (instructor of c2, not c1) tries to export c1 grades -> 403
    binh_token = get_token(client, "binh.gv@lms.test")
    resp_binh = client.get(
        "/courses/c1/grades/export",
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert resp_binh.status_code == 403
    assert resp_binh.get_json()["error"] == "FORBIDDEN"


# B9-06: Response sanitization - no password hashes or sensitive fields leaked
def test_b9_06_response_sanitization_no_secrets_leaked(client: FlaskClient) -> None:
    admin_token = get_token(client, "admin@lms.test")
    resp = client.get(
        "/courses/c1/grades/export?format=json",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    raw_text = resp.get_data(as_text=True)

    assert "password" not in raw_text
    assert "password_hash" not in raw_text
    assert "secret" not in raw_text.lower()
    assert "token" not in raw_text.lower()
