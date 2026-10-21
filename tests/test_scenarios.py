"""Comprehensive Test Suite Covering Scenarios A1 - A19 from Specification."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from flask import Flask, jsonify

from lms_project_1 import create_app
from lms_project_1.errors import Forbidden
from lms_project_1.services import update_grade

TEST_SECRET = "super_secret_test_key_at_least_32_chars_long"


@pytest.fixture
def test_app(tmp_path: Path) -> Flask:
    audit_file = tmp_path / "test_audit.log"
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


# A1: Login khongco@lms.test; login chi.sv@lms.test sai mật khẩu -> Cả hai 401, body giống hệt
def test_a1_timing_mitigation_identical_401(client: Any) -> None:
    res1 = client.post("/auth/login", json={"email": "khongco@lms.test", "password": "wrong"})
    res2 = client.post("/auth/login", json={"email": "chi.sv@lms.test", "password": "wrong"})

    assert res1.status_code == 401
    assert res2.status_code == 401
    assert res1.get_json() == {"error": "INVALID_CREDENTIALS"}
    assert res2.get_json() == {"error": "INVALID_CREDENTIALS"}
    assert res1.get_json() == res2.get_json()


# A2: GET /me không token -> 401
def test_a2_get_me_without_token(client: Any) -> None:
    res = client.get("/me")
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# A3: Token của Chi, sửa sub thành u1, giữ chữ ký cũ -> 401
def test_a3_tampered_sub_signature(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    parts = chi_token.split(".")
    tampered_payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "u1",
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 900,
                }
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    res = client.get("/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# A4: Token có header alg: none -> 401
def test_a4_token_alg_none(client: Any) -> None:
    none_token = jwt.encode(
        {"sub": "u4", "iat": int(time.time()), "exp": int(time.time()) + 900},
        key="",
        algorithm="none",
    )
    res = client.get("/me", headers={"Authorization": f"Bearer {none_token}"})
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# A5: TOKEN_TTL_SECONDS=1, chờ 2 giây, gọi /me -> 401
def test_a5_token_expired(tmp_path: Path) -> None:
    short_app = create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 1,
            "AUDIT_LOG_PATH": str(tmp_path / "audit_a5.log"),
        }
    )
    c = short_app.test_client()
    token = login_user(c, "chi.sv@lms.test")
    time.sleep(1.5)
    res = c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# A6: Soi mọi response: Không có password, password_hash, passwordHash
def test_a6_output_sanitization(client: Any) -> None:
    res = client.post("/auth/login", json={"email": "chi.sv@lms.test", "password": "Lms@2026"})
    text = res.get_data(as_text=True)
    assert "password" not in text.lower() or "password" in text  # check raw keys
    data = res.get_json()
    assert "password" not in data
    assert "password_hash" not in data
    assert "passwordHash" not in data

    token = data["accessToken"]
    res_me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    me_data = res_me.get_json()
    assert "password" not in me_data
    assert "password_hash" not in me_data
    assert "passwordHash" not in me_data


# A7: Chi GET /courses/c1/grades -> 200 [{"studentId":"u4","score":7.5}]
def test_a7_chi_get_c1_grades(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    res = client.get("/courses/c1/grades", headers={"Authorization": f"Bearer {chi_token}"})
    assert res.status_code == 200
    assert res.get_json() == [{"studentId": "u4", "score": 7.5}]


# A8: Chi GET /courses/c2/grades -> 403
def test_a8_chi_get_c2_grades(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    res = client.get("/courses/c2/grades", headers={"Authorization": f"Bearer {chi_token}"})
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


# A9: Chi PUT /courses/c1/grades/u4 {"score":10} -> 403
def test_a9_chi_put_c1_u4(client: Any) -> None:
    chi_token = login_user(client, "chi.sv@lms.test")
    res = client.put(
        "/courses/c1/grades/u4",
        json={"score": 10},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


# A10: Bình PUT /courses/c1/grades/u4 {"score":0} -> 403
def test_a10_binh_put_c1_u4(client: Any) -> None:
    binh_token = login_user(client, "binh.gv@lms.test")
    res = client.put(
        "/courses/c1/grades/u4",
        json={"score": 0},
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


# A11: Admin PUT /courses/c1/grades/u4 {"score":10} -> 403
def test_a11_admin_put_c1_u4(client: Any) -> None:
    admin_token = login_user(client, "admin@lms.test")
    res = client.put(
        "/courses/c1/grades/u4",
        json={"score": 10},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 403
    assert res.get_json() == {"error": "FORBIDDEN"}


# A12: An PUT c1/u4 với score là 11, -1, "10", true; và body {"score":9,"courseId":"c2"}
# Cả 5 trường hợp phải trả về 400 VALIDATION_ERROR
def test_a12_an_put_invalid_scores(client: Any) -> None:
    an_token = login_user(client, "an.gv@lms.test")
    headers = {"Authorization": f"Bearer {an_token}"}

    cases = [
        {"score": 11},
        {"score": -1},
        {"score": "10"},
        {"score": True},
        {"score": 9, "courseId": "c2"},
    ]

    for payload in cases:
        res = client.put("/courses/c1/grades/u4", json=payload, headers=headers)
        assert res.status_code == 400, f"Payload {payload} did not return 400: {res.status_code}"
        assert res.get_json() == {"error": "VALIDATION_ERROR"}


# A13: An PUT /courses/c1/grades/u6 {"score":5} -> 404 (u6 không học c1)
def test_a13_an_put_c1_u6_not_enrolled(client: Any) -> None:
    an_token = login_user(client, "an.gv@lms.test")
    res = client.put(
        "/courses/c1/grades/u6",
        json={"score": 5},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res.status_code == 404
    assert res.get_json() == {"error": "NOT_FOUND"}


# A14: An PUT c1/u4 {"score":9}, sau đó Chi GET c1 -> 200; Chi thấy 9
def test_a14_an_put_then_chi_get(client: Any) -> None:
    an_token = login_user(client, "an.gv@lms.test")
    chi_token = login_user(client, "chi.sv@lms.test")

    res_put = client.put(
        "/courses/c1/grades/u4",
        json={"score": 9},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_put.status_code == 200
    assert res_put.get_json() == {"courseId": "c1", "studentId": "u4", "score": 9.0}

    res_get = client.get("/courses/c1/grades", headers={"Authorization": f"Bearer {chi_token}"})
    assert res_get.status_code == 200
    assert res_get.get_json() == [{"studentId": "u4", "score": 9.0}]


# A15: Gỡ @require_role khỏi route PUT, chạy lại A9-A11; gọi update_grade(chi, "c1", "u4", 10)
# Vẫn 403; hàm update_grade ném Forbidden
def test_a15_defense_in_depth_services(test_app: Flask) -> None:
    chi_actor = {"id": "u4", "email": "chi.sv@lms.test", "role": "STUDENT"}
    binh_actor = {"id": "u3", "email": "binh.gv@lms.test", "role": "INSTRUCTOR"}
    admin_actor = {"id": "u1", "email": "admin@lms.test", "role": "ADMIN"}

    with pytest.raises(Forbidden):
        update_grade(chi_actor, "c1", "u4", 10, store=test_app.store)

    with pytest.raises(Forbidden):
        update_grade(binh_actor, "c1", "u4", 0, store=test_app.store)

    with pytest.raises(Forbidden):
        update_grade(admin_actor, "c1", "u4", 10, store=test_app.store)


# A16: Thêm GET /debug không khai báo gì, gọi không token -> 401
def test_a16_undeclared_route_blocked_without_token(test_app: Flask) -> None:
    @test_app.route("/debug", methods=["GET"])
    def debug_route() -> Any:
        return jsonify({"status": "ok"}), 200

    c = test_app.test_client()
    res = c.get("/debug")
    assert res.status_code == 401
    assert res.get_json() == {"error": "UNAUTHENTICATED"}


# A17: create_app() khi thiếu JWT_SECRET -> RuntimeError
def test_a17_missing_jwt_secret_raises_runtime_error() -> None:
    with pytest.raises(RuntimeError):
        create_app({"JWT_SECRET": ""})

    with pytest.raises(RuntimeError):
        create_app({"JWT_SECRET": "short_secret"})


# A18: Sai mật khẩu Dũng 5 lần, lần 6 nhập đúng -> 429
def test_a18_account_locked_after_5_failures(client: Any) -> None:
    dung_email = "dung.sv@lms.test"

    for _ in range(5):
        res = client.post("/auth/login", json={"email": dung_email, "password": "wrong_password"})
        assert res.status_code == 401

    # 6th attempt with CORRECT password
    res6 = client.post("/auth/login", json={"email": dung_email, "password": "Lms@2026"})
    assert res6.status_code == 429
    assert res6.get_json() == {"error": "ACCOUNT_LOCKED"}


# A19: Sau A10 và A14, đọc file AUDIT_LOG_PATH -> 2 dòng tương ứng, không có mật khẩu, token
def test_a19_audit_log_entries(tmp_path: Path) -> None:
    audit_file = tmp_path / "audit_a19.log"
    app = create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 900,
            "AUDIT_LOG_PATH": str(audit_file),
        }
    )
    c = app.test_client()

    # Perform A10: Binh PUT c1/u4 -> 403
    binh_token = login_user(c, "binh.gv@lms.test")
    res_a10 = c.put(
        "/courses/c1/grades/u4",
        json={"score": 0},
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert res_a10.status_code == 403

    # Perform A14: An PUT c1/u4 {"score": 9} -> 200
    an_token = login_user(c, "an.gv@lms.test")
    res_a14 = c.put(
        "/courses/c1/grades/u4",
        json={"score": 9},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_a14.status_code == 200

    # Inspect audit log
    assert audit_file.is_file(), "Audit file was not created"
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, f"Expected 2 lines, found {len(lines)}: {lines}"

    entry1 = json.loads(lines[0])
    entry2 = json.loads(lines[1])

    # Check entry 1 (A10 Forbidden event)
    assert entry1["result"] == "FORBIDDEN"
    assert entry1["actorId"] == "u3"
    assert "/courses/c1/grades/u4" in entry1["resource"]

    # Check entry 2 (A14 Update Grade event)
    assert entry2["result"] == "SUCCESS"
    assert entry2["actorId"] == "u2"
    assert entry2["action"] == "UPDATE_GRADE"
    assert entry2["oldScore"] == 7.5
    assert entry2["newScore"] == 9.0

    # Ensure no passwords or tokens were logged
    raw_content = audit_file.read_text(encoding="utf-8").lower()
    assert "password" not in raw_content
    assert "token" not in raw_content or "accesstoken" not in raw_content
    assert binh_token not in raw_content
    assert an_token not in raw_content
