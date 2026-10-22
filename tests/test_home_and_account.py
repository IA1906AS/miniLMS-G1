"""Comprehensive Tests for Home Page & Account Page Features."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from lms_project_1 import create_app

TEST_SECRET = "super_secret_test_key_at_least_32_chars_long"


@pytest.fixture
def test_app(tmp_path: Path) -> Flask:
    audit_file = tmp_path / "test_audit_home.log"
    return create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 900,
            "AUDIT_LOG_PATH": str(audit_file),
        }
    )


@pytest.fixture
def client(test_app: Flask) -> Any:
    return test_app.test_client()


def login_user(client: Any, email: str, password: str = "Lms@2026") -> str:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"
    token: str = res.get_json()["accessToken"]
    return token


# 1. GET /home requires authentication
def test_home_unauthenticated(client: Any) -> None:
    res = client.get("/home")
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# 2. GET /home for student Chi returns enrolled courses, stats, and recommended courses
def test_home_student_data(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    res = client.get("/home", headers={"Authorization": f"Bearer {chi_token}"})
    assert res.status_code == 200
    data = res.get_json()

    # Check user section
    assert data["user"]["id"] == "u4"
    assert data["user"]["email"] == "chi.sv@lms.test"
    assert data["user"]["role"] == "STUDENT"
    assert "Lê Linh Chi" in data["user"]["fullName"]

    # Check stats section
    stats = data["stats"]
    assert "completedCourses" in stats
    assert "inProgressCourses" in stats
    assert "totalHours" in stats
    assert "certificates" in stats

    # Check enrolled courses
    enrolled = data["enrolledCourses"]
    assert len(enrolled) >= 1
    c1 = next(c for c in enrolled if c["id"] == "c1")
    assert c1["title"] == "Lập trình Web"
    assert c1["score"] == 7.5
    assert c1["progress"] > 0
    assert "nextLessonTitle" in c1

    # Check featured/recommended courses (c2 and c3 should appear since Chi is only enrolled in c1)
    featured = data["featuredCourses"]
    featured_ids = [c["id"] for c in featured]
    assert "c1" not in featured_ids
    assert "c2" in featured_ids or "c3" in featured_ids


# 3. GET /account/profile returns profile, learning history, and notification settings
def test_account_profile_data(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    res = client.get("/account/profile", headers={"Authorization": f"Bearer {chi_token}"})
    assert res.status_code == 200
    data = res.get_json()

    profile = data["profile"]
    assert profile["email"] == "chi.sv@lms.test"
    assert "password" not in profile
    assert "password_hash" not in profile

    history = data["history"]
    assert len(history) >= 1
    assert history[0]["courseId"] == "c1"

    notifications = data["notifications"]
    assert "emailNewCourses" in notifications
    assert "emailAssignments" in notifications


# 4. PUT /account/profile updates editable fields safely
def test_update_account_profile(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    headers = {"Authorization": f"Bearer {chi_token}"}

    update_payload = {
        "fullName": "Lê Linh Chi Updated",
        "phone": "0987654321",
        "bio": "Đã cập nhật tiểu sử cá nhân.",
    }
    res = client.put("/account/profile", json=update_payload, headers=headers)
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["profile"]["fullName"] == "Lê Linh Chi Updated"
    assert res_data["profile"]["phone"] == "0987654321"
    assert res_data["profile"]["bio"] == "Đã cập nhật tiểu sử cá nhân."

    # Try injecting forbidden fields (IDOR / privilege escalation attempt)
    bad_payload = {"role": "ADMIN"}
    res_bad = client.put("/account/profile", json=bad_payload, headers=headers)
    assert res_bad.status_code == 400
    assert res_bad.get_json() == {"error": "VALIDATION_ERROR"}


# 5. PUT /account/change-password verifies old password and hashes new password
def test_change_password_flow(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test", "Lms@2026")
    headers = {"Authorization": f"Bearer {chi_token}"}

    # Wrong old password
    res_wrong = client.put(
        "/account/change-password",
        json={"oldPassword": "WrongPassword@123", "newPassword": "NewPassword@2026"},
        headers=headers,
    )
    assert res_wrong.status_code == 401
    assert res_wrong.get_json() == {"error": "INVALID_CREDENTIALS"}

    # Too short new password (< 8 chars)
    res_short = client.put(
        "/account/change-password",
        json={"oldPassword": "Lms@2026", "newPassword": "short"},
        headers=headers,
    )
    assert res_short.status_code == 400
    assert res_short.get_json() == {"error": "VALIDATION_ERROR"}

    # Correct old password -> Success
    res_ok = client.put(
        "/account/change-password",
        json={"oldPassword": "Lms@2026", "newPassword": "BrandNewPassword@2026"},
        headers=headers,
    )
    assert res_ok.status_code == 200
    assert res_ok.get_json() == {"message": "Đổi mật khẩu thành công"}

    # Now login with the NEW password succeeds
    new_token = login_user(client, "chi.sv@lms.test", "BrandNewPassword@2026")
    assert new_token is not None


# 6. PUT /account/notifications updates toggle settings
def test_update_notification_settings(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    headers = {"Authorization": f"Bearer {chi_token}"}

    res = client.put(
        "/account/notifications",
        json={"emailNewCourses": False, "emailGradeUpdates": True},
        headers=headers,
    )
    assert res.status_code == 200
    notifs = res.get_json()["notifications"]
    assert notifs["emailNewCourses"] is False
    assert notifs["emailGradeUpdates"] is True
