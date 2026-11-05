"""Tests for Defensive Pattern: Idempotency Key (02_idempotency_key_pattern.md).

Covers:
1. Vulnerable version (/assignments/submit-vulnerable):
   - Demonstrates duplicate submissions under double submission / race condition.
2. Patched version (/assignments/submit-secure):
   - Missing header rejection (400 Bad Request).
   - First submission succeeds (201 Created).
   - Replay request returns cached payload (200 OK) without saving duplicates.
   - Concurrent processing returns 409 Conflict.
3. Unified endpoint (/assignments/submit).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app


@pytest.fixture
def client() -> Any:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": None,
            "JWT_SECRET": "super_secret_jwt_key_that_is_at_least_32_characters_long",
        }
    )
    with app.test_client() as c:
        yield c


def login_user(client: Any, email: str, password: str = "Lms@2026") -> dict[str, Any]:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"
    return res.get_json()


def _student_auth_header(client: Any) -> dict[str, str]:
    # Student Chi (u4) is enrolled in course c1
    login_data = login_user(client, "chi.sv@lms.test")
    return {"Authorization": f"Bearer {login_data['accessToken']}"}


def test_vulnerable_submission_allows_duplicates(client: FlaskClient) -> None:
    """Demonstrates Vulnerable Version: Repeated submissions result in duplicate records."""
    headers = _student_auth_header(client)
    payload = {
        "course_id": "c1",
        "content": "Bài làm đồ án môn Web của sinh viên Chi (Vulnerable)",
    }

    # First request
    res1 = client.post("/assignments/submit-vulnerable", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.get_json()
    assert "submission" in data1
    sub1_id = data1["submission"]["id"]

    # Second request with identical payload (e.g. user double-clicked)
    res2 = client.post("/assignments/submit-vulnerable", json=payload, headers=headers)
    assert res2.status_code == 201
    data2 = res2.get_json()
    assert "submission" in data2
    sub2_id = data2["submission"]["id"]

    # Both submissions succeeded with different IDs (DUPLICATE DETECTED!)
    assert sub1_id != sub2_id

    # Verify duplicate count in store submissions list
    inspect_res = client.get("/assignments/submissions?course_id=c1", headers=headers)
    assert inspect_res.status_code == 200
    all_subs = inspect_res.get_json()
    matching = [s for s in all_subs if s.get("studentId") == "u4" and s.get("courseId") == "c1"]
    assert len(matching) >= 2


def test_patched_submission_requires_idempotency_key(client: FlaskClient) -> None:
    """Patched Version: Rejects request missing Idempotency-Key header with 400 Bad Request."""
    headers = _student_auth_header(client)
    payload = {
        "course_id": "c1",
        "content": "Nộp bài nhưng quên gửi header Idempotency-Key",
    }
    res = client.post("/assignments/submit-secure", json=payload, headers=headers)
    assert res.status_code == 400
    assert res.get_json()["error"] == "VALIDATION_ERROR"


def test_patched_submission_prevents_duplicates_on_replay(client: FlaskClient) -> None:
    """Patched Version: Replaying same Idempotency-Key returns cached 200 OK without duplication."""
    headers = _student_auth_header(client)
    key = str(uuid.uuid4())
    headers["Idempotency-Key"] = key

    payload = {
        "course_id": "c1",
        "content": "Nộp bài chuẩn an toàn với Idempotency Key UUID",
    }

    # 1. First request -> 201 Created
    res1 = client.post("/assignments/submit-secure", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.get_json()
    assert data1["idempotencyKey"] == key
    sub_id_1 = data1["submission"]["id"]

    # 2. Replay request with exact same Idempotency-Key -> 200 OK
    res2 = client.post("/assignments/submit-secure", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.get_json()
    sub_id_2 = data2["submission"]["id"]

    # Exactly the same submission is returned, no duplicate created
    assert sub_id_1 == sub_id_2

    # 3. Third request replay -> still 200 OK with cached response
    res3 = client.post("/assignments/submit-secure", json=payload, headers=headers)
    assert res3.status_code == 200
    assert res3.get_json()["submission"]["id"] == sub_id_1

    # 4. Inspect submissions: student should have only 1 submission for this key
    inspect_res = client.get("/assignments/submissions?course_id=c1", headers=headers)
    all_subs = inspect_res.get_json()
    matching_subs = [s for s in all_subs if s["id"] == sub_id_1]
    assert len(matching_subs) == 1


def test_patched_submission_concurrent_conflict(client: FlaskClient) -> None:
    """Patched Version: Concurrent requests with same key trigger 409 Conflict when PROCESSING."""
    headers = _student_auth_header(client)
    key = "concurrent-key-" + str(uuid.uuid4())

    # Directly mark key as PROCESSING in store cache to simulate in-flight request
    store = client.application.store  # type: ignore[attr-defined]
    with store.idempotency_lock:
        store.idempotency_cache[key] = {
            "status": "PROCESSING",
            "userId": "u4",
            "courseId": "c1",
        }

    headers["Idempotency-Key"] = key
    payload = {
        "course_id": "c1",
        "content": "Request song song khi một request khác đang được xử lý",
    }

    res = client.post("/assignments/submit-secure", json=payload, headers=headers)
    assert res.status_code == 409
    assert res.get_json()["error"] == "CONFLICT"


def test_unified_endpoint_routes_correctly(client: FlaskClient) -> None:
    """Unified /assignments/submit: works with or without Idempotency-Key."""
    headers = _student_auth_header(client)
    payload = {
        "course_id": "c1",
        "content": "Thử nghiệm endpoint /assignments/submit",
    }

    # Case A: Without header -> executes vulnerable
    res_no_key = client.post("/assignments/submit", json=payload, headers=headers)
    assert res_no_key.status_code == 201

    # Case B: With header -> executes patched
    secure_headers = dict(headers)
    sec_key = str(uuid.uuid4())
    secure_headers["Idempotency-Key"] = sec_key
    res_secure_1 = client.post("/assignments/submit", json=payload, headers=secure_headers)
    assert res_secure_1.status_code == 201

    # Replay -> returns 200
    res_secure_2 = client.post("/assignments/submit", json=payload, headers=secure_headers)
    assert res_secure_2.status_code == 200
    sub1_id = res_secure_1.get_json()["submission"]["id"]
    sub2_id = res_secure_2.get_json()["submission"]["id"]
    assert sub1_id == sub2_id
