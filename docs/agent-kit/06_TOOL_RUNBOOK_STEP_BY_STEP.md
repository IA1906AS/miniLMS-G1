# Runbook thực hành — từng bước để chủ dự án tự kiểm thử

> Agent phải đối chiếu host/port/API thực tế trước khi cho user dán lệnh. Mọi ví dụ dưới đây **chỉ localhost**. Không lưu JWT thực vào screenshot hoặc Git.

## Chuẩn bị (Windows PowerShell)
1. Mở PowerShell trong thư mục miniLMS; tạo `git switch -c test/local-security-audit` hoặc giữ branch riêng sau khi chắc chắn working tree sạch.
2. `uv sync` (hoặc `uv pip install -r requirements.txt` trong venv nếu project chỉ có requirements); `uv run pytest -q`.
3. Mở server `uv run flask --app app run --host 127.0.0.1 --port 5000` ở terminal riêng. Đảm bảo chỉ local, không bật debug cho demo ghi hình.
4. Copy `.env.example` thành `.env` trong máy nếu cần, đặt JWT_SECRET dài >=32, **không commit**. Bắt đầu bằng seed lab, dữ liệu không thật.
5. Gọi endpoint smoke `curl.exe -i http://127.0.0.1:5000/me` → thường 401 khi PDF B áp dụng. Kiểm tra JSON.
6. Đăng nhập từ file request riêng và lưu token **chỉ local**; trong evidence hãy thay token bằng `[REDACTED]`.

## Burp Suite Community — thực hành bắt và sửa request
1. Mở Burp Suite → **Temporary project** → **Use Burp defaults**. Dùng browser built-in tại Proxy → Intercept → Open Browser (đỡ phải cấu hình CA hệ thống).
2. Chạy miniLMS `http://127.0.0.1:5000` trong browser của Burp, đăng nhập tài khoản seed TEST. Nếu không thấy traffic, kiểm tra proxy settings/Intercept/HTTP history.
3. Vào **Proxy → HTTP history**, chọn request dashboard (hoặc gọi bằng browser), right-click **Send to Repeater**.
4. Trong **Repeater**, đổi `course_id` sang môn actor không sở hữu, bấm **Send**, quan sát 403/404. Tạo screenshot đã che token.
5. Trở lại dashboard, bật fake provider delay theo **cấu hình local do Agent xây**; lặp lại request. Dùng thời gian hiển thị trong Burp hoặc đo bằng script; ghi `elapsed`, status, body, `isFallback` và timestamp. So sánh baseline vs patch ở cùng delay.
6. Với quiz: login Student A, gửi request sửa attempt của Student B trong Repeater; đảm bảo 403/404. Với reservation: gửi lại confirm expired; đảm bảo rejected.
7. Với grades: thay body `{"score":"10"}`, `{"score":true}`, `{"score":11}` nếu route PDF B có; mỗi trường hợp 400.
8. Không xuất raw Burp project có token/password; chỉ trích request redacted và ảnh an toàn.

## OWASP ZAP — passive + giới hạn active trên local
1. Mở ZAP → Quick Start → **Manual Explore** → nhập `http://127.0.0.1:5000` → launch browser.
2. Đăng nhập tài khoản test, duyệt các trang bạn có quyền, xem **Sites / History / Alerts**. Ưu tiên **passive scan** lúc đầu; không có alert không đồng nghĩa an toàn.
3. Chỉ sau snapshot DB và đảm bảo local: active scan nếu được cho phép, scope toàn bộ chỉ `127.0.0.1:5000`, không scan ngoài scope. Hạn chế threads/intensity; không scan endpoint ghi dữ liệu như enroll/submit/grade khi chưa có rollback fixture.
4. Export summary và tự xác minh alert bằng reproduction. Ghi false-positive và điều kiện kiểm tra.

## SQLMap — chỉ khi dùng SQL thật và có endpoint SQL phù hợp
1. Xác nhận trong code endpoint thực sự query SQLite/PostgreSQL/... và user có quyền scan. Nếu PDF B in-memory được áp dụng nguyên bản: ghi **NOT APPLICABLE** cho SQLMap, không giả định SQLi.
2. Trong Burp, capture một request read-only có query param thật dẫn tới SQL. **Xóa token khỏi bản report**, lưu `request-local.txt` trong folder tạm bị `.gitignore` (nếu cần token thì chỉ chạy local).
3. Chạy mức nhẹ: `sqlmap -r request-local.txt --batch --risk=1 --level=1 --threads=1 --timeout=5 --retries=0`.
4. Không thêm `--dump`, `--dbs`, `--os-shell`, dữ liệu thực; dừng nếu app có dấu hiệu gián đoạn. Negative output chỉ chứng minh tại endpoint/parameters/settings đã chạy.

## curl / Python tests timeout & fallback
1. Agent tạo fake stats provider local, nhận `delay_ms` và `mode=ok|error|delay`; log rõ port/URL để không ảnh hưởng production.
2. PowerShell ví dụ đo tổng time: `curl.exe -s -o NUL -w "HTTP=%{http_code} total=%{time_total}s`n" http://127.0.0.1:5000/me` (trên Linux/macOS thay `NUL` bằng `/dev/null`).
3. Đối với dashboard cần auth, dùng Burp Repeater hoặc script `httpx` với bearer test token lấy lúc runtime; không paste token vào file evidence.
4. Chạy `uv run pytest -q -k timeout` và `uv run pytest -q -k security` nếu Agent tạo markers/names; tuyệt đối không khẳng định có tests trước khi file được tạo.
5. Kịch bản baseline: fake delay 3 giây, dashboard chưa có timeout; patched: cùng delay, có timeout và fallback. 10 lần/cấu hình; xuất CSV latency thực và tính median/p95.

## Load test nhỏ với Locust/k6/pytest concurrency
1. Chỉ chạy trên local test server với **tối đa 20 concurrent, tối đa 60s**, tránh làm hỏng demo.
2. Nhiệm vụ: chạy 10 yêu cầu export chậm rồi GET `/me` 20 lần; đo phản hồi `/me` dưới tải để chứng minh Bulkhead.
3. Không gửi requests không giới hạn, không fuzz login brute force trên account thật. Ghi phần cứng, worker config, thời gian, percentile và limit.

## Ghi minh chứng
Tạo thư mục `evidence/YYYY-MM-DD/` (gitignored nếu chứa nhạy cảm), lưu `environment.md`, `commands.md`, `test-output.txt`, `latency.csv`, `burp-before.png`, `burp-after.png`, `zap-summary.html`, `sqlmap-summary.txt` nếu áp dụng. Điền `docs/agent-kit/08_EVIDENCE_TEMPLATE.md`.
