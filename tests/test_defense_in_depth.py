from __future__ import annotations

import base64
import json
import time

import pytest
from app import create_app, services
from app.errors import Forbidden

TEST_SECRET = "super-secret-jwt-key-with-at-least-32-bytes-length!"


@pytest.fixture()
def app_ctx(tmp_path):
    audit_file = tmp_path / "audit.log"
    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 900,
            "AUDIT_LOG_PATH": str(audit_file),
        }
    )
    return app, audit_file


@pytest.fixture()
def client(app_ctx):
    app, _ = app_ctx
    return app.test_client()


def login(client, email, password="Lms@2026"):
    return client.post("/auth/login", json={"email": email, "password": password})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a1_login_unknown_and_wrong_password_identical(client):
    r1 = login(client, "khongco@lms.test", "wrong")
    r2 = login(client, "chi.sv@lms.test", "wrong")
    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r1.get_json() == r2.get_json() == {"error": "INVALID_CREDENTIALS"}


def test_a2_get_me_without_token(client):
    r = client.get("/me")
    assert r.status_code == 401
    assert r.get_json() == {"error": "UNAUTHENTICATED"}


def test_a3_tampered_sub_in_token(client):
    token = login(client, "chi.sv@lms.test").get_json()["accessToken"]
    parts = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    payload["sub"] = "u1"
    tampered_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    r = client.get("/me", headers=auth_header(tampered_token))
    assert r.status_code == 401


def test_a4_alg_none_token(client):
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"sub": "u1", "iat": int(time.time()), "exp": int(time.time()) + 900}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )
    none_token = f"{header}.{payload}."
    r = client.get("/me", headers=auth_header(none_token))
    assert r.status_code == 401


def test_a5_expired_token(tmp_path):
    app = create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 1,
            "AUDIT_LOG_PATH": str(tmp_path / "audit.log"),
        }
    )
    c = app.test_client()
    token = login(c, "chi.sv@lms.test").get_json()["accessToken"]
    time.sleep(2.1)
    r = c.get("/me", headers=auth_header(token))
    assert r.status_code == 401


def test_a6_no_sensitive_fields_in_responses(client):
    res_login = login(client, "chi.sv@lms.test")
    token = res_login.get_json()["accessToken"]
    for resp in [
        res_login,
        client.get("/me", headers=auth_header(token)),
        client.get("/courses/c1/grades", headers=auth_header(token)),
    ]:
        text = resp.get_data(as_text=True)
        assert "password" not in text.lower()


def test_a7_and_a8_student_get_grades(client):
    token = login(client, "chi.sv@lms.test").get_json()["accessToken"]
    # A7: Chi GET c1 -> 200 [{"studentId": "u4", "score": 7.5}]
    r1 = client.get("/courses/c1/grades", headers=auth_header(token))
    assert r1.status_code == 200
    assert r1.get_json() == [{"studentId": "u4", "score": 7.5}]

    # A8: Chi GET c2 -> 403
    r2 = client.get("/courses/c2/grades", headers=auth_header(token))
    assert r2.status_code == 403


def test_a9_a10_a11_forbidden_put_grades(client):
    chi_token = login(client, "chi.sv@lms.test").get_json()["accessToken"]
    binh_token = login(client, "binh.gv@lms.test").get_json()["accessToken"]
    admin_token = login(client, "admin@lms.test").get_json()["accessToken"]

    # A9: Chi PUT c1/u4
    assert (
        client.put(
            "/courses/c1/grades/u4", json={"score": 10}, headers=auth_header(chi_token)
        ).status_code
        == 403
    )
    # A10: Bình PUT c1/u4
    assert (
        client.put(
            "/courses/c1/grades/u4", json={"score": 0}, headers=auth_header(binh_token)
        ).status_code
        == 403
    )
    # A11: Admin PUT c1/u4
    assert (
        client.put(
            "/courses/c1/grades/u4", json={"score": 10}, headers=auth_header(admin_token)
        ).status_code
        == 403
    )


def test_a12_validation_errors(client):
    an_token = login(client, "an.gv@lms.test").get_json()["accessToken"]
    invalid_payloads = [
        {"score": 11},
        {"score": -1},
        {"score": "10"},
        {"score": True},
        {"score": 9, "courseId": "c2"},
    ]
    for body in invalid_payloads:
        r = client.put("/courses/c1/grades/u4", json=body, headers=auth_header(an_token))
        assert r.status_code == 400, f"Failed for payload: {body}"
        assert r.get_json() == {"error": "VALIDATION_ERROR"}


def test_a13_put_unenrolled_student_returns_404(client):
    an_token = login(client, "an.gv@lms.test").get_json()["accessToken"]
    r = client.put("/courses/c1/grades/u6", json={"score": 5}, headers=auth_header(an_token))
    assert r.status_code == 404
    assert r.get_json() == {"error": "NOT_FOUND"}


def test_a14_update_and_verify_new_score(client):
    an_token = login(client, "an.gv@lms.test").get_json()["accessToken"]
    chi_token = login(client, "chi.sv@lms.test").get_json()["accessToken"]

    r_put = client.put("/courses/c1/grades/u4", json={"score": 9}, headers=auth_header(an_token))
    assert r_put.status_code == 200
    assert r_put.get_json() == {"courseId": "c1", "studentId": "u4", "score": 9.0}

    r_get = client.get("/courses/c1/grades", headers=auth_header(chi_token))
    assert r_get.status_code == 200
    assert r_get.get_json() == [{"studentId": "u4", "score": 9.0}]


def test_a15_service_layer_blocks_direct_call_without_route_guard(client):
    chi = {"id": "u4", "email": "chi.sv@lms.test", "role": "STUDENT"}
    with pytest.raises(Forbidden):
        services.update_grade(chi, "c1", "u4", 10)


def test_a16_undeclared_new_route_blocked_by_gate(app_ctx):
    app, _ = app_ctx

    @app.get("/debug")
    def debug_route():
        return {"debug": True}, 200

    c = app.test_client()
    r = c.get("/debug")
    assert r.status_code == 401
    assert r.get_json() == {"error": "UNAUTHENTICATED"}


def test_a17_missing_jwt_secret_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        create_app({})


def test_a18_brute_force_lockout(client):
    for _ in range(5):
        r = login(client, "dung.sv@lms.test", "WrongPass")
        assert r.status_code == 401
    # Lần thứ 6 nhập ĐÚNG mật khẩu vẫn phải trả 429 ACCOUNT_LOCKED
    r6 = login(client, "dung.sv@lms.test", "Lms@2026")
    assert r6.status_code == 429
    assert r6.get_json() == {"error": "ACCOUNT_LOCKED"}


def test_a19_audit_log_entries_and_no_secrets(app_ctx):
    app, audit_file = app_ctx
    c = app.test_client()
    binh_token = login(c, "binh.gv@lms.test").get_json()["accessToken"]
    an_token = login(c, "an.gv@lms.test").get_json()["accessToken"]

    # A10: Bình PUT c1/u4 -> 403
    c.put("/courses/c1/grades/u4", json={"score": 0}, headers=auth_header(binh_token))
    # A14: An PUT c1/u4 -> 200
    c.put("/courses/c1/grades/u4", json={"score": 9}, headers=auth_header(an_token))

    content = audit_file.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in content.splitlines() if line.strip()]
    assert len(lines) >= 2
    assert "Lms@2026" not in content
    assert binh_token not in content
    assert an_token not in content
