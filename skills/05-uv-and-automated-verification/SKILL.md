---
name: uv-and-automated-verification
description: Code tham chiếu hoàn chỉnh cho các module trong app/ và bộ kiểm thử pytest tự động kiểm tra 100% kịch bản A1-A19 cùng tính năng Web App mở rộng.
---

# ✅ SKILL 05: CODE THAM CHIẾU HOÀN CHỈNH & BỘ TEST TỰ ĐỘNG A1–A19

Antigravity hãy đối chiếu và cập nhật các file trong dự án theo đúng chuẩn dưới đây, sau đó chạy `uv run pytest -v` để xác nhận **100% PASS**.

---

## 1. Code chuẩn cho `app/auth.py` (Lớp 1 & Lớp 7)

```python
import time
from typing import Any
import bcrypt
import jwt
from app.errors import InvalidCredentials, Unauthenticated, AccountLocked, ValidationError
from app.store import store
from app.audit import write_audit_log

# Dummy hash khởi tạo 1 lần để chống timing/user enumeration khi email không tồn tại (Lớp 1 - A1)
_DUMMY_HASH: bytes = bcrypt.hashpw(b"DummyPassword@2026", bcrypt.gensalt(rounds=10))

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 phút (Lớp 7 - A18)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(user_id: str, secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    # JWT HS256 chỉ chứa đúng sub, iat, exp theo yêu cầu mục 3
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        # Bắt buộc truyền algorithms=["HS256"] để chặn alg: none (A4) và chữ ký giả (A3)
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        return payload
    except Exception as exc:
        raise Unauthenticated() from exc


def _check_and_update_lockout(email_key: str) -> dict[str, Any]:
    now = time.time()
    record = store.login_attempts.get(email_key)
    if not record:
        record = {"count": 0, "locked_until": 0.0}
        store.login_attempts[email_key] = record

    if record["locked_until"] > now:
        raise AccountLocked()

    # Nếu đã hết thời gian khóa 15 phút thì reset lại bộ đếm
    if record["locked_until"] != 0.0 and record["locked_until"] <= now:
        record["count"] = 0
        record["locked_until"] = 0.0

    return record


def _record_failed_attempt(email_key: str) -> None:
    now = time.time()
    record = store.login_attempts.setdefault(email_key, {"count": 0, "locked_until": 0.0})
    record["count"] += 1
    if record["count"] >= MAX_FAILED_ATTEMPTS:
        record["locked_until"] = now + LOCKOUT_DURATION_SECONDS


def authenticate_user(email: str, password: str, secret: str, ttl_seconds: int) -> dict[str, Any]:
    email_key = email.strip().lower()
    attempt_record = _check_and_update_lockout(email_key)

    user = store.get_user_by_email(email_key)
    if not user:
        # Chạy checkpw giả để thời gian xử lý tương đương và trả lỗi giống hệt (A1)
        bcrypt.checkpw(password.encode("utf-8"), _DUMMY_HASH)
        _record_failed_attempt(email_key)
        raise InvalidCredentials()

    if not verify_password(password, user["password_hash"]):
        _record_failed_attempt(email_key)
        raise InvalidCredentials()

    # Đăng nhập đúng trước ngưỡng -> reset bộ đếm (Lớp 7)
    attempt_record["count"] = 0
    attempt_record["locked_until"] = 0.0

    token = create_access_token(user["id"], secret=secret, ttl_seconds=ttl_seconds)
    return {
        "accessToken": token,
        "expiresIn": int(ttl_seconds),
    }


def register_new_user(email: str, password: str, role: str = "STUDENT") -> dict[str, str]:
    email_key = email.strip().lower()
    if store.get_user_by_email(email_key) is not None:
        raise ValidationError()

    norm_role = role.strip().upper()
    if norm_role == "TEACHER":
        norm_role = "INSTRUCTOR"
    if norm_role not in {"STUDENT", "INSTRUCTOR", "GUEST"}:
        raise ValidationError()

    new_index = len(store.users_by_id) + 1
    new_id = f"u{new_index}"
    while new_id in store.users_by_id:
        new_index += 1
        new_id = f"u{new_index}"

    user_record = {
        "id": new_id,
        "email": email_key,
        "password_hash": hash_password(password),
        "role": norm_role,
    }
    store.users_by_id[new_id] = user_record
    store.users_by_email[email_key] = user_record
    store.id_aliases[new_id] = new_id

    write_audit_log(
        actor_id=new_id,
        action="REGISTER_USER",
        resource=f"/users/{new_id}",
        result="SUCCESS",
    )
    return {
        "id": new_id,
        "email": email_key,
        "role": norm_role,
    }


def reset_user_password(email: str, new_password: str) -> dict[str, str]:
    email_key = email.strip().lower()
    _check_and_update_lockout(email_key)

    user = store.get_user_by_email(email_key)
    if not user:
        # Không tiết lộ email tồn tại hay không, hoặc báo lỗi validation
        bcrypt.checkpw(new_password.encode("utf-8"), _DUMMY_HASH)
        raise ValidationError()

    user["password_hash"] = hash_password(new_password)
    store.login_attempts[email_key] = {"count": 0, "locked_until": 0.0}

    write_audit_log(
        actor_id=user["id"],
        action="RESET_PASSWORD",
        resource=f"/users/{user['id']}",
        result="SUCCESS",
    )
    return {"status": "PASSWORD_UPDATED"}
```

---

## 2. Code chuẩn cho `app/services.py` (Lớp 4 - Tuyệt đối không import Flask)

```python
from typing import Any
from app.errors import Forbidden, NotFound, ValidationError
from app.schemas import validate_score_value
from app.store import store
from app.audit import write_audit_log


def _validate_actor(actor: Any) -> tuple[str, str]:
    if not isinstance(actor, dict):
        raise Forbidden()
    actor_id = actor.get("id")
    actor_role = str(actor.get("role", "")).upper()
    if actor_role == "TEACHER":
        actor_role = "INSTRUCTOR"
    if not actor_id or not isinstance(actor_id, str) or not actor_role:
        raise Forbidden()
    return store.resolve_user_id(actor_id), actor_role


def assert_can_update_course(actor: dict[str, Any], course_id: str) -> dict[str, Any]:
    """
    Kiểm tra thứ tự: 404 (môn không tồn tại) -> 403 (không phải GV dạy môn đó).
    Hàm này được dùng trước khi validate body ở PUT route và được gọi lại độc lập trong update_grade().
    """
    actor_id, actor_role = _validate_actor(actor)
    course = store.courses_by_id.get(course_id)
    if not course:
        raise NotFound()

    if actor_role != "INSTRUCTOR" or course.get("instructorId") != actor_id:
        write_audit_log(
            actor_id=actor_id,
            action="UPDATE_GRADE",
            resource=f"/courses/{course_id}/grades",
            result="FORBIDDEN",
        )
        raise Forbidden()

    return course


def get_grades(actor: dict[str, Any], course_id: str) -> list[dict[str, Any]]:
    actor_id, actor_role = _validate_actor(actor)

    # Thứ tự kiểm tra: 404 (môn) -> 403 (quyền)
    course = store.courses_by_id.get(course_id)
    if not course:
        raise NotFound()

    if actor_role == "ADMIN":
        return [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id
        ]

    if actor_role == "INSTRUCTOR":
        if course.get("instructorId") != actor_id:
            write_audit_log(
                actor_id=actor_id,
                action="GET_GRADES",
                resource=f"/courses/{course_id}/grades",
                result="FORBIDDEN",
            )
            raise Forbidden()
        return [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id
        ]

    if actor_role == "STUDENT":
        own_records = [
            {"studentId": e["studentId"], "score": e["score"]}
            for e in store.enrollments
            if e["courseId"] == course_id and e["studentId"] == actor_id
        ]
        if not own_records:
            write_audit_log(
                actor_id=actor_id,
                action="GET_GRADES",
                resource=f"/courses/{course_id}/grades",
                result="FORBIDDEN",
            )
            raise Forbidden()
        return own_records

    # GUEST hoặc bất kỳ role nào khác
    write_audit_log(
        actor_id=actor_id,
        action="GET_GRADES",
        resource=f"/courses/{course_id}/grades",
        result="FORBIDDEN",
    )
    raise Forbidden()


def update_grade(
    actor: dict[str, Any],
    course_id: str,
    student_id: str,
    score: Any,
) -> dict[str, Any]:
    actor_id, _ = _validate_actor(actor)

    # Bước 1 & 2: 404 (môn) -> 403 (quyền đối tượng, độc lập hoàn toàn với lớp 3 @require_role)
    assert_can_update_course(actor, course_id)

    # Bước 3: 400 (Service tự kiểm tra lại miền giá trị theo yêu cầu Lớp 5)
    validated_score = validate_score_value(score)

    # Bước 4: 404 (Kiểm tra sinh viên có ghi danh vào môn học không - Kịch bản A13)
    resolved_student_id = store.resolve_user_id(student_id)
    target_enrollment = None
    for e in store.enrollments:
        if e["courseId"] == course_id and (
            e["studentId"] == resolved_student_id or e["studentId"] == student_id
        ):
            target_enrollment = e
            break

    if target_enrollment is None:
        raise NotFound()

    old_score = target_enrollment["score"]
    target_enrollment["score"] = validated_score

    # Bước 5: Ghi Audit Log (Lớp 8 - Kịch bản A19)
    write_audit_log(
        actor_id=actor_id,
        action="UPDATE_GRADE",
        resource=f"/courses/{course_id}/grades/{target_enrollment['studentId']}",
        result="SUCCESS",
        old_score=old_score,
        new_score=validated_score,
    )

    return {
        "courseId": course_id,
        "studentId": target_enrollment["studentId"],
        "score": validated_score,
    }
```

---

## 3. Code chuẩn cho `app/__init__.py`

```python
import os
from pathlib import Path
from typing import Any
from flask import Flask, jsonify, request, g, render_template

from app.store import store
from app.audit import configure_audit, read_audit_logs
from app.errors import register_error_handlers, ValidationError
from app.gate import init_gate
from app.guards import require_role
from app.auth import authenticate_user, register_new_user, reset_user_password
from app.schemas import (
    validate_login_body,
    validate_put_grade_body,
)
from app import services


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)

    # 1. Nạp cấu hình từ biến môi trường, sau đó ghi đè bằng dict config truyền vào
    jwt_secret = os.environ.get("JWT_SECRET", "")
    token_ttl = int(os.environ.get("TOKEN_TTL_SECONDS", "900"))
    audit_log_path = os.environ.get("AUDIT_LOG_PATH", "audit.log")
    seed_path = os.environ.get("SEED_PATH", "seed.json")

    if config:
        if "JWT_SECRET" in config:
            jwt_secret = config["JWT_SECRET"]
        if "TOKEN_TTL_SECONDS" in config:
            token_ttl = int(config["TOKEN_TTL_SECONDS"])
        if "AUDIT_LOG_PATH" in config:
            audit_log_path = config["AUDIT_LOG_PATH"]
        if "SEED_PATH" in config:
            seed_path = config["SEED_PATH"]
        app.config.update(config)

    # 2. Fail-closed khi thiếu hoặc JWT_SECRET < 32 ký tự (Lớp 6 - Kịch bản A17)
    if not jwt_secret or not isinstance(jwt_secret, str) or len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET is required and must be at least 32 characters.")

    app.config["JWT_SECRET"] = jwt_secret
    app.config["TOKEN_TTL_SECONDS"] = token_ttl
    app.config["AUDIT_LOG_PATH"] = audit_log_path

    # 3. Khởi tạo lại Audit Log path và nạp lại seed.json tạo state mới
    configure_audit(audit_log_path)
    if not Path(seed_path).exists():
        # Fallback tìm ở thư mục gốc dự án
        root_seed = Path(__file__).resolve().parent.parent / "seed.json"
        seed_path = str(root_seed)
    store.load_seed(seed_path)

    # 4. Đăng ký Error Handlers (Lớp 6) & Global Gate (Lớp 2)
    register_error_handlers(app)
    init_gate(app)

    # =========================================================================
    # 4 ENDPOINT BẮT BUỘC TRONG ĐỀ BÀI
    # =========================================================================

    @app.post("/auth/login")
    def login_route():
        body = request.get_json(silent=True)
        email, password = validate_login_body(body)
        result = authenticate_user(
            email=email,
            password=password,
            secret=app.config["JWT_SECRET"],
            ttl_seconds=app.config["TOKEN_TTL_SECONDS"],
        )
        return jsonify(result), 200

    @app.get("/me")
    @require_role("ADMIN", "INSTRUCTOR", "STUDENT", "GUEST")
    def me_route():
        actor = g.current_actor
        return jsonify(
            {
                "id": actor["id"],
                "email": actor["email"],
                "role": actor["role"],
            }
        ), 200

    @app.get("/courses/<course_id>/grades")
    @require_role("ADMIN", "INSTRUCTOR", "STUDENT")
    def get_course_grades_route(course_id: str):
        actor = g.current_actor
        grades = services.get_grades(actor, course_id)
        return jsonify(grades), 200

    @app.put("/courses/<course_id>/grades/<student_id>")
    @require_role("INSTRUCTOR")
    def put_course_grade_route(course_id: str, student_id: str):
        actor = g.current_actor
        # Đảm bảo thứ tự: 401 -> 404 (môn) -> 403 (quyền) -> 400 (body) -> 404 (ghi danh)
        # Kể cả khi giảng viên gỡ @require_role("INSTRUCTOR") khỏi route này (Kịch bản A15)
        services.assert_can_update_course(actor, course_id)
        body = request.get_json(silent=True)
        score = validate_put_grade_body(body)
        updated = services.update_grade(actor, course_id, student_id, score)
        return jsonify(updated), 200

    # =========================================================================
    # CÁC ENDPOINT MỞ RỘNG CHO WEB APP LMS 4 ROLES & HOME PAGE HIỆN ĐẠI
    # =========================================================================

    @app.get("/")
    def home_page():
        return render_template("index.html")

    @app.get("/api/public/courses")
    def public_courses_route():
        result = []
        for cid, c in store.courses_by_id.items():
            inst = store.get_user_by_id(c["instructorId"])
            enrolled_count = sum(1 for e in store.enrollments if e["courseId"] == cid)
            result.append(
                {
                    "id": cid,
                    "title": c["title"],
                    "instructorId": c["instructorId"],
                    "instructorEmail": inst["email"] if inst else "",
                    "enrolledCount": enrolled_count,
                }
            )
        return jsonify(result), 200

    @app.post("/auth/register")
    def register_route():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValidationError()
        allowed_keys = {"email", "password", "role"}
        if (
            not set(body.keys()).issubset(allowed_keys)
            or "email" not in body
            or "password" not in body
        ):
            raise ValidationError()
        email = body.get("email")
        password = body.get("password")
        role = body.get("role", "STUDENT")
        if not isinstance(email, str) or not isinstance(password, str) or not isinstance(role, str):
            raise ValidationError()
        if len(password) < 6 or "@" not in email:
            raise ValidationError()
        user_info = register_new_user(email=email, password=password, role=role)
        return jsonify(user_info), 201

    @app.post("/auth/reset-password")
    def reset_password_route():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body.keys()) != {"email", "newPassword"}:
            raise ValidationError()
        email = body.get("email")
        new_pw = body.get("newPassword")
        if not isinstance(email, str) or not isinstance(new_pw, str) or len(new_pw) < 6:
            raise ValidationError()
        res = reset_user_password(email=email, new_password=new_pw)
        return jsonify(res), 200

    @app.get("/api/admin/audit-logs")
    @require_role("ADMIN")
    def admin_audit_logs_route():
        return jsonify(read_audit_logs(limit=100)), 200

    return app
```

---

## 4. Bộ Kiểm Thử Tự Động `tests/test_defense_in_depth.py` (Bao phủ A1 -> A19)

Antigravity hãy tạo file `tests/test_defense_in_depth.py` dưới đây và chạy `uv run pytest -v`:

```python
import json
import time
import jwt
import pytest
from app import create_app
from app import services
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
    import base64

    payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
    payload["sub"] = "u1"
    tampered_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    r = client.get("/me", headers=auth_header(tampered_token))
    assert r.status_code == 401


def test_a4_alg_none_token(client):
    import base64

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
```
