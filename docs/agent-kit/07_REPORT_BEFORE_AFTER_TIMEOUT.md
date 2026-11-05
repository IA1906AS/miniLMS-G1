# Mẫu báo cáo cá nhân: Timeout & Fallback (Pattern #6)

> Chỉ thay các trường `TODO` bằng kết quả có thật. **Không coi đây là báo cáo kiểm thử đã hoàn tất**.

## 1. Thông tin
- Dự án: miniLMS; người thực hiện: TODO; nhóm: TODO; ngày: TODO.
- Phạm vi: Dashboard thống kê khóa học; môi trường local/branch SHA TODO; công nghệ và uv version TODO.
- Mục tiêu: giảm nguy cơ mất khả dụng khi dịch vụ thống kê bên ngoài phản hồi chậm.

## 2. Bối cảnh & threat model
- Actor: user hợp lệ xem dashboard của course được phép.
- External dependency: adapter thống kê (fake/local cho test).
- Tài sản: availability, latency, privacy các thống kê theo course.
- Threat: downstream slow/hang làm giữ Flask request worker, user chờ hoặc client timeout; dưới đồng thời cao dẫn tới resource exhaustion.
- Out of scope: đo hiệu năng production hay tấn công host bên ngoài.

## 3. Baseline / bản lỗi đầu tiên
- Commit/tag: TODO, chỉ lab local.
- Cơ chế: dashboard gọi upstream **không explicit timeout/fallback**.
- Điều kiện tái hiện: fake provider delay TODO ms, n=TODO, concurrency=TODO.
- Steps: (1) start mock; (2) start server; (3) send authorized request; (4) record latency + response; (5) repeat N.
- Quan sát thực: TODO (status, total latency, p50, p95, screenshots paths).
- Nguyên nhân: không có time budget và đường trả lời degraded có kiểm soát; worker bị giữ chờ upstream.

## 4. Bản vá
- Commit SHA: TODO.
- Changes: timeout upstream; time budget request; fallback cached scoped per course; auth before cache; safe error; observability; bounded workers.
- Pseudocode logic: verify actor → try call upstream under bounded deadline → success update last-good data → on recognized upstream timeout/unavailable: serve permitted cache with metadata or explicit 503 if absent → never leak unauthorized course.
- Ràng buộc còn lại: stale stats, background cancellation / Flask worker model, fake provider vs actual provider.

## 5. Kiểm thử đối chứng
| Mục | Baseline (thực đo) | Patched (thực đo) | Minh chứng |
|---|---|---|---|
| Fake delay | TODO | cùng TODO | config |
| Median latency | TODO | TODO | CSV |
| P95 latency | TODO | TODO | CSV |
| HTTP status | TODO | TODO | response |
| Fallback flag | N/A | TODO | screenshot |
| Unauthorized course | TODO | TODO | 403/404 evidence |
| Concurrent 10 requests | TODO | TODO | active threads/latency |

## 6. Công cụ & bảo mật
- `pytest` unit/integration test IDs TT-01…TT-10: TODO outcomes.
- Burp Suite Repeater: quyền course, response fallback, redacted screenshots.
- ZAP passive scan: TODO findings (xác minh từng alert).
- SQLMap: TODO/N/A (nêu rõ vì sao in-memory/không SQL).
- Additional patterns #5,7,8,9,10: bảng test-ID và evidence links ở phụ lục.

## 7. Đánh giá và giới hạn
- Impact before: TODO; likelihood under upstream outage: TODO; severity giải thích dựa trên observed data.
- Residual risk: dữ liệu cached cũ, bad cache isolation, worker limits, multi-process behavior, network configuration, quyền truy cập.
- Không gọi patch là “100% bảo mật” hay đoán SLA.

## 8. Kết luận và tài liệu
- Kết luận dựa trên số liệu thực tế, diff code, test regression.
- Trích yêu cầu pattern từ `Bai_tap_defensive_pattern_LMS.pdf` (trang 1); nguyên tắc AuthN/AuthZ từ `de-bai.pdf` (trang 1–6, nếu áp dụng).
- Đính kèm screenshot/log sanitized, config, commit SHA, exact commands.
