---
name: defense-in-depth-core
description: Thiết kế và cài đặt chuẩn xác 8 lớp bảo vệ độc lập (Defense in Depth) cho LMS Flask theo đúng cấu trúc file và kịch bản chấm A1-A19.
---

# 🛡️ SKILL 02: LÕI 8 LỚP BẢO VỆ ĐỘC LẬP (DEFENSE IN DEPTH CORE)

## 1. Kiến trúc & Cấu trúc File Bắt Buộc

Antigravity phải đảm bảo cây thư mục dự án có đầy đủ các file sau:
```text
project_root/
├── app/
│   ├── __init__.py      # create_app(config=None), đăng ký routes, gate, error handlers
│   ├── store.py         # Nạp seed.json vào RAM, băm mật khẩu ngay khi nạp, không lưu bản rõ
│   ├── auth.py          # Lớp 1 (Băm MK, JWT HS256, Login) & Lớp 7 (Chống Brute-force 5 lần/15p)
│   ├── gate.py          # Lớp 2 (before_request toàn cục mặc định từ chối - Default Deny)
│   ├── guards.py        # Lớp 3 (Decorator @require_role(*roles))
│   ├── services.py      # Lớp 4 (Kiểm tra quyền trên đối tượng, KHÔNG import flask)
│   ├── schemas.py       # Lớp 5 (Validate body chặt chẽ, chống type coercion boolean/string)
│   ├── errors.py        # Lớp 6 (Custom Exceptions & JSON Error Handlers toàn cục)
│   ├── audit.py         # Lớp 8 (Ghi JSON audit log cho mỗi lần sửa điểm và mỗi lần 403)
│   └── templates/       # Giao diện Web App LMS hiện đại (tách biệt, không ảnh hưởng JSON API)
│       └── index.html
├── tests/
│   └── test_all.py      # Bộ test tự động A1 -> A19 + Extended LMS
├── seed.json            # Dữ liệu khởi tạo
├── .env.example         # File mẫu biến môi trường (không chứa secret thật)
├── pyproject.toml       # Cấu hình dự án uv
└── requirements.txt     # Danh sách gói phục vụ chấm điểm
```

---

## 2. Quy tắc Thứ tự Kiểm tra (Check Order) Cực Kỳ Quan Trọng

Đề bài quy định rõ thứ tự kiểm tra khi xử lý request:
> **`401` (Xác thực) $ightarrow$ `404` (Môn học không tồn tại) $ightarrow$ `403` (Không đủ quyền) $ightarrow$ `400` (Body/Dữ liệu đầu vào sai) $ightarrow$ `404` (Sinh viên không ghi danh vào môn khi PUT)**

**Giải thích tại sao thứ tự này quan trọng cho các câu A9, A10, A11, A12, A13, A15:**
1. **`401 UNAUTHENTICATED`**: Kiểm tra ở `gate.py` (`before_request`) đầu tiên.
2. **`404 NOT_FOUND` (Môn học)**: Trong `services.py` (và trước khi validate body ở route `PUT`), nếu `course_id` không tồn tại trong `store` -> ném `NotFound("NOT_FOUND")` (404).
3. **`403 FORBIDDEN` (Quyền vai trò & Quyền đối tượng)**:
   - Ở Lớp 3 (`@require_role`) và Lớp 4 (`services.py`):
   - Với `PUT /courses/<course_id>/grades/<student_id>`: Chỉ `INSTRUCTOR` dạy chính môn `course_id` đó mới có quyền. Nếu `ADMIN` (A11), `STUDENT` (A9), hoặc `INSTRUCTOR` dạy môn khác (A10 - Bình PUT môn c1 của An) gọi vào -> phải trả `403 FORBIDDEN` (và ghi Audit Log) **TRƯỚC KHI** kiểm tra body hay kiểm tra sinh viên ghi danh!
   - Lưu ý: Khi giảng viên gỡ `@require_role` khỏi route `PUT` và gọi `PUT` với body hợp lệ, hoặc gọi trực tiếp `update_grade(chi, "c1", "u4", 10)` trong Python (Kịch bản A15), hàm `update_grade` trong `services.py` phải tự kiểm tra quyền của `actor` trước rồi mới kiểm tra `score` và `enrollment`!
4. **`400 VALIDATION_ERROR` (Đầu vào)**:
   - Sau khi đã xác nhận người gọi là Giảng viên dạy môn đó (hoặc kiểm tra schema kết hợp kiểm tra quyền), nếu body không phải JSON object, thiếu `score`, có field thừa (ví dụ `{"score": 9, "courseId": "c2"}`), hoặc `score` là `"10"` (string), `True`/`False` (boolean), hoặc ngoài đoạn `[0, 10]` -> trả `400 {"error": "VALIDATION_ERROR"}` (Kịch bản A12).
   - **Mẹo kỹ thuật để đảm bảo cả khi gỡ `@require_role` vẫn đúng thứ tự `401 -> 404 (môn) -> 403 -> 400 -> 404 (ghi danh)`**:
     Trong route `PUT /courses/<course_id>/grades/<student_id>`, có thể gọi kiểm tra quyền môn học hoặc truyền raw payload/score xuống theo đúng thứ tự:
     - Bước 1: Kiểm tra môn `course_id` có tồn tại không (`404`) và `actor` có phải giảng viên dạy `course_id` không (`403`).
     - Bước 2: Validate body bằng `schemas.py` (`400`).
     - Bước 3: Gọi `services.update_grade(actor, course_id, student_id, score)` — bên trong `services.update_grade` **LẶP LẠI** đầy đủ cả 4 kiểm tra độc lập:
       1. Kiểm tra `course_id` tồn tại (`NotFound`).
       2. Kiểm tra `actor["role"] == "INSTRUCTOR"` và `course["instructorId"] == actor["id"]` (`Forbidden`).
       3. Kiểm tra lại miền giá trị và kiểu của `score` (không phải `bool`, là `int | float`, `0 <= score <= 10`) (`ValidationError`).
       4. Kiểm tra `(course_id, student_id)` có trong `enrollments` không (`NotFound` - Kịch bản A13: An PUT điểm c1 cho u6 trả `404`).

---

## 3. Chi tiết Cài đặt Từng Module Lõi

### 3.1. `app/errors.py` (Lớp 6: Đầu ra & Fail-Closed)
```python
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, error_code: str | None = None, status_code: int | None = None):
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.error_code)


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class InvalidCredentials(AppError):
    status_code = 401
    error_code = "INVALID_CREDENTIALS"


class Unauthenticated(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class AccountLocked(AppError):
    status_code = 429
    error_code = "ACCOUNT_LOCKED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify({"error": err.error_code}), err.status_code

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": "NOT_FOUND"}), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({"error": "NOT_FOUND"}), 405

    @app.errorhandler(400)
    def handle_400(_err):
        return jsonify({"error": "VALIDATION_ERROR"}), 400

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        code = err.code or 500
        mapping = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "NOT_FOUND",
            429: "ACCOUNT_LOCKED",
        }
        return jsonify({"error": mapping.get(code, "INTERNAL_ERROR")}), code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(_err: Exception):
        # Tuyệt đối không lộ stack trace ra ngoài
        return jsonify({"error": "INTERNAL_ERROR"}), 500
```

---

### 3.2. `app/audit.py` (Lớp 8: Audit Logging)
- Mỗi lần sửa điểm thành công và **mỗi lần trả 403 (`Forbidden`)** phải ghi 1 dòng JSON vào `AUDIT_LOG_PATH`.
- Các trường bắt buộc: `ts` (ISO-8601 UTC timestamp), `actorId`, `action`, `resource`, `result`, và kèm `oldScore`, `newScore` khi sửa điểm.
- Tuyệt đối không bao giờ ghi `password`, `password_hash`, hay `token`.

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIT_LOG_PATH: str = "audit.log"


def configure_audit(log_path: str) -> None:
    global _AUDIT_LOG_PATH
    _AUDIT_LOG_PATH = log_path


def write_audit_log(
    *,
    actor_id: str | None,
    action: str,
    resource: str,
    result: str,
    old_score: float | None = None,
    new_score: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actorId": actor_id or "anonymous",
        "action": action,
        "resource": resource,
        "result": result,
    }
    if old_score is not None:
        entry["oldScore"] = old_score
    if new_score is not None:
        entry["newScore"] = new_score
    if extra:
        # Đảm bảo không bao giờ lọt trường nhạy cảm
        for k, v in extra.items():
            if k.lower() not in {
                "password",
                "password_hash",
                "passwordhash",
                "token",
                "accesstoken",
            }:
                entry[k] = v

    path = Path(_AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    path = Path(_AUDIT_LOG_PATH)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
```

---

### 3.3. `app/store.py` (Quản lý State trong RAM & Băm Mật Khẩu Khi Nạp)
- Khi nạp `seed.json`, phải dùng `bcrypt` (cost >= 10) băm toàn bộ mật khẩu và **xóa hoàn toàn trường `password` bản rõ** khỏi bộ nhớ.
- Chuẩn hóa ID: nếu trong `seed.json` có `"1"` hoặc `"u1"`, `"5"` hoặc `"u5"`, hỗ trợ tra cứu tương thích cả hai nhưng chuẩn hóa ID chuẩn `"u1"`..`"u6"` hoặc giữ nguyên ID gốc đồng thời ánh xạ alias để không bao giờ lỗi.
- Để tăng tốc khi `create_app()` được gọi liên tục trong bài test mà vẫn đảm bảo băm `bcrypt` thật (cost >= 10), có thể băm với `bcrypt.gensalt(rounds=10)`.

```python
import copy
import json
from pathlib import Path
from typing import Any
import bcrypt


class InMemoryStore:
    def __init__(self) -> None:
        self.users_by_id: dict[str, dict[str, Any]] = {}
        self.users_by_email: dict[str, dict[str, Any]] = {}
        self.id_aliases: dict[str, str] = {}
        self.courses_by_id: dict[str, dict[str, Any]] = {}
        self.enrollments: list[dict[str, Any]] = []
        # State phục vụ Brute-force protection (Lớp 7)
        self.login_attempts: dict[str, dict[str, Any]] = {}
        # State phục vụ Reset Password token/OTP
        self.reset_requests: dict[str, str] = {}

    def load_seed(self, seed_path: str | Path = "seed.json") -> None:
        self.users_by_id.clear()
        self.users_by_email.clear()
        self.id_aliases.clear()
        self.courses_by_id.clear()
        self.enrollments.clear()
        self.login_attempts.clear()
        self.reset_requests.clear()

        raw = json.loads(Path(seed_path).read_text(encoding="utf-8"))

        # Tối ưu hóa việc băm nếu cùng 1 mật khẩu mặc định trong seed nhưng vẫn dùng bcrypt rounds=10 thật
        hash_cache: dict[str, str] = {}

        for u in raw.get("users", []):
            plain_pw = u.get("password", "")
            if plain_pw not in hash_cache:
                hash_cache[plain_pw] = bcrypt.hashpw(
                    plain_pw.encode("utf-8"), bcrypt.gensalt(rounds=10)
                ).decode("utf-8")

            uid = str(u["id"]).strip()
            email = str(u["email"]).strip().lower()
            role = str(u["role"]).strip().upper()
            if role == "TEACHER":
                role = "INSTRUCTOR"

            # Lưu bản ghi user tuyệt đối KHÔNG có trường 'password' rõ
            user_record = {
                "id": uid,
                "email": email,
                "password_hash": hash_cache[plain_pw],
                "role": role,
            }
            self.users_by_id[uid] = user_record
            self.users_by_email[email] = user_record

            # Hỗ trợ alias phòng trường hợp seed.json ghi "1" thay vì "u1" hoặc "5" thay vì "u5"
            if uid.isdigit():
                self.id_aliases[f"u{uid}"] = uid
                self.id_aliases[uid] = uid
            elif uid.startswith("u") and uid[1:].isdigit():
                self.id_aliases[uid[1:]] = uid
                self.id_aliases[uid] = uid

        for c in raw.get("courses", []):
            cid = str(c["id"]).strip()
            inst_id = self.resolve_user_id(str(c["instructorId"]).strip())
            self.courses_by_id[cid] = {
                "id": cid,
                "title": str(c["title"]),
                "instructorId": inst_id,
            }

        for e in raw.get("enrollments", []):
            cid = str(e["courseId"]).strip()
            sid = self.resolve_user_id(str(e["studentId"]).strip())
            score = float(e["score"])
            self.enrollments.append(
                {
                    "courseId": cid,
                    "studentId": sid,
                    "score": score,
                }
            )

    def resolve_user_id(self, user_id: str) -> str:
        if user_id in self.users_by_id:
            return user_id
        return self.id_aliases.get(user_id, user_id)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        resolved = self.resolve_user_id(user_id)
        return self.users_by_id.get(resolved)

    def get_public_actor(self, user_id: str) -> dict[str, str] | None:
        u = self.get_user_by_id(user_id)
        if not u:
            return None
        # Chỉ trả đúng 3 trường trong contract: id, email, role
        return {
            "id": u["id"],
            "email": u["email"],
            "role": u["role"],
        }

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        return self.users_by_email.get(email.strip().lower())


# Global store instance được reset mỗi lần gọi create_app()
store = InMemoryStore()
```

---

### 3.4. `app/auth.py` (Lớp 1: Xác thực JWT HS256 & Lớp 7: Chống Brute-force)
Các yêu cầu bắt buộc ở Lớp 1 và Lớp 7:
1. **Chống Enumeration & Timing Side-Channel (Kịch bản A1)**:
   - Khi email không tồn tại, vẫn phải chạy `bcrypt.checkpw` với một `_DUMMY_HASH` (băm sẵn lúc nạp module với cost=10) và trả về cùng mã lỗi `401 {"error": "INVALID_CREDENTIALS"}` giống hệt như khi sai mật khẩu!
2. **Chống Brute-force theo Email (Lớp 7 - Kịch bản A18)**:
   - Sai 5 lần liên tiếp cùng `email` -> khóa tài khoản 15 phút (`900` giây).
   - Khi đang trong thời gian bị khóa, mọi lần đăng nhập vào email đó (kể cả nhập **ĐÚNG** mật khẩu ở lần thứ 6) đều phải trả `429 {"error": "ACCOUNT_LOCKED"}`.
   - Nếu đăng nhập đúng **trước khi** chạm ngưỡng 5 lần (ví dụ sai 1–4 lần rồi nhập đúng) -> reset bộ đếm lỗi về `0`.
3. **JWT HS256 (Kịch bản A3, A4, A5)**:
   - Payload JWT **chỉ chứa đúng 3 claim**: `sub`, `iat`, `exp`. Không lưu `role` hay `email` trong JWT; mỗi request phải tra cứu lại từ `store`!
   - Khi giải mã (`jwt.decode`), bắt buộc truyền `algorithms=["HS256"]` và `options={"require": ["sub", "iat", "exp"]}` để chặn hoàn toàn tấn công `alg: none` (A4), sửa `sub` giữ chữ ký cũ (A3), hoặc hết hạn `TOKEN_TTL_SECONDS` (A5).

---

### 3.5. `app/gate.py` (Lớp 2: `before_request` Mặc Định Từ Chối)
```python
from flask import Flask, request, g
from app.errors import Unauthenticated
from app.auth import verify_access_token
from app.store import store

# Danh sách Allowlist tường minh theo (METHOD, PATH)
PUBLIC_ALLOWLIST: set[tuple[str, str]] = {
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/reset-password"),
    ("GET", "/"),
    ("GET", "/api/public/courses"),
}


def init_gate(app: Flask) -> None:
    @app.before_request
    def enforce_default_deny():
        path = request.path
        method = request.method.upper()

        # Cho phép static assets của giao diện web (nếu có)
        if method == "GET" and path.startswith("/static/"):
            return None

        # Nếu nằm trong allowlist công khai thì cho qua
        if (method, path) in PUBLIC_ALLOWLIST:
            return None

        # Mọi route khác (kể cả route mới thêm như GET /debug hay route không tồn tại)
        # đều BẮT BUỘC phải có Authorization: Bearer <token> hợp lệ
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise Unauthenticated()

        token = auth_header[len("Bearer ") :].strip()
        if not token:
            raise Unauthenticated()

        payload = verify_access_token(
            token=token,
            secret=app.config["JWT_SECRET"],
        )
        user_id = payload.get("sub")
        if not user_id or not isinstance(user_id, str):
            raise Unauthenticated()

        actor = store.get_public_actor(user_id)
        if not actor:
            # User trong token không còn tồn tại trong store
            raise Unauthenticated()

        g.current_actor = actor
        return None
```

---

### 3.6. `app/guards.py` (Lớp 3: Decorator `@require_role(*roles)`)
```python
from functools import wraps
from flask import g, request
from app.errors import Unauthenticated, Forbidden
from app.audit import write_audit_log


def require_role(*allowed_roles: str):
    normalized_roles = {r.upper() for r in allowed_roles}
    if "TEACHER" in normalized_roles:
        normalized_roles.add("INSTRUCTOR")
    if "INSTRUCTOR" in normalized_roles:
        normalized_roles.add("TEACHER")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor = getattr(g, "current_actor", None)
            if not actor:
                raise Unauthenticated()

            actor_role = str(actor.get("role", "")).upper()
            if actor_role not in normalized_roles:
                write_audit_log(
                    actor_id=actor.get("id"),
                    action=f"{request.method} {request.path}",
                    resource=request.path,
                    result="FORBIDDEN",
                )
                raise Forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator
```

---

### 3.7. `app/schemas.py` (Lớp 5: Kiểm tra Đầu Vào Nghiêm Ngặt)
**Cạm bẫy kinh điển của Python**: Trong Python, `isinstance(True, int)` trả về `True` vì `bool` kế thừa từ `int`! Do đó, kịch bản **A12** truyền `{"score": true}` sẽ lọt qua nếu chỉ dùng `isinstance(score, (int, float))`.
Bắt buộc phải kiểm tra `if isinstance(score, bool): raise ValidationError()` trước!

```python
from typing import Any
from app.errors import ValidationError


def validate_score_value(score: Any) -> float:
    # Từ chối boolean ("true"/"false" trong JSON) vì bool là subclass của int trong Python
    if isinstance(score, bool):
        raise ValidationError()
    # Từ chối string ("10") hoặc kiểu khác int/float
    if not isinstance(score, (int, float)):
        raise ValidationError()
    val = float(score)
    if val < 0.0 or val > 10.0:
        raise ValidationError()
    return val


def validate_put_grade_body(data: Any) -> float:
    if not isinstance(data, dict):
        raise ValidationError()
    # Chỉ cho phép duy nhất field 'score', từ chối mọi field thừa (VD: {"score": 9, "courseId": "c2"})
    if set(data.keys()) != {"score"}:
        raise ValidationError()
    return validate_score_value(data["score"])


def validate_login_body(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise ValidationError()
    if set(data.keys()) != {"email", "password"}:
        raise ValidationError()
    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise ValidationError()
    if not email.strip() or not password:
        raise ValidationError()
    return email.strip(), password
```

---

### 3.8. `app/services.py` (Lớp 4: Quyền trên Đối Tượng - Độc lập với Flask)
- **QUY TẮC SỐNG CÒN**: `app/services.py` **TUYỆT ĐỐI KHÔNG** `import flask`.
- Hàm bắt buộc:
  1. `get_grades(actor: dict, course_id: str) -> list[dict]`
  2. `update_grade(actor: dict, course_id: str, student_id: str, score: float) -> dict`
- Ma trận quyền bắt buộc trong `services.py`:
  - Kiểm tra `actor` hợp lệ (phải là `dict` có `id`, `role`).
  - Kiểm tra `course_id` có tồn tại trong `store.courses_by_id` không -> nếu không, ném `NotFound()`.
  - Với `get_grades(actor, course_id)`:
    - `ADMIN`: Trả về toàn bộ `[{"studentId": ..., "score": ...}]` của môn `course_id`.
    - `INSTRUCTOR`: Nếu `course["instructorId"] == actor_id` -> trả về toàn bộ điểm của môn đó. Nếu là GV dạy môn khác -> ghi audit log `FORBIDDEN` và ném `Forbidden()`.
    - `STUDENT`: Kiểm tra sinh viên có ghi danh vào `course_id` không. Nếu có -> chỉ trả về đúng 1 phần tử `[{"studentId": actor_id, "score": ...}]` của chính sinh viên đó (Kịch bản A7). Nếu không ghi danh (Kịch bản A8: Chi GET điểm c2) -> ghi audit log `FORBIDDEN` và ném `Forbidden()`.
    - `GUEST` hoặc role khác: ghi audit log `FORBIDDEN` và ném `Forbidden()`.
  - Với `update_grade(actor, course_id, student_id, score)`:
    1. Kiểm tra `course_id` có trong `store` không -> nếu không ném `NotFound()`.
    2. Kiểm tra quyền đối tượng: Chỉ `INSTRUCTOR` có `course["instructorId"] == actor_id` mới được phép. Mọi trường hợp khác (`ADMIN`, `STUDENT`, `GUEST`, hoặc `INSTRUCTOR` khác như Bình sửa môn c1 ở A10) -> ghi audit log `FORBIDDEN` (nếu chưa được ghi ở Lớp 3) và ném `Forbidden()`! (Đảm bảo Kịch bản A15: gỡ `@require_role` hoặc gọi hàm `update_grade(chi, "c1", "u4", 10)` trực tiếp vẫn ném `Forbidden`).
    3. Kiểm tra lại miền giá trị `score` bằng `validate_score_value(score)` (Lớp 5 quy định: *"Service kiểm tra lại miền giá trị"*).
    4. Tìm bản ghi ghi danh `(course_id, resolved_student_id)` trong `store.enrollments`. Nếu sinh viên không ghi danh trong môn này (Kịch bản A13: An PUT c1/u6) -> ném `NotFound()`.
    5. Cập nhật điểm mới, ghi Audit Log với `oldScore` và `newScore` (Kịch bản A19), và trả về `{"courseId": course_id, "studentId": enrollment["studentId"], "score": validated_score}`.
