# Requirements traceability — đối chiếu 2 PDF

## Nguồn A — `Bai_tap_defensive_pattern_LMS.pdf` (1 trang)
- Quy tắc: nhóm chọn **2 pattern trong 10**, hai thành viên **không trùng**; mỗi pattern chỉ cho **một tính năng LMS**, tối đa **một module và một bảng dữ liệu**, tự lập trình phần logic chính.
- Được giao thực hiện tính năng của #5–#10 dưới đây; việc báo cáo chính thức 2 pattern cần chốt với giảng viên nếu 6 tính năng cùng xuất hiện.

| ID | Pattern nguyên văn | Tính năng | Rủi ro gốc theo PDF | Chứng minh |
|---|---|---|---|---|
| P5 | Circuit breaker | Kiểm tra đạo văn | checker ngoài lỗi khiến request treo hàng loạt | state machine breaker & bulk requests |
| P6 | Timeout và fallback | Dashboard thống kê khóa học | service chậm khiến trang không tải được | latency bound, fallback state, before/after |
| P7 | Máy trạng thái | Lượt làm bài kiểm tra | bỏ qua bước, sửa bài đã nộp, nộp quá hạn | transition table + authorization |
| P8 | Transactional outbox | Email xác nhận đăng ký khóa học | dữ liệu lưu nhưng sự kiện mất | transactional enrollment+event + retry |
| P9 | Bulkhead | Xuất báo cáo điểm | task nặng nghẽn chức năng khác | queue/semaphore limited & other API latency |
| P10 | Giữ chỗ có thời hạn | Đăng ký lớp giới hạn sĩ số | vượt sĩ số hoặc giữ chỗ mãi | atomic capacity claim + expiration |

**Lưu ý:** PDF A không cung cấp endpoint URL, DB engine, màu sắc frontend, ngưỡng thời gian cụ thể hay tiêu chí chi tiết #5–#10. Mọi API, TTL, timeout trong kit là **gợi ý triển khai**, phải đối chiếu repo và thống nhất nhóm; không được trình bày là đề gốc.

## Nguồn B — `de-bai.pdf` (6 trang): bài Defense in Depth AuthN/AuthZ Flask
- Trang 1–2: Python 3.11+, Flask 3.x, `create_app(config=None)` load `seed.json` mới mỗi lần, in-memory **không database**; `JWT_SECRET` >=32, `TOKEN_TTL_SECONDS` default 900, `AUDIT_LOG_PATH`; cấu trúc `app/{__init__,store,auth,gate,guards,services,schemas,errors}.py`, `audit.py`.
- Trang 3–4: 4 endpoint bắt buộc: POST `/auth/login`; GET `/me`; GET `/courses/<course_id>/grades`; PUT `/courses/<course_id>/grades/<student_id>`; ma trận ADMIN/INSTRUCTOR/STUDENT; lỗi JSON `{"error":"CODE"}`; check order `401 → 404(course) → 403 → 400 → 404(enrollment)`; JWT HS256 chỉ sub/iat/exp, role từ store mỗi request.
- Trang 4–5: Auth bcrypt cost >=10 hoặc argon2; deny-by-default allowlist duy nhất POST login; role guard + service-level object checks độc lập; strict numeric validation; safe output; bonus brute-force lock 5 failures/15min, audit logs 403/grade changes.
- Trang 5–6: scenarios **A1–A19** và CI, requirements.txt + .env.example, không commit secret.

**Xung đột cần xử lý minh bạch:** PDF B không DB, PDF A có các pattern #8/#10 cần lưu trạng thái bền vững hoặc có tính nguyên tử. Nếu hai PDF áp dụng cùng một repo theo đúng chữ, cần thảo luận với giảng viên về DB riêng cho phần mở rộng hoặc một mô phỏng in-memory (chỉ dùng lab, không bảo đảm durability khi restart). Không tự kết luận cho phép dùng DB.

## Acceptance checks bảo mật từ PDF B (áp dụng nếu project phải tuân thủ B)
| ID | Mục tiêu | Kết quả bắt buộc |
|---|---|---|
| A1 | user không tồn tại vs sai password | cùng 401, JSON giống hệt |
| A2 | `/me` không token | 401 |
| A3 | JWT sửa `sub` nhưng không ký lại | 401 |
| A4 | JWT `alg=none` | 401 |
| A5 | TTL=1, chờ 2s | 401 |
| A6 | mọi response | không password/hash |
| A7 | Chi xem c1 | chỉ score của Chi 200 |
| A8 | Chi xem c2 | 403 |
| A9 | Chi PUT score | 403 |
| A10 | Bình PUT c1 | 403 |
| A11 | admin PUT score | 403 |
| A12 | score 11,-1,"10",true, extra field | 400 cho cả 5 |
| A13 | An PUT c1/u6 (không ghi danh) | 404 |
| A14 | An đổi score u4 thành 9, Chi GET | 200 và thấy 9 |
| A15 | bỏ role decorator, gọi service trực tiếp | vẫn 403 |
| A16 | thêm route GET /debug không được khai báo | không token 401 |
| A17 | create_app thiếu secret | RuntimeError |
| A18 | Dũng sai 5 lần, lần 6 đúng | 429 (mở rộng) |
| A19 | log sau A10/A14 | audit events, không secret (mở rộng) |

Nội dung nguồn B chỉ làm baseline cho app nếu instructor xác nhận cả hai đề đồng thời áp dụng; không để việc thêm patterns làm hỏng A1–A19.
