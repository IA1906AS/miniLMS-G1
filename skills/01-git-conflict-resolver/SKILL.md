---
name: git-conflict-resolver-uv
description: Kỹ năng xử lý Git Merge Conflict cho dự án Flask LMS sử dụng uv, bảo toàn cả logic chấm điểm Defense-in-Depth và giao diện Web App mở rộng.
---

# 🛠️ SKILL 01: XỬ LÝ GIT CONFLICT & ĐỒNG BỘ MÔI TRƯỜNG `uv`

## 1. Mục tiêu
Khi nhiều thành viên trong nhóm cùng chỉnh sửa các file lõi (`app/__init__.py`, `app/auth.py`, `app/gate.py`, `app/services.py`, `seed.json`, `pyproject.toml`, `requirements.txt`), xung đột (conflict) thường xảy ra giữa:
- Nhánh làm **Core Security (8 lớp bảo vệ theo PDF đề bài)**.
- Nhánh làm **Web App UI + Đăng ký / Reset Password + 4 Roles**.

Antigravity cần thực hiện quy trình dưới đây để giải quyết triệt để conflict mà không làm hỏng bất kỳ kịch bản chấm điểm nào (A1–A19).

---

## 2. Quy trình rà soát Conflict tự động

### Bước 1: Kiểm tra trạng thái Git và tìm toàn bộ Conflict Markers
Chạy các lệnh sau trong terminal:
```bash
git status
git diff --name-only --diff-filter=U
grep -rn "<<<<<<<" .
```

### Bước 2: Nguyên tắc vàng khi phân giải Conflict (Conflict Resolution Rules)

1. **Trong `seed.json`**:
   - Giữ nguyên cấu trúc dữ liệu gốc gồm `users`, `courses`, `enrollments`.
   - **LƯU Ý QUAN TRỌNG VỀ ID TRONG `seed.json`**:
     - Kiểm tra kỹ ID của Admin và Dũng: Trong kịch bản kiểm tra A3 có nhắc tới `u1` và trong `enrollments` nhắc tới `u5`, nhưng một số bản copy từ PDF bị OCR nhầm `"u1"` thành `"1"` và `"u5"` thành `"5"`.
     - Giải pháp an toàn tuyệt đối trong `app/store.py`: Giữ `seed.json` chuẩn (`u1`..`u6`), đồng thời trong hàm `get_user_by_id(user_id)` của `store.py`, hỗ trợ ánh xạ dự phòng (nếu tìm `"u1"` hoặc `"1"` đều khớp Admin, `"u5"` hoặc `"5"` đều khớp `dung.sv@lms.test`) để dù giảng viên dùng file `seed.json` nào cũng pass 100%!

2. **Trong `app/services.py`**:
   - **TUYỆT ĐỐI KHÔNG** `import flask` (không dùng `request`, `g`, `current_app`, `abort` của Flask trong `services.py`).
   - Nếu có nhánh nào của thành viên khác lỡ `import flask` trong `services.py`, phải gỡ bỏ ngay và chuyển sang nhận `actor` (`{"id", "email", "role"}`) + `store` (hoặc truy cập module-level state được khởi tạo lại ở `create_app`), tự ném `Forbidden`, `NotFound`, `ValidationError` từ `app.errors`.

3. **Trong `app/gate.py`**:
   - Nếu một nhánh chặn toàn bộ trừ `POST /auth/login`, còn nhánh kia mở toang `before_request` cho Web UI:
   - **Cách gộp chuẩn**: Giữ cơ chế **Default Deny** (mặc định từ chối mọi route chưa xác thực), chỉ mở một danh sách `PUBLIC_ALLOWLIST` tường minh theo cặp `(method, path)` cho:
     - `("POST", "/auth/login")`
     - `("POST", "/auth/register")`
     - `("POST", "/auth/reset-password")`
     - `("GET", "/")` (Trang chủ LMS hiện đại)
     - `("GET", "/api/public/courses")` (API danh sách khóa học công khai cho Guest)
     - Các file tĩnh `/static/...`
   - Nhờ đó, khi giảng viên thêm route bất kỳ như `GET /debug` (Kịch bản A16), nó không nằm trong `PUBLIC_ALLOWLIST` nên `gate.py` lập tức chặn lại và trả `401 {"error": "UNAUTHENTICATED"}`!

4. **Trong `app/__init__.py`**:
   - Hàm `create_app(config=None)` phải:
     1. Đọc biến môi trường và ghi đè bằng dict `config` truyền vào (nếu có).
     2. Kiểm tra `JWT_SECRET`: Nếu không có, không phải chuỗi, hoặc `len(JWT_SECRET) < 32` -> lập tức `raise RuntimeError("JWT_SECRET must be at least 32 characters")` (Kịch bản A17).
     3. Nạp lại `seed.json` và tạo state bộ nhớ mới hoàn toàn ở **mỗi lần gọi `create_app()`**.

---

## 3. Chuẩn hóa quản lý gói bằng `uv` và tương thích `pip`

Dự án phát triển bằng `uv` nhưng khi chấm bài giảng viên có thể chạy `pip install -r requirements.txt && flask --app app run`. Do đó Antigravity phải cấu hình song song:

### Cấu hình `pyproject.toml` chuẩn (Không chứa thư viện bị cấm):
```toml
[project]
name = "lms-defense-in-depth"
version = "0.1.0"
description = "Defense in Depth AuthN/AuthZ LMS Web Application (Flask 3.x)"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0.0",
    "bcrypt>=4.1.0",
    "pyjwt>=2.8.0",
    "pydantic>=2.6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]
```

### Lệnh đồng bộ `uv` và xuất `requirements.txt`:
```bash
# Cài đặt và đồng bộ môi trường ảo bằng uv
uv sync

# Xuất ra requirements.txt chuẩn (không chứa các thư viện bị cấm)
uv pip compile pyproject.toml -o requirements.txt
```

### Kiểm tra danh sách thư viện bị cấm (Forbidden Packages Check):
Chạy lệnh kiểm tra để chắc chắn không thành viên nào cài nhầm:
```bash
grep -iE "flask-login|flask-jwt-extended|flask-security|flask-httpauth|authlib" pyproject.toml requirements.txt
```
*(Kết quả phải trống! Nếu có bất kỳ thư viện nào trong danh sách cấm trên, phải xóa ngay lập tức).*
