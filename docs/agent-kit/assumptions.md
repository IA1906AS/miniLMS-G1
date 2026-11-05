# Giả định Kỹ thuật & Ranh giới Thiết kế (miniLMS Patterns #5–#10)

Tài liệu này ghi nhận các giả định an toàn trước khi triển khai các defensive pattern từ #5 đến #10 trong miniLMS theo đúng tinh thần `AGENTS.md`, `00_MASTER_PLAN.md` và `01_REQUIREMENTS_TRACEABILITY.md`.

---

## 1. Ranh giới giữa 2 Nguồn Đề Bài (PDF A & PDF B)

1. **Nguồn A (`Bai_tap_defensive_pattern_LMS.pdf`)**:
   - Quy định: Nhóm chọn các pattern phân công cho từng thành viên (không trùng lặp); mỗi pattern gắn liền với **một tính năng LMS cụ thể**, tối đa **1 module code Python mới** và **1 bảng dữ liệu mới** cho mỗi pattern.
   - Agent tự lập trình thuật toán chính, không dùng thư viện có sẵn bao trọn pattern (như `pybreaker`, `celery`, v.v.).
   - Phân công: User chịu trách nhiệm dải pattern **#5–#10**, trong đó chọn **#6 Timeout & Fallback** làm trọng tâm báo cáo cá nhân. Thứ tự triển khai: **#6 → #5 → #7 → #8 → #9 → #10**.

2. **Nguồn B (`de-bai.pdf`)**:
   - Yêu cầu kiến trúc bảo mật Defense in Depth (8 tầng), deny-by-default, thứ tự kiểm tra lỗi: `401 (Unauthenticated) → 404 (Không tìm thấy tài nguyên gốc) → 403 (Forbidden) → 400 (Validation)`.
   - Lưu trữ gốc yêu cầu nạp từ `seed.json` vào in-memory store mỗi lần gọi `create_app()`.
   - Bộ test A1–A19 phải luôn xanh (PASS 100%), không được làm gãy bất kỳ hợp đồng bảo mật nào.

3. **Xử lý xung đột DB vs In-memory (Trade-off Decision)**:
   - *Vấn đề*: PDF B cấm lệ thuộc DB cố định ngoài in-memory khi test A1–A19; nhưng PDF A có Pattern #8 (Outbox) và #10 (Reservation) cần tính bền vững hoặc nguyên tử.
   - *Giải pháp an toàn*: Áp dụng thiết kế **Dual-mode Store** (đã có sẵn nền tảng trong repo `store.py` và `database.py`):
     - Mặc định khi chạy test (`create_app()` không cấu hình `DATABASE_URL`): Lưu trữ in-memory có cơ chế `threading.Lock()` bảo vệ tính nguyên tử của State Machine, Outbox và Reservation. Đảm bảo chạy `pytest` 100% offline, độc lập, deterministic, không cần Postgres container.
     - Khi cấu hình `DATABASE_URL`: Áp dụng SQLAlchemy ORM Model tương ứng để ánh xạ bảng DB quan hệ thực tế.
     - Thỏa mãn cả hai yêu cầu: Tuân thủ in-memory của PDF B và nguyên tắc tối đa 1 bảng dữ liệu/pattern của PDF A.

---

## 2. Giả định Chi tiết Từng Pattern (#5 – #10)

| Pattern | Tính năng LMS | Module dự kiến | Bảng dữ liệu dự kiến | Giả định ngưỡng & hành vi |
|---|---|---|---|---|
| **#6 Timeout & Fallback** | Thống kê Dashboard Khóa học (`GET /courses/<course_id>/dashboard`) | `src/lms_project_1/patterns/p6_timeout.py` | 0 bảng (lưu cache trong Store memory/cache) | Timeout mặc định 1.0s (testable/injectable). Fallback trả về số liệu đã lưu an toàn gần nhất (`isFallback=True`, kèm `asOf` và `reasonCode`). Nếu không có cache, trả degraded an toàn (không bịa số liệu). |
| **#5 Circuit Breaker** | Kiểm tra đạo văn bài nộp (`POST /courses/<cid>/submissions/<sid>/plagiarism-check`) | `src/lms_project_1/patterns/p5_circuit_breaker.py` | 0 bảng (State quản lý thread-safe trong Store) | 3 trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`. Ngưỡng lỗi: 3 lần liên tiếp lỗi upstream chuyển sang `OPEN`. Cooldown: 5 giây. Không tính lỗi 4xx (validation/auth) vào breaker. |
| **#7 State Machine** | Vòng đời lượt làm bài kiểm tra (`quizzes/<quiz_id>/attempts`) | `src/lms_project_1/patterns/p7_state_machine.py` | 1 bảng `quiz_attempts` (và dict `store.quiz_attempts`) | Các trạng thái: `CREATED → IN_PROGRESS → SUBMITTED` / `EXPIRED`. Chặn sửa bài sau nộp, chặn nộp quá hạn, kiểm tra quyền student sở hữu attempt. |
| **#8 Transactional Outbox** | Email xác nhận ghi danh khóa học (`POST /courses/<cid>/enroll`) | `src/lms_project_1/patterns/p8_outbox.py` | 1 bảng `outbox_events` (và list `store.outbox_events`) | Khi ghi danh thành công, bản ghi enrollment và event outbox được tạo đồng thời. Worker mô phỏng quét event `PENDING` gửi email giả lập và cập nhật `PROCESSED`. |
| **#9 Bulkhead** | Xuất báo cáo điểm (`GET /courses/<cid>/grades/export`) | `src/lms_project_1/patterns/p9_bulkhead.py` | 0 bảng | Giới hạn concurrency tối đa (ví dụ: semaphore max 2 concurrent requests). Request vượt quá giới hạn trả về `429/503 Bounded Capacity` nhanh, không làm nghẽn endpoint `/me` hay `/grades`. |
| **#10 Timed Seat Reservation** | Giữ chỗ lớp giới hạn sĩ số (`POST /courses/<cid>/reserve`, `confirm`) | `src/lms_project_1/patterns/p10_reservation.py` | 1 bảng `seat_reservations` (và dict `store.seat_reservations`) | Sĩ số tối đa được kiểm tra nguyên tử: `Số chỗ confirmed + Active hold chưa hết hạn <= Capacity`. TTL giữ chỗ mặc định 300s (5 phút, testable bằng fake clock). Quá hạn tự động thu hồi. |

---

## 3. Ranh giới với Đồng đội

- Không sửa hoặc ghi đè các hàm hiện tại trong `auth.py`, `gate.py`, `guards.py`, `errors.py`.
- Các route hiện tại của đồng đội (`/me`, `/courses/<cid>/grades`, `/auth/login`, `/assignments/submit`, `/account/*`) được giữ nguyên chữ ký (signature) và hợp đồng HTTP.
- Mọi pattern mới được đóng gói độc lập trong package con `src/lms_project_1/patterns/` hoặc blueprint riêng để dễ cô lập, tích hợp và kiểm thử.

