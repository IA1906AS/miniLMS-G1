# EduShield miniLMS

EduShield miniLMS là nền tảng quản lý học tập trực tuyến được xây dựng bằng Python và Flask. Dự án cung cấp một SPA phục vụ học viên, giảng viên và quản trị viên; backend JSON API chịu trách nhiệm xác thực, phân quyền, quản lý khóa học, theo dõi học tập và các luồng đánh giá.

Dự án ưu tiên ba mục tiêu: chức năng học tập có thể kiểm thử, kiểm soát truy cập theo vai trò và phòng thủ nhiều lớp ở backend.

## Tính năng hiện có

### Xác thực và tài khoản

- Đăng ký, đăng nhập và đăng xuất bằng email/mật khẩu.
- JWT access token và refresh token; refresh token được xoay vòng và chống phát lại.
- Thu hồi phiên khi đăng xuất, kiểm tra token hết hạn hoặc bị chỉnh sửa.
- Quên mật khẩu, đặt lại mật khẩu và đổi mật khẩu.
- OAuth sandbox cho Google/GitHub với `state` dùng một lần và kiểm tra email đã xác minh.
- Xem và cập nhật hồ sơ, avatar URL và tùy chọn thông báo.
- Khóa tạm thời sau nhiều lần đăng nhập sai.

### Vai trò và quản trị người dùng

- Các vai trò chính: `STUDENT`, `TEACHER`/`INSTRUCTOR` và `ADMIN`.
- Gatekeeper mặc định yêu cầu xác thực; chỉ các endpoint công khai được khai báo rõ mới được bỏ qua JWT.
- Quản trị viên có thể tìm kiếm, lọc và phân trang danh sách người dùng.
- Khóa, mở khóa, thay đổi vai trò và soft-delete tài khoản.
- Kiểm tra quyền sở hữu tài nguyên ở tầng nghiệp vụ nhằm hạn chế IDOR/BOLA.
- Nhật ký audit dành cho quản trị viên, có loại bỏ dữ liệu nhạy cảm.

### Khóa học và nội dung

- Danh mục công khai với tìm kiếm, lọc và phân trang.
- Trang chi tiết khóa học, đề cương, lộ trình và tài nguyên.
- CRUD danh mục dành cho quản trị viên.
- Giảng viên tạo và cập nhật khóa học, chương, bài học và lộ trình.
- Quản lý tài nguyên qua URL hoặc upload tệp.
- Quy trình gửi duyệt, phê duyệt/từ chối, ẩn/hiện và lưu trữ khóa học.
- Kiểm tra chủ sở hữu khóa học trước khi cho phép chỉnh sửa nội dung.

### Trải nghiệm học tập

- Đăng ký khóa học miễn phí.
- Kích hoạt enrollment trả phí qua thao tác quản trị có `orderId` — chưa tích hợp cổng thanh toán thật.
- Trình phát bài học và kiểm soát quyền truy cập theo enrollment.
- Đánh dấu hoàn thành bài học và tính tiến độ theo khóa học.
- Thông báo trong hệ thống và trạng thái đã đọc.
- Cấp và tải chứng chỉ khi học viên đáp ứng điều kiện hoàn thành.
- Giảng viên xem danh sách học viên và báo cáo tiến độ của khóa học mình phụ trách.

### Bài tập và đánh giá

- Tạo bài tập, nộp bài, xem bài nộp, chấm điểm và nhận xét.
- Chống gửi trùng bằng `Idempotency-Key` ở luồng nộp bài an toàn.
- Vòng đời quiz có lưu câu trả lời, nộp bài, chặn nộp hai lần và kiểm tra thời hạn.
- Bảo vệ kết quả và lượt làm quiz theo học viên, giảng viên và quản trị viên.
- Kiểm tra đạo văn thông qua adapter có circuit breaker.

### Độ tin cậy và xử lý đồng thời

- Timeout và cache fallback cho dashboard khi dịch vụ thống kê chậm.
- Circuit breaker cho dịch vụ kiểm tra đạo văn.
- Transactional outbox cho sự kiện enrollment, có retry, dead-letter và chống gửi lại.
- Bulkhead giới hạn tác vụ xuất báo cáo để bảo vệ các endpoint quan trọng.
- Khóa và kiểm tra dung lượng khi giữ/chốt chỗ học, tránh vượt quá sức chứa.
- Idempotency và kiểm soát trạng thái cho các thao tác dễ bị lặp hoặc chạy đồng thời.

## Kiến trúc và công nghệ

| Thành phần | Công nghệ |
| --- | --- |
| Backend | Python 3.13+, Flask 3.1+, JSON API |
| Xác thực | PyJWT, bcrypt |
| Dữ liệu | SQLAlchemy 2, PostgreSQL qua psycopg; có chế độ in-memory cho phát triển/test |
| Validation | Pydantic, email-validator và validation nghiệp vụ tại service/store |
| Frontend | SPA, Alpine.js, Tailwind CSS và design system CSS riêng |
| Kiểm thử | Pytest, coverage |
| Chất lượng | Ruff, Mypy strict, pre-commit |
| Bảo mật tĩnh | Semgrep và pip-audit |

Luồng xử lý backend chính:

```text
HTTP request
  -> deny-by-default authentication gate
  -> route-level RBAC
  -> input validation
  -> service ownership/domain checks
  -> store hoặc SQLAlchemy transaction
  -> standardized error, response sanitization và audit
```

## Cơ chế bảo mật

- `JWT_SECRET` là bắt buộc và phải dài tối thiểu 32 ký tự khi khởi tạo ứng dụng theo luồng chuẩn.
- JWT chỉ được giải mã bằng thuật toán cho phép; token sai chữ ký, hết hạn hoặc đã thu hồi bị từ chối.
- Mật khẩu được băm bằng bcrypt; API không trả về password hash.
- Refresh token được lưu dưới dạng hash, xoay vòng khi refresh và bị vô hiệu hóa khi phát hiện replay.
- Endpoint riêng tư được bảo vệ mặc định; RBAC phía backend không phụ thuộc vào việc ẩn nút trên giao diện.
- Payload được giới hạn field, kiểu và độ dài để giảm mass assignment và dữ liệu không hợp lệ.
- Upload chỉ cho phép PDF, TXT, PNG và JPEG, tối đa 10 MiB; tên lưu trữ ngẫu nhiên và đường dẫn được kiểm tra chống traversal.
- Lỗi ngoài dự kiến trả response chuẩn, không đưa stack trace hoặc raw exception cho client.
- Response API có chính sách chống cache dữ liệu riêng tư và các header như `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` và `Permissions-Policy`.
- Audit log và outbox payload loại bỏ các trường credential phổ biến.
- CI kiểm tra lint, format, type, test/coverage và Semgrep SAST.

Các kiểm soát trên giảm rủi ro nhưng không thay thế hardening hạ tầng, TLS, secret manager, backup, giám sát và kiểm thử xâm nhập trước khi triển khai production.

## Cài đặt và chạy cục bộ

### Yêu cầu

- Python 3.13 trở lên.
- [uv](https://docs.astral.sh/uv/).
- PostgreSQL nếu cần lưu dữ liệu bền vững. Có thể bỏ qua `DATABASE_URL` để chạy chế độ in-memory phục vụ phát triển.

### 1. Cài dependency

```bash
uv sync --frozen --all-groups
```

### 2. Cấu hình môi trường

Không commit secret hoặc file `.env`. Hãy tạo một `JWT_SECRET` riêng, ngẫu nhiên và dài ít nhất 32 ký tự.

PowerShell:

```powershell
$env:JWT_SECRET = (uv run python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:TOKEN_TTL_SECONDS = "900"
$env:AUDIT_LOG_PATH = "audit.log"
# Tùy chọn khi dùng PostgreSQL:
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@localhost:5432/lms_db"
```

Bash:

```bash
export JWT_SECRET="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export TOKEN_TTL_SECONDS=900
export AUDIT_LOG_PATH=audit.log
# Tùy chọn khi dùng PostgreSQL:
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/lms_db'
```

Nếu không khai báo `DATABASE_URL`, ứng dụng sử dụng store in-memory và dữ liệu không được bảo toàn sau khi tiến trình dừng.

### 3. Khởi động ứng dụng

```bash
uv run python run.py
```

Mở `http://127.0.0.1:5000` trong trình duyệt. Có thể đặt biến `PORT` để đổi cổng và chỉ bật `FLASK_DEBUG` trong môi trường phát triển.

## Kiểm thử và kiểm tra chất lượng

```bash
uv run --frozen pytest -q
uv run --frozen ruff check src tests
uv run --frozen ruff format --check src tests
uv run --frozen mypy src
uv run --no-sync semgrep scan --config=.semgrep/minilms_rules.yaml --metrics=off --error
```

Để bật hook kiểm tra trước mỗi commit:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Cấu trúc mã nguồn

```text
frontend/                 SPA giao diện người dùng
static/                   design system và tài nguyên tĩnh
src/lms_project_1/
  __init__.py             application factory và API tích hợp
  auth.py                 xác thực, phiên và OAuth sandbox
  gate.py                 authentication gate và RBAC
  course_management.py    danh mục, khóa học, curriculum, resource
  learning.py             enrollment, tiến độ, thông báo, chứng chỉ
  services.py             nghiệp vụ và authorization theo domain
  store.py                persistence abstraction và transaction logic
  models.py               SQLAlchemy models
  errors.py               lỗi chuẩn, response sanitization, security headers
  audit.py                audit logging
  dashboard.py            timeout và fallback cho dashboard
  plagiarism.py           circuit breaker
  quizzes.py              quiz state machine
  outbox.py               transactional outbox
  reports.py              report export bulkhead
  reservations.py         giữ chỗ và kiểm soát sức chứa
tests/                    unit, API integration, RBAC/IDOR và regression tests
```

## Trạng thái và giới hạn hiện tại

- OAuth hiện là sandbox flow, chưa phải tích hợp production với Google/GitHub.
- Chưa có payment gateway hoặc webhook thanh toán thật; enrollment trả phí chỉ được kích hoạt bởi quản trị viên.
- Chưa triển khai các module blog/community và commerce hoàn chỉnh.
- Rate limit đăng nhập hiện theo tiến trình ứng dụng; môi trường nhiều instance cần shared rate-limit store.
- Frontend hiện tải Alpine.js và Tailwind CSS từ CDN; production nên self-host asset và áp dụng CSP phù hợp.
- Endpoint `/assignments/submit-vulnerable` chỉ phục vụ minh họa/kiểm thử về idempotency và phải bị vô hiệu hóa trước khi phát hành production.
- Flask development server chỉ dùng để phát triển, không phải production server.

## Nguyên tắc đóng góp

- Không commit secret, access token, dữ liệu cá nhân, audit log, database dump hoặc file môi trường.
- Mọi API riêng tư phải có kiểm tra role và quyền sở hữu ở backend.
- Thay đổi dữ liệu cần giữ hành vi tương thích giữa store in-memory và PostgreSQL khi phù hợp.
- Tính năng mới cần có test happy path, validation, role/IDOR và regression liên quan.
- Chạy các lệnh quality phù hợp trước khi tạo pull request.
