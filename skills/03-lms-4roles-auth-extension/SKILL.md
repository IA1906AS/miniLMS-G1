---
name: lms-4roles-auth-extension
description: Mở rộng hệ thống LMS hỗ trợ 4 Roles (Admin, Teacher/Instructor, Student, Guest) cùng luồng Đăng nhập, Đăng ký, Reset Password và Quản lý khóa học.
---

# 👥 SKILL 03: MỞ RỘNG LMS 4 ROLES + ĐĂNG KÝ + RESET PASSWORD

## 1. Mô hình 4 Roles Chuẩn Hóa

Để vừa tương thích 100% với bộ test chấm điểm tự động của giảng viên (`ADMIN`, `INSTRUCTOR`, `STUDENT`), vừa đáp ứng yêu cầu mở rộng thành Web App LMS 4 Roles (`Admin`, `Teacher`, `Student`, `Guest`):

| Role trên Giao diện (UI) | Mã Role chuẩn trong Backend (`role`) | Quyền hạn trong hệ thống LMS |
| :--- | :--- | :--- |
| **Admin** | `ADMIN` | Xem điểm toàn bộ các môn học (`GET /courses/<id>/grades`), xem bảng thống kê hệ thống & nhật ký bảo mật (`GET /api/admin/audit-logs`), quản lý danh sách người dùng. **Không được sửa điểm SV (`403 FORBIDDEN`)**. |
| **Teacher (Instructor)** | `INSTRUCTOR` *(chấp nhận alias `TEACHER` khi đăng ký và tự chuẩn hóa về `INSTRUCTOR`)* | Xem toàn bộ bảng điểm của môn mình giảng dạy, cập nhật điểm số (`PUT /courses/<id>/grades/<student_id>`) cho sinh viên đã ghi danh vào môn đó. |
| **Student** | `STUDENT` | Xem điểm của chính mình ở các môn đã ghi danh (`GET /courses/<id>/grades`), ghi danh môn học mới (`POST /courses/<id>/enroll`). |
| **Guest** | `GUEST` | Truy cập trang chủ hiện đại, xem danh mục khóa học công khai (`GET /api/public/courses`), đăng ký tài khoản hoặc đăng nhập với vai trò `GUEST`. Bị chặn (`403 FORBIDDEN`) nếu cố truy cập bảng điểm nội bộ. |

---

## 2. Đặc tả các Endpoint Mở Rộng (Không ảnh hưởng 4 Endpoint Lõi)

### 2.1. 4 Endpoint Lõi Bắt Buộc (Giữ nguyên 100% Contract theo Đề bài)
1. `POST /auth/login`
   - Input: `{"email": "...", "password": "..."}`
   - Output `200`: `{"accessToken": "<jwt>", "expiresIn": 900}`
2. `GET /me`
   - Output `200`: `{"id": "...", "email": "...", "role": "..."}`
3. `GET /courses/<course_id>/grades`
   - Output `200`: `[{"studentId": "...", "score": 7.5}, ...]`
4. `PUT /courses/<course_id>/grades/<student_id>`
   - Input: `{"score": 9.0}`
   - Output `200`: `{"courseId": "c1", "studentId": "u4", "score": 9.0}`

---

### 2.2. Các Endpoint Mở Rộng Phục Vụ Web App LMS

#### A. Đăng ký tài khoản (`POST /auth/register`)
- **Allowlist trong `gate.py`**: Có `("POST", "/auth/register")`.
- **Body**:
  ```json
  {
    "email": "new.student@lms.test",
    "password": "StrongPassword@2026",
    "role": "STUDENT"
  }
  ```
  *(Chấp nhận `role` là `"STUDENT"`, `"TEACHER"` / `"INSTRUCTOR"`, hoặc `"GUEST"`. Mặc định là `"STUDENT"`. Không cho phép tự đăng ký `"ADMIN"` công khai để đảm bảo an toàn bảo mật — nếu truyền `"ADMIN"` sẽ trả `403 {"error": "FORBIDDEN"}` hoặc `400 {"error": "VALIDATION_ERROR"}`).*
- **Xử lý**:
  - Kiểm tra định dạng email, độ dài mật khẩu (`>= 6` ký tự), và không có field thừa.
  - Nếu email đã tồn tại trong `store.users_by_email` -> trả `400 {"error": "VALIDATION_ERROR"}`.
  - Băm mật khẩu bằng `bcrypt` (cost >= 10), tạo ID mới (ví dụ `u7`, `u8`...), lưu vào `store` (không lưu mật khẩu bản rõ).
  - Trả về `201`:
    ```json
    {
      "id": "u7",
      "email": "new.student@lms.test",
      "role": "STUDENT"
    }
    ```

#### B. Đặt lại mật khẩu (`POST /auth/reset-password`)
- **Allowlist trong `gate.py`**: Có `("POST", "/auth/reset-password")`.
- **Body**:
  ```json
  {
    "email": "chi.sv@lms.test",
    "newPassword": "NewPassword@2026"
  }
  ```
- **Xử lý**:
  - Validate body chặt chẽ (`email`, `newPassword` >= 6 ký tự).
  - Kiểm tra nếu tài khoản đang bị khóa Brute-force (`429 ACCOUNT_LOCKED`) thì từ chối với `429`.
  - Cập nhật `password_hash` mới bằng `bcrypt` (cost >= 10) trong `store`, đồng thời ghi một dòng vào Audit Log (`action="RESET_PASSWORD"`, không ghi mật khẩu).
  - Trả về `200`: `{"status": "PASSWORD_UPDATED"}`.

#### C. Danh sách khóa học công khai cho Guest & Home Page (`GET /api/public/courses`)
- **Allowlist trong `gate.py`**: Có `("GET", "/api/public/courses")`.
- **Output `200`**:
  Trả về danh sách môn học kèm tên/ID giảng viên và số lượng sinh viên đã ghi danh (tuyệt đối không lộ điểm số hay thông tin nhạy cảm):
  ```json
  [
    {
      "id": "c1",
      "title": "Lập trình Web",
      "instructorId": "u2",
      "instructorEmail": "an.gv@lms.test",
      "enrolledCount": 2
    },
    {
      "id": "c2",
      "title": "Cơ sở dữ liệu",
      "instructorId": "u3",
      "instructorEmail": "binh.gv@lms.test",
      "enrolledCount": 2
    }
  ]
  ```

#### D. Xem Audit Log dành riêng cho Admin (`GET /api/admin/audit-logs`)
- **Bảo vệ**: Đi qua `gate.py` (Lớp 2) + `@require_role("ADMIN")` (Lớp 3).
- **Output `200`**: Danh sách các bản ghi Audit Log mới nhất để hiển thị trực quan trên Admin Security Dashboard.
