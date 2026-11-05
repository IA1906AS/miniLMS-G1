# Pattern #6 — Timeout & Fallback (đề tài báo cáo cá nhân)

## Mục đích (PDF A)
Đối tượng duy nhất: **Dashboard thống kê khóa học**. Rủi ro: dịch vụ thống kê bên ngoài/chậm khiến dashboard không tải được. Bảo đảm trang không bị treo vô hạn; thời gian xử lý bị giới hạn; phản hồi thay thế có căn cứ, an toàn và không làm lộ thông tin.

## Thiết kế thành phần
1. `DashboardService.get(course_id, actor, deadline, stats_client)`: kiểm tra actor được xem course trước tiên.
2. `StatsClient` qua interface, fake delay/fail/hang cho tests; không phụ thuộc public host.
3. Deadline tổng request + timeout provider (ví dụ đề xuất 0.8s/1.0s; configurable, không phải số trong đề).
4. Fallback: **dữ liệu cached của chính course + quyền được xác minh**, có timestamp/TTL và metadata `isFallback=true`/`asOf`; nếu không có cache hợp lệ, trả response degraded với placeholder/503 theo contract team. **Không tạo số lượng học viên/điểm giả**, không trả cache từ course khác hoặc cached identity đã hết quyền.
5. Không `except Exception: return 200` vô điều kiện; phân biệt timeout/unavailable với auth, permission, validation, programmer errors. Không nuốt cancellation; thu hồi hoặc hạn chế background work để tránh backlog.
6. Chặn thác tài nguyên: giới hạn số upstream calls đồng thời, connection pool timeout, cancellation hoặc bounded thread occupancy. Nếu code sync Flask, không kỳ vọng `future.result(timeout=...)` tự dừng worker Python; phải đảm bảo timeout tại HTTP client, executor bounded, và benchmark dưới load.

## Bộ test bắt buộc
| Test ID | Kịch bản | Expected |
|---|---|---|
| TT-01 | stats client trả ngay | 200 và thống kê đúng; `isFallback=false` |
| TT-02 | stats client delay > timeout, có last-known-good valid cache | hoàn thành trong deadline (+ tolerance), trả fallback đúng course, `asOf` |
| TT-03 | delay > timeout, không cache | bounded response degraded/503, **không fake số liệu** |
| TT-04 | stats client ném timeout/connection error | không 500 stack; fallback hoặc unavailable theo contract |
| TT-05 | unauthorized actor, dù cache có dữ liệu | 403, không trả cached stats |
| TT-06 | nhiều requests đồng thời & client treo | không tăng mãi active workers, `/me` vẫn đáp ứng |
| TT-07 | cache expired/stale | không trình bày như real-time, policy stale rõ ràng |
| TT-08 | config min/max/deadline boundary | validation fail safe, regression |
| TT-09 | actor mất quyền sau khi tạo cache | không truy cập được fallback |
| TT-10 | logs/errors | không lộ secret, stack, data course khác |

## Mô hình baseline lỗi đầu tiên → fix
**Baseline lab (chỉ local, không production):** cùng một fake stats service do nhóm sở hữu; nó có endpoint `/stats?delay_ms=...` nhưng server bind 127.0.0.1. Dashboard gọi service mà **không có timeout hoặc fallback** → request kéo dài đúng theo delay (ví dụ 3s). Không tạo lỗ hổng SQLi/remote code/hack auth. Giữ một test `@pytest.mark.baseline` hoặc local tag riêng tái hiện, không push code lỗi lên main.

**Patch:** strict authorization → bounded upstream request timeout + total deadline → last-known-good valid cache/explicit degraded response → metrics + tests. Chạy cùng input và cùng host để so sánh latency. Nếu không thể instrument baseline trong repo, dùng isolated test fixture/mock và mô tả giới hạn.

## Thí nghiệm minh chứng
1. Cấu hình fake stats service `delay=0`, gọi 10 lần để lấy median success.
2. Baseline gọi `delay=3000ms` với 10 requests tuần tự, đo wall time client timeout >=5s, ghi median/p95 thật; local only.
3. Patch gọi same delay, 10 lần; test expected `elapsed < configured_threshold + jitter_allowance`, ví dụ < 1.5s nếu timeout 1s nhưng quyết định sau máy thật.
4. 10–20 concurrent requests với limits; ghi availability `/me` và active worker count. Không tự ghi số '3s→1s' nếu chưa chạy.
5. Phản hồi an toàn: fallback flags, cache timestamp, không rò data; chụp Burp Repeater before/after.
6. Biểu diễn threat: availability/DoS cục bộ do upstream slowness; **không gọi đây là SQLi hay data breach**.

## Định lượng
`latency_ms`, `http_status`, `fallback_used`, `timeout_reason`, `timestamp`, `commit_sha`, `request_id`. Tính median và p95 từ mẫu đủ số; nêu sample size / machine / local config. Không kết luận throughput bằng 1 request.
