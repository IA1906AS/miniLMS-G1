"""Test suite covering Authentication, Password Management & RBAC specifications.

Adheres strictly to test cases defined in:
- authentication_password_management_specs.md (TC01 - TC06)
- rbac_permission_system_specs.md (TC01 - TC06)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from lms_project_1 import create_app

TEST_SECRET = "super_secret_test_key_at_least_32_chars_long"


@pytest.fixture
def auth_app(tmp_path: Path) -> Flask:
    audit_file = tmp_path / "test_auth_audit.log"
    db_file = tmp_path / "test_auth.db"
    return create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 900,
            "AUDIT_LOG_PATH": str(audit_file),
            "DATABASE_URL": f"sqlite:///{db_file}",
            "TESTING": True,
        }
    )


@pytest.fixture
def client(auth_app: Flask) -> Any:
    return auth_app.test_client()


# =========================================================================
# Part 1: Authentication & Password Management Tests (TC01 - TC06)
# =========================================================================


def test_tc01_register_new_valid_user(client: Any) -> None:
    """TC01: Đăng ký tài khoản mới hợp lệ.

    Email mới, mật khẩu đủ độ mạnh -> Trả về HTTP 201, Role = 'guest'.
    """
    res = client.post(
        "/auth/register",
        json={
            "email": "new.student@lms.test",
            "password": "Password123!",
            "full_name": "Nguyen Van A",
        },
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["email"] == "new.student@lms.test"
    assert data["full_name"] == "Nguyen Van A"
    assert data["role"] == "guest"
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert "password" not in data
    assert "password_hash" not in data


def test_tc02_register_duplicate_email(client: Any) -> None:
    """TC02: Đăng ký trùng Email -> Trả về HTTP 400."""
    # First registration
    res1 = client.post(
        "/auth/register",
        json={
            "email": "duplicate@lms.test",
            "password": "Password123!",
            "full_name": "Nguyen Van B",
        },
    )
    assert res1.status_code == 201

    # Second registration with identical email
    res2 = client.post(
        "/auth/register",
        json={
            "email": "duplicate@lms.test",
            "password": "OtherPassword456!",
            "full_name": "Nguyen Van C",
        },
    )
    assert res2.status_code == 400
    assert res2.get_json()["error"] == "VALIDATION_ERROR"


def test_register_weak_password_validation(client: Any) -> None:
    """Validate password security policy: min 8 chars, uppercase, lowercase, digit."""
    # Too short (< 8 chars)
    res = client.post(
        "/auth/register",
        json={"email": "short@lms.test", "password": "Pass1", "full_name": "Short"},
    )
    assert res.status_code == 400

    # No uppercase
    res = client.post(
        "/auth/register",
        json={"email": "noupper@lms.test", "password": "password123", "full_name": "No Upper"},
    )
    assert res.status_code == 400

    # No lowercase
    res = client.post(
        "/auth/register",
        json={"email": "nolower@lms.test", "password": "PASSWORD123", "full_name": "No Lower"},
    )
    assert res.status_code == 400

    # No digit
    res = client.post(
        "/auth/register",
        json={"email": "nodigit@lms.test", "password": "PasswordOnly", "full_name": "No Digit"},
    )
    assert res.status_code == 400


def test_tc03_login_valid_credentials(client: Any) -> None:
    """TC03: Đăng nhập đúng thông tin -> HTTP 200 + JWT Token + Refresh Token + User."""
    # Register user
    client.post(
        "/auth/register",
        json={
            "email": "login.user@lms.test",
            "password": "ValidPassword1",
            "full_name": "Login User",
        },
    )

    # Login
    res = client.post(
        "/auth/login",
        json={"email": "login.user@lms.test", "password": "ValidPassword1"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["expiresIn"] == 900
    assert data["user"]["email"] == "login.user@lms.test"
    assert data["user"]["role"] == "guest"


def test_tc04_login_wrong_password(client: Any) -> None:
    """TC04: Đăng nhập sai mật khẩu -> HTTP 401."""
    res = client.post(
        "/auth/login",
        json={"email": "admin@lms.test", "password": "WrongPassword999"},
    )
    assert res.status_code == 401
    assert res.get_json() == {"error": "INVALID_CREDENTIALS"}


def test_tc05_reset_password_success(client: Any) -> None:
    """TC05: Reset Password thành công.

    Token hợp lệ, chưa hết hạn, mật khẩu mới hợp lệ ->
    Mật khẩu được cập nhật, token hết hiệu lực, đăng nhập mật khẩu mới thành công.
    """
    # 1. Register a user
    email = "reset.me@lms.test"
    old_pwd = "OldPassword123"
    client.post(
        "/auth/register",
        json={"email": email, "password": old_pwd, "full_name": "Reset Candidate"},
    )

    # 2. Request forgot password
    res_forgot = client.post("/auth/forgot-password", json={"email": email})
    assert res_forgot.status_code == 200
    reset_token = res_forgot.get_json().get("resetToken")
    assert reset_token is not None

    # 3. Reset password with valid token
    new_pwd = "BrandNewPassword2026"
    res_reset = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": new_pwd},
    )
    assert res_reset.status_code == 200
    assert "successfully reset" in res_reset.get_json()["message"]

    # 4. Old password must no longer work
    res_old_login = client.post("/auth/login", json={"email": email, "password": old_pwd})
    assert res_old_login.status_code == 401

    # 5. New password must work
    res_new_login = client.post("/auth/login", json={"email": email, "password": new_pwd})
    assert res_new_login.status_code == 200
    assert "accessToken" in res_new_login.get_json()


def test_tc06_reset_password_with_used_token(client: Any) -> None:
    """TC06: Reset Password bằng Token đã dùng -> Trả về HTTP 400 (Token invalid)."""
    email = "used.token@lms.test"
    client.post(
        "/auth/register",
        json={"email": email, "password": "FirstPassword1", "full_name": "Token Tester"},
    )

    # Request reset token
    res_forgot = client.post("/auth/forgot-password", json={"email": email})
    reset_token = res_forgot.get_json()["resetToken"]

    # First reset (succeeds)
    res_reset1 = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": "SecondPassword2"},
    )
    assert res_reset1.status_code == 200

    # Second reset with SAME token (must fail with 400)
    res_reset2 = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": "ThirdPassword3"},
    )
    assert res_reset2.status_code == 400
    assert res_reset2.get_json()["error"] == "VALIDATION_ERROR"


# =========================================================================
# Part 2: Role-Based Access Control (RBAC) Tests (TC01 - TC06)
# =========================================================================


def _get_token(client: Any, email: str, password: str = "Lms@2026") -> str:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed: {res.get_json()}"
    return str(res.get_json()["accessToken"])


def test_rbac_tc01_access_guest_endpoints(client: Any) -> None:
    """RBAC TC01: Access Guest Endpoint.

    Unauthenticated/Guest truy cập thông tin chung
    (login, register, forgot-password) -> HTTP 200/201.
    """
    res_reg = client.post(
        "/auth/register",
        json={
            "email": "guest.access@lms.test",
            "password": "Password123!",
            "full_name": "Guest Visitor",
        },
    )
    assert res_reg.status_code == 201

    res_forgot = client.post("/auth/forgot-password", json={"email": "nonexistent@lms.test"})
    assert res_forgot.status_code == 200


def test_rbac_tc02_student_accesses_teacher_endpoint(client: Any) -> None:
    """RBAC TC02: Student truy cập tính năng Teacher.

    Role = 'student' gọi API tạo bài tập (POST /courses/c1/assignments) -> HTTP 403 Forbidden.
    """
    student_token = _get_token(client, "chi.sv@lms.test")
    res = client.post(
        "/courses/c1/assignments",
        json={"title": "Assignment 1"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


def test_rbac_tc03_teacher_accesses_teacher_endpoint(client: Any) -> None:
    """RBAC TC03: Teacher truy cập tính năng Teacher.

    Role = 'teacher' gọi API tạo bài tập (POST /courses/c1/assignments) -> HTTP 200 / 201 Created.
    """
    teacher_token = _get_token(client, "an.gv@lms.test")
    res = client.post(
        "/courses/c1/assignments",
        json={"title": "Midterm Project"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["courseId"] == "c1"
    assert data["title"] == "Midterm Project"


def test_rbac_tc04_non_admin_updates_role(client: Any) -> None:
    """RBAC TC04: Non-Admin nâng cấp Role.

    Role = 'teacher' gọi API cấp quyền (PATCH /users/u4/role) -> HTTP 403 Forbidden.
    """
    teacher_token = _get_token(client, "an.gv@lms.test")
    res = client.patch(
        "/users/u4/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


def test_rbac_tc05_admin_updates_user_role(client: Any) -> None:
    """RBAC TC05: Admin nâng cấp Role người dùng.

    Role = 'admin' gọi API cấp quyền (PATCH /users/u4/role) -> HTTP 200 OK.
    """
    admin_token = _get_token(client, "admin@lms.test")
    res = client.patch(
        "/users/u4/role",
        json={"role": "teacher"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == "u4"
    assert data["role"] == "teacher"


def test_rbac_tc06_expired_token_access(tmp_path: Path) -> None:
    """RBAC TC06: Token hết hạn truy cập API -> HTTP 401 Unauthorized."""
    short_app = create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 1,
            "AUDIT_LOG_PATH": str(tmp_path / "audit_rbac_tc06.log"),
            "DATABASE_URL": f"sqlite:///{tmp_path / 'tc06.db'}",
        }
    )
    c = short_app.test_client()
    token = _get_token(c, "chi.sv@lms.test")
    time.sleep(1.5)
    res = c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}
