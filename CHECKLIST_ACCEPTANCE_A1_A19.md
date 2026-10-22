# 📋 CHECKLIST NGHIỆM THU DỰ ÁN TRƯỚC KHI PUSH CI & CHẤM TRỰC TIẾP

Antigravity phải kiểm tra từng mục trong bảng dưới đây trước khi kết thúc nhiệm vụ:

## 1. Kiểm tra Cấu trúc & File Bắt Buộc
- [ ] `app/__init__.py` có `create_app(config=None)` nạp lại `seed.json` và tạo state mới mỗi lần gọi.
- [ ] `app/store.py` băm mật khẩu ngay khi nạp `seed.json`, xóa hoàn toàn mật khẩu bản rõ khỏi RAM.
- [ ] `app/auth.py` dùng `bcrypt` (cost >= 10) hoặc `argon2`, JWT HS256 chỉ chứa `sub`, `iat`, `exp`, truyền `algorithms=["HS256"]` khi decode.
- [ ] `app/gate.py` cài đặt `before_request` toàn cục theo nguyên tắc Default Deny.
- [ ] `app/guards.py` cài đặt decorator `@require_role(*roles)`.
- [ ] `app/services.py` **KHÔNG** `import flask`, tự kiểm tra quyền trên đối tượng và miền giá trị, tự ném `Forbidden`, `NotFound`, `ValidationError` từ `app.errors`.
- [ ] `app/schemas.py` từ chối `"10"`, `True`/`False` (boolean), ngoài `[0, 10]`, và từ chối mọi field thừa.
- [ ] `app/errors.py` trả JSON `{"error": "<MÃ>"}` cho mọi lỗi (kể cả 404/405 mặc định của Flask), không lộ stack trace.
- [ ] `app/audit.py` ghi JSON Lines cho mỗi lần sửa điểm và mỗi lần 403 (`ts`, `actorId`, `action`, `resource`, `result`, kèm điểm cũ/mới).
- [ ] Có đầy đủ `seed.json`, `requirements.txt`, `.env.example`, và **không commit secret thật**.

## 2. Kiểm tra 19 Kịch bản Chấm Điểm (A1 -> A19)
- [ ] **A1**: Login email không tồn tại và sai mật khẩu trả `401 {"error": "INVALID_CREDENTIALS"}` giống hệt nhau.
- [ ] **A2**: `GET /me` không token trả `401`.
- [ ] **A3**: Token của Chi sửa `sub` thành `u1` giữ chữ ký cũ trả `401`.
- [ ] **A4**: Token có header `alg: none` trả `401`.
- [ ] **A5**: `TOKEN_TTL_SECONDS=1`, chờ 2 giây, gọi `/me` trả `401`.
- [ ] **A6**: Mọi response không chứa `password`, `password_hash`, `passwordHash`.
- [ ] **A7**: Chi `GET /courses/c1/grades` trả `200 [{"studentId": "u4", "score": 7.5}]`.
- [ ] **A8**: Chi `GET /courses/c2/grades` trả `403`.
- [ ] **A9**: Chi `PUT /courses/c1/grades/u4 {"score": 10}` trả `403`.
- [ ] **A10**: Bình `PUT /courses/c1/grades/u4 {"score": 0}` trả `403`.
- [ ] **A11**: Admin `PUT /courses/c1/grades/u4 {"score": 10}` trả `403`.
- [ ] **A12**: An `PUT c1/u4` với `score` là `11`, `-1`, `"10"`, `true`, và `{"score": 9, "courseId": "c2"}` đều trả `400`.
- [ ] **A13**: An `PUT /courses/c1/grades/u6 {"score": 5}` trả `404`.
- [ ] **A14**: An `PUT c1/u4 {"score": 9}`, sau đó Chi `GET c1` thấy `9`.
- [ ] **A15**: Gỡ `@require_role` khỏi route `PUT`, chạy lại A9–A11 vẫn `403`; gọi trực tiếp `update_grade(chi, "c1", "u4", 10)` ném `Forbidden`.
- [ ] **A16**: Thêm `GET /debug` không khai báo gì, gọi không token trả `401`.
- [ ] **A17**: `create_app()` khi thiếu `JWT_SECRET` (hoặc `< 32` ký tự) ném `RuntimeError`.
- [ ] **A18**: Sai mật khẩu Dũng 5 lần, lần 6 nhập đúng vẫn trả `429`.
- [ ] **A19**: Sau A10 và A14, đọc `AUDIT_LOG_PATH` có 2 dòng tương ứng, không chứa mật khẩu hay token.

## 3. Kiểm tra Tính năng Web App LMS Mở Rộng (4 Roles & Home Page)
- [ ] Hỗ trợ đầy đủ 4 Roles: **Admin**, **Teacher (`INSTRUCTOR`)**, **Student**, **Guest**.
- [ ] Có đầy đủ luồng **Đăng nhập**, **Đăng ký**, **Reset Password** hoạt động mượt mà.
- [ ] Trang chủ (`GET /`) hiện đại, có **1-Click Role Switcher** để demo nhanh và bảng **Live Security Inspector**.
