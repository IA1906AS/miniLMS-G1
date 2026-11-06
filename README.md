# EduShield miniLMS — Secure Learning Management System

> **Dự án Môn học:** Phát triển & Kiểm thử Ứng dụng An toàn (IAW301) — Nhóm 1  
> **Kiến trúc:** Clean Architecture & 7-Layer Defense-in-Depth  
> **Công nghệ cốt lõi:** Python 3.14+, Flask 3.1, SQLAlchemy 2.0, PostgreSQL 16, TailwindCSS, Alpine.js

---

## 1. Giới Thiệu Tổng Quan

**EduShield miniLMS** là hệ thống quản lý học tập (LMS) thế hệ mới được thiết kế theo tiêu chuẩn an ninh phần mềm của OWASP. Dự án kết hợp hài hòa giữa các chức năng quản trị đào tạo thực tế với mô hình phòng thủ đa tầng (**Defense-in-Depth**) và các mẫu thiết kế hệ thống phân tán chịu lỗi cao.

Hệ thống được tổ chức hoàn chỉnh như một ứng dụng web thống nhất, loại bỏ hoàn toàn các giao diện thử nghiệm mẫu đơn lẻ, cho phép kiểm thử bảo mật tự nhiên thông qua các công cụ chuyên dụng như **Burp Suite**, **SQLMap**, hoặc các kịch bản kiểm thử API tự động.

---

## 2. Mô Hình An Ninh Defense-in-Depth 7 Lớp

| Tầng Phòng Thủ | Module Đảm Nhiệm | Trách Nhiệm An Toàn |
|:---|:---|:---|
| **Layer 1: Input Validation** | `schemas.py` | Kiểm tra nghiêm ngặt kiểu dữ liệu, giới hạn độ dài, định dạng email/mật khẩu, chặn payload rác ngay tại cửa vào. |
| **Layer 2: Deny-by-Default Gatekeeper** | `gate.py` | Chặn toàn bộ các request không có JWT Bearer Token hợp lệ (thuật toán bắt buộc `HS256`, kiểm tra hạn dùng `exp`), ngoại trừ các public endpoint được allowlist. |
| **Layer 3: Route-Level RBAC** | `guards.py` | Phân quyền vai trò người dùng (`ADMIN`, `INSTRUCTOR`, `STUDENT`) thông qua decorator `@require_roles`. |
| **Layer 4: Domain Service Authorization** | `services.py` | Kiểm soát quyền sở hữu tài nguyên (IDOR/BOLA): chỉ giảng viên phụ trách môn học mới được cập nhật điểm; sinh viên chỉ được xem điểm của chính mình. |
| **Layer 5: Storage & Transaction Integrity** | `database.py`, `models.py` | Sử dụng ORM SQLAlchemy với câu lệnh tham số hóa chống triệt để SQL Injection; giao dịch ACID và phân cách dữ liệu. |
| **Layer 6: Standard Error Handling** | `errors.py` | Chuẩn hóa thông điệp lỗi theo RFC 7807, giấu kín stacktrace kỹ thuật và thông tin hệ thống nhạy cảm. |
| **Layer 7: Brute-Force & Audit Trail** | `auth.py`, `audit.py` | Chống tấn công dò mật khẩu (khóa tài khoản 15 phút sau 5 lần sai liên tiếp, thời gian phản hồi hằng số chống timing attack), lưu vết kiểm toán an toàn không rò rỉ secret. |

---

## 3. Các Phân Hệ Nghiệp Vụ & Cơ Chế Chịu Lỗi Hệ Thống

Toàn bộ các cơ chế phòng thủ nâng cao được tích hợp trực tiếp vào domain nghiệp vụ LMS:
- **Kiểm Tra Đạo Văn (Circuit Breaker):** `plagiarism.py` — Tự động ngắt kết nối (Trip to Open) và phản hồi nhanh khi dịch vụ kiểm tra đạo văn bên ngoài gặp sự cố, tránh nghẽn thread máy chủ.
- **Bảng Thống Kê Điểm Số (Timeout & Fallback):** `dashboard.py` — Áp dụng giới hạn thời gian (deadline) cho các truy vấn tổng hợp nặng; tự động chuyển sang dữ liệu bộ đệm (cache fallback) khi dịch vụ thống kê quá tải.
- **Khảo Thí Trắc Nghiệm (State Machine Lifecycle):** `quizzes.py` — Quản lý vòng đời bài thi chặt chẽ (`CREATED` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `SUBMITTED`/`EXPIRED`), ngăn chặn hoàn toàn việc sửa đáp án sau nộp hoặc nộp đúp.
- **Ghi Danh & Thông Báo (Transactional Outbox):** `outbox.py` — Đảm bảo việc sinh viên ghi danh và phát sinh sự kiện thông báo luôn diễn ra nguyên khối trong cùng một giao dịch database, có cơ chế retry tự động với backoff.
- **Xuất Báo Cáo Điểm (Bulkhead Concurrency):** `reports.py` — Cách ly số lượng luồng xử lý xuất báo cáo nặng (giới hạn semaphore), bảo đảm các endpoint trọng yếu như đăng nhập, xem điểm luôn phản hồi tức thì.
- **Giữ Chỗ Đăng Ký Lớp Học (Two-Phase Reservation):** `reservations.py` — Giữ chỗ có thời hạn (`HELD`), kiểm soát sĩ số phòng máy/lớp học nghiêm ngặt và tự động thu hồi chỗ khi hết hạn giữ.
- **Xử Lý Chống Trùng Lặp (Idempotency Key):** `services.py` — Ngăn chặn trùng lặp nộp bài tập hoặc xử lý thanh toán/ghi danh khi người dùng bấm nút nhiều lần hoặc có mạng chập chờn.

---

## 4. Cài Đặt & Khởi Chạy

### Yêu cầu tiên quyết
- Python 3.13 hoặc 3.14 (Khuyến nghị 64-bit)
- PostgreSQL 16 (Tùy chọn cho môi trường sản xuất; hệ thống tự động fallback về in-memory store khi chạy test local)

### Các bước cài đặt:
1. **Clone repository và truy cập thư mục:**
   ```bash
   git clone <repo-url>
   cd IAW301-Project_Group_1
   ```

2. **Khởi tạo và kích hoạt môi trường ảo:**
   ```powershell
   # Windows PowerShell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Cài đặt các gói phụ thuộc:**
   ```powershell
   pip install -e ".[dev]"
   ```

4. **Khởi tạo Cơ sở dữ liệu PostgreSQL (Tùy chọn):**
   ```powershell
   # Chạy script khởi tạo schema và seed data:
   psql -U postgres -d minidb -f database/init.sql
   ```

5. **Khởi chạy ứng dụng:**
   ```powershell
   python run.py
   # Ứng dụng khởi động tại: http://127.0.0.1:5000
   ```

---

## 5. Tài Khoản Thử Nghiệm

Mật khẩu mặc định cho tất cả tài khoản là: **`Lms@2026`**

| Email | Vai Trò (Role) | Chức Danh / Họ Tên | Mục Đích Kiểm Thử |
|:---|:---|:---|:---|
| `admin@lms.test` | `ADMIN` | Quản Trị Viên Hệ Thống | Kiểm tra quản lý người dùng, nhật ký kiểm toán (Audit Log) |
| `an.gv@lms.test` | `INSTRUCTOR` | ThS. Nguyễn Văn An | Giảng viên môn Lập trình Web & An toàn Web; chấm điểm, tạo bài |
| `binh.gv@lms.test`| `INSTRUCTOR` | TS. Trần Thị Bình | Giảng viên môn Cơ sở dữ liệu; kiểm tra phân quyền liên môn học |
| `chi.sv@lms.test` | `STUDENT` | Lê Linh Chi | Sinh viên môn Web; kiểm tra xem điểm, nộp bài, thi trắc nghiệm |
| `dung.sv@lms.test`| `STUDENT` | Phạm Quốc Dũng | Sinh viên môn An toàn Web & CSDL; kiểm tra giữ chỗ phòng máy |
| `em.sv@lms.test`  | `STUDENT` | Hoàng Thị Ánh Em | Sinh viên môn CSDL; kiểm tra chống truy cập IDOR |

---

## 6. Kiểm Thử Hệ Thống (Testing & Verification)

### Chạy Static Analysis (Linter):
```powershell
.\.venv\Scripts\ruff.exe check src tests
```

### Chạy Bộ Kiểm Thử Tự Động (120 Tests):
```powershell
.\.venv\Scripts\pytest.exe -v
```

### Ma trận kiểm thử an ninh chuyên sâu:
- **`tests/test_defense_in_depth.py`**: Kiểm thử toàn diện 19 ca bảo mật **A1 đến A19**.
- **`tests/test_auth_and_rbac.py`**: Kiểm thử phân quyền truy cập và xác thực tài khoản.
- **`tests/test_idempotency_key.py`**: Kiểm thử chống gửi lặp bài tập và xử lý xung đột đồng thời.
- **`tests/test_pattern_*.py`**: Kiểm thử các mẫu thiết kế chịu lỗi (Circuit Breaker, Timeout, State Machine, Outbox, Bulkhead, Reservation).

---

## 7. Giấy Phép & Tác Quyền

Dự án được xây dựng phục vụ nghiên cứu và học tập môn học **IAW301 - An Toàn Ứng Dụng Web**. Mọi hành vi kiểm thử tải hoặc quét lỗ hổng chỉ được phép thực hiện trên môi trường máy chủ nội bộ.
