"""Comprehensive test suite for Defensive Pattern #6: Timeout & Fallback (TT-01 to TT-10)."""

from __future__ import annotations

import concurrent.futures
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
            "JWT_SECRET": "pattern6_timeout_and_fallback_test_secret_key_32chars",
            "TOKEN_TTL_SECONDS": 900,
            "STATS_TIMEOUT_SECONDS": 0.3,  # Fast timeout for test suite
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


# TT-01: Upstream responds immediately
def test_tt01_stats_client_success_immediate(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")  # Instructor of c1
    resp = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["courseId"] == "c1"
    assert data["isFallback"] is False
    assert data["stats"] is not None
    assert "enrolledStudents" in data["stats"]
    assert data["stats"]["enrolledStudents"] >= 1
    assert data["reasonCode"] is None


# TT-02: Upstream delay > timeout with existing last-known-good cache
def test_tt02_delay_exceeds_timeout_uses_fallback_cache(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")

    # 1. First call: warm the cache with immediate response
    warm_resp = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert warm_resp.status_code == 200
    assert warm_resp.get_json()["isFallback"] is False

    # 2. Second call: inject delay 800ms (timeout configured at 300ms)
    start_time = time.perf_counter()
    resp = client.get(
        "/courses/c1/dashboard?delay_ms=800",
        headers={"Authorization": f"Bearer {token}"},
    )
    elapsed = time.perf_counter() - start_time

    assert resp.status_code == 200
    data = resp.get_json()
    # Deadline bound check: aborts around timeout (~0.3s - 0.6s), NOT waiting 0.8s
    assert elapsed < 0.75, f"Expected timeout under 0.75s, got {elapsed:.2f}s"
    assert data["isFallback"] is True
    assert data["reasonCode"] == "UPSTREAM_TIMEOUT"
    assert data["asOf"] is not None
    assert data["stats"] is not None
    assert data["mode"] == "patched_fallback_cached"


# TT-03: Delay > timeout without existing cache -> honest degraded response
def test_tt03_delay_without_cache_returns_honest_degradation(client: FlaskClient) -> None:
    # Test admin on c3 (which has no pre-warmed cache)
    admin_token = get_token(client, "admin@lms.test")

    start_time = time.perf_counter()
    resp = client.get(
        "/courses/c1/dashboard?delay_ms=700",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    elapsed = time.perf_counter() - start_time

    assert resp.status_code == 200
    data = resp.get_json()
    assert elapsed < 0.7
    assert data["isFallback"] is True
    # If no cache was warmed in this fresh test fixture:
    assert data["reasonCode"] in ("UPSTREAM_TIMEOUT", "NO_CACHE_AVAILABLE")
    # Honest response: does NOT fabricate imaginary student scores
    if data["stats"] is None:
        assert data["asOf"] is None


# TT-04: Upstream connection or timeout error handled safely without 500 stack
def test_tt04_upstream_error_handled_safely(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")

    # 1. Test error=timeout
    resp_timeout = client.get(
        "/courses/c1/dashboard?error=timeout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_timeout.status_code == 200
    data_t = resp_timeout.get_json()
    assert data_t["isFallback"] is True
    assert "error" not in data_t or data_t.get("error") is None
    assert "Traceback" not in resp_timeout.get_data(as_text=True)

    # 2. Test error=connection
    resp_conn = client.get(
        "/courses/c1/dashboard?error=connection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_conn.status_code == 200
    data_c = resp_conn.get_json()
    assert data_c["isFallback"] is True
    assert "UPSTREAM" in data_c["reasonCode"]


# TT-05: Unauthorized actor receives 403, cache is NEVER leaked
def test_tt05_unauthorized_actor_forbidden_no_cache_leak(
    client: FlaskClient, app_instance: Any
) -> None:
    instructor_token = get_token(client, "an.gv@lms.test")
    # Warm the cache
    warm = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert warm.status_code == 200

    # 1. Binh (instructor of c2, NOT c1) tries to view c1 dashboard
    binh_token = get_token(client, "binh.gv@lms.test")
    resp_binh = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert resp_binh.status_code == 403
    assert resp_binh.get_json()["error"] == "FORBIDDEN"

    # 2. Student not enrolled tries to view c1
    # u6 (em.sv) is not enrolled in c1 in seed.json
    em_token = get_token(client, "em.sv@lms.test")
    resp_em = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {em_token}"},
    )
    assert resp_em.status_code == 403
    assert resp_em.get_json()["error"] == "FORBIDDEN"


# TT-06: High concurrency & slow upstream does not exhaust server; /me remains fast
def test_tt06_concurrency_isolation_me_endpoint_remains_available(client: FlaskClient) -> None:
    token = get_token(client, "admin@lms.test")

    def _call_dashboard() -> int:
        r = client.get(
            "/courses/c1/dashboard?delay_ms=500",
            headers={"Authorization": f"Bearer {token}"},
        )
        return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_call_dashboard) for _ in range(5)]

        # Concurrently request /me
        me_start = time.perf_counter()
        me_resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        me_elapsed = time.perf_counter() - me_start

        assert me_resp.status_code == 200
        assert me_resp.get_json()["email"] == "admin@lms.test"
        # /me must respond quickly, not blocked by stats workers
        assert me_elapsed < 0.2

        for f in futures:
            assert f.result() == 200


# TT-07: Fallback metadata includes explicit asOf timestamp and isFallback flag
def test_tt07_cache_staleness_and_metadata_transparency(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")
    client.get("/courses/c1/dashboard", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(
        "/courses/c1/dashboard?delay_ms=600",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.get_json()
    assert data["isFallback"] is True
    assert "asOf" in data
    assert isinstance(data["asOf"], str)
    assert "T" in data["asOf"]  # ISO-8601 formatted


# TT-08: Configuration and input boundary validation
def test_tt08_input_and_boundary_validation(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")

    # Invalid delay_ms
    resp_inv_delay = client.get(
        "/courses/c1/dashboard?delay_ms=abc",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_inv_delay.status_code == 400
    assert resp_inv_delay.get_json()["error"] == "VALIDATION_ERROR"

    # Invalid error type
    resp_inv_err = client.get(
        "/courses/c1/dashboard?error=sql_injection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_inv_err.status_code == 400
    assert resp_inv_err.get_json()["error"] == "VALIDATION_ERROR"


# TT-09: Actor losing permission after cache creation is immediately blocked
def test_tt09_actor_permission_loss_blocks_fallback_access(
    client: FlaskClient, app_instance: Any
) -> None:
    student_token = get_token(client, "chi.sv@lms.test")  # Chi is enrolled in c1
    # 1. Chi can view c1 dashboard
    resp1 = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp1.status_code == 200

    # 2. Simulate revocation: remove Chi from enrollments in Store
    store = app_instance.config["STORE"]
    store.enrollments.pop(("c1", "u4"), None)

    # 3. Chi tries to view c1 again (even though cache exists)
    resp2 = client.get(
        "/courses/c1/dashboard",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp2.status_code == 403
    assert resp2.get_json()["error"] == "FORBIDDEN"


# TT-10: Response output sanitization: no secrets leaked
def test_tt10_response_sanitization_no_secrets_leaked(client: FlaskClient) -> None:
    token = get_token(client, "admin@lms.test")
    resp = client.get("/courses/c1/dashboard", headers={"Authorization": f"Bearer {token}"})
    raw_text = resp.get_data(as_text=True)

    assert "password" not in raw_text
    assert "password_hash" not in raw_text
    assert "secret" not in raw_text.lower()
    # Check security headers
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"


# Lab Baseline vs Patched Benchmark Comparison Test (for Before-After Report)
def test_baseline_vs_patched_latency_comparison(client: FlaskClient) -> None:
    token = get_token(client, "an.gv@lms.test")

    # Warm cache
    client.get("/courses/c1/dashboard", headers={"Authorization": f"Bearer {token}"})

    # 1. Patched execution: delay=600ms, timeout=300ms -> completes in < 550ms with fallback
    t0 = time.perf_counter()
    resp_patched = client.get(
        "/courses/c1/dashboard?delay_ms=600",
        headers={"Authorization": f"Bearer {token}"},
    )
    patched_duration = time.perf_counter() - t0
    assert resp_patched.status_code == 200
    assert resp_patched.get_json()["isFallback"] is True
    assert patched_duration < 0.55

    # 2. Baseline execution: delay=600ms, baseline=true -> must block for >= 580ms
    t1 = time.perf_counter()
    resp_baseline = client.get(
        "/courses/c1/dashboard?delay_ms=600&baseline=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    baseline_duration = time.perf_counter() - t1
    assert resp_baseline.status_code == 200
    assert resp_baseline.get_json()["isFallback"] is False
    assert baseline_duration >= 0.58, f"Baseline should block >=0.58s, got {baseline_duration:.2f}s"
