# 🚀 MASTER ORCHESTRATION PROMPT FOR ANTIGRAVITY
**Role**: Senior Python Developer & Security Architect (chuyên gia `uv`, Flask 3.x, Defense-in-Depth)  
**Target**: Giải quyết triệt để Git Merge Conflict, đảm bảo pass 100% kịch bản chấm điểm **A1 -> A19** trong đề bài **Defense in Depth cho AuthN/AuthZ - LMS (Flask)**, đồng thời mở rộng thành **Web App LMS hoàn chỉnh 4 Roles (Admin, Teacher/Instructor, Student, Guest)** với tính năng **Đăng nhập, Đăng ký, Reset Password** và **Modern Executive Home Page**.

---

## 📌 CÁCH SỬ DỤNG BỘ SKILL NÀY VỚI ANTIGRAVITY

1. Giải nén toàn bộ thư mục này vào gốc dự án (hoặc thư mục `.agent/skills/` của workspace).
2. Gửi câu lệnh sau vào khung chat của **Antigravity**:
   > *"Hãy đọc file `@00_MASTER_PROMPT_FOR_ANTIGRAVITY.md` và nạp lần lượt các file skill từ `01` đến `05` trong thư mục `skills/`. Thực hiện tuần tự từng Phase: (1) Xử lý Git conflict & đồng bộ môi trường `uv`, (2) Chuẩn hóa lõi 8 lớp bảo vệ Defense-in-Depth theo đúng cấu trúc bắt buộc, (3) Mở rộng 4 roles + Đăng ký + Reset Password, (4) Xây dựng giao diện Home Page & LMS Portal hiện đại, (5) Chạy bộ test tự động A1-A19 bằng `uv run pytest` và xuất `requirements.txt`."*

---

## 🗺️ LỘ TRÌNH THỰC THI (EXECUTION PIPELINE CHO ANTIGRAVITY)

### Phase 1: Nạp `skills/01-git-conflict-resolver/SKILL.md`
- Quét toàn bộ conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
- Ưu tiên giữ nguyên **Contract API & Cấu trúc 9 file bắt buộc** trong `app/` cho phần chấm điểm tự động, đồng thời hợp nhất phần UI/Frontend và các route mở rộng một cách an toàn.
- Đồng bộ hóa `pyproject.toml`, `uv.lock` và xuất `requirements.txt` chuẩn xác.

### Phase 2: Nạp `skills/02-defense-in-depth-core/SKILL.md`
- Kiểm tra và hoàn thiện **8 Lớp Bảo Vệ Độc Lập (Defense in Depth)**:
  - **Lớp 1 (`app/auth.py`)**: Băm mật khẩu (`bcrypt` cost >= 10 hoặc `argon2`), ký/xác minh JWT HS256 (`sub`, `iat`, `exp`), chống timing/enumeration khi login.
  - **Lớp 2 (`app/gate.py`)**: `before_request` toàn cục theo cơ chế **Default Deny** (Mặc định từ chối). Mọi route không nằm trong `PUBLIC_ALLOWLIST` đều bắt buộc phải có Bearer Token hợp lệ (đảm bảo khi giảng viên thêm `GET /debug` không khai báo gì sẽ bị chặn với `401 UNAUTHENTICATED`).
  - **Lớp 3 (`app/guards.py`)**: Decorator `@require_role(*roles)` kiểm tra vai trò cấp độ route.
  - **Lớp 4 (`app/services.py`)**: Kiểm tra quyền cấp độ đối tượng (Object-level Authorization) độc lập hoàn toàn với Flask (` không import flask`), đảm bảo khi giảng viên gỡ `@require_role` ở route `PUT` thì `services.py` vẫn ném `Forbidden` (403).
  - **Lớp 5 (`app/schemas.py`)**: Validate chặt chẽ dữ liệu đầu vào (từ chối `"10"`, `true`/`false` boolean núp bóng `int` trong Python, số ngoài `[0, 10]`, và từ chối mọi field thừa).
  - **Lớp 6 (`app/errors.py`)**: Fail-closed khi thiếu `JWT_SECRET` (hoặc `< 32` ký tự) bằng `RuntimeError`. Chuẩn hóa mọi phản hồi lỗi về `{"error": "<MÃ>"}`, bao gồm cả 404/405 mặc định của Flask, tuyệt đối không lộ stack trace hay `password`/`password_hash`.
  - **Lớp 7 (`app/auth.py`)**: Chống Brute-force (sai 5 lần liên tiếp cùng email -> khóa 15 phút, trả `429 ACCOUNT_LOCKED` kể cả lần thứ 6 nhập đúng).
  - **Lớp 8 (`app/audit.py`)**: Ghi Audit Log định dạng JSON Lines (`ts`, `actorId`, `action`, `resource`, `result`, kèm `oldScore`/`newScore` khi sửa điểm, không bao giờ ghi password/token).

### Phase 3: Nạp `skills/03-lms-4roles-auth-extension/SKILL.md`
- Mở rộng mô hình 4 Roles:
  1. **Admin (`ADMIN`)**: Xem toàn bộ điểm các môn, quản lý danh sách khóa học, xem nhật ký bảo mật (Audit Logs) trên giao diện, không được phép sửa điểm sinh viên (`403 FORBIDDEN` theo đúng ma trận quyền).
  2. **Teacher (`INSTRUCTOR` / hiển thị UI là `Teacher`)**: Xem và cập nhật điểm của sinh viên đã ghi danh vào môn mình phụ trách.
  3. **Student (`STUDENT`)**: Xem điểm của chính mình ở các môn đã ghi danh, đăng ký xem khóa học.
  4. **Guest (`GUEST`)**: Khám phá trang chủ, xem danh mục khóa học công khai, trải nghiệm bản xem trước (Preview) mà không được phép truy cập dữ liệu điểm nội bộ.
- Bổ sung các tính năng:
  - **Đăng nhập** (`POST /auth/login`)
  - **Đăng ký tài khoản mới** (`POST /auth/register`)
  - **Khôi phục mật khẩu / Reset Password** (`POST /auth/reset-password`)

### Phase 4: Nạp `skills/04-modern-lms-homepage-ui/SKILL.md`
- Thiết kế **Modern Executive LMS Home Page & Web App Portal** phục vụ tiêu chuẩn đánh giá của các PM/Sếp quản lý dự án web:
  - Giao diện hiện đại (Bento Grid, Glassmorphism, Dark/Light Theme, Micro-interactions mượt mà).
  - Tích hợp **Interactive Role Workspace** cho cả 4 Role (Guest, Student, Teacher, Admin) ngay trên Web App.
  - Tích hợp **Live Security & Defense-in-Depth Inspector** giúp biểu diễn trực quan 8 lớp bảo vệ khi thuyết trình với giảng viên và quản lý dự án.

### Phase 5: Nạp `skills/05-uv-and-automated-verification/SKILL.md`
- Tạo và chạy bộ kiểm thử tự động `tests/test_defense_in_depth.py` bao phủ toàn bộ **A1 -> A19** và các tính năng mới.
- Xuất `requirements.txt` và `.env.example` sẵn sàng nộp bài.
