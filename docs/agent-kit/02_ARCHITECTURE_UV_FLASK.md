# Kiến trúc & uv — không thay stack hiện có nếu chưa kiểm tra

## Phase 0 commands
```bash
git status --short
git branch --show-current
find . -maxdepth 3 -type f | head -120  # macOS/Linux; Windows: Get-ChildItem -Recurse -File | Select-Object -First 120
uv --version
uv tree  # khi đã tồn tại pyproject.toml
```
Trên Windows PowerShell thay `find` bằng `Get-ChildItem` như chú thích. Kiểm tra `.python-version`, `pyproject.toml`, `uv.lock`, `requirements.txt`, `app/__init__.py`, `tests/`, API mappings, migration và nền tảng DB; không in nội dung `.env`/secrets. `uv init` chỉ nếu repo chưa cấu hình Python; tránh tạo project lồng trong project.

## Dùng uv an toàn
```bash
uv python install 3.11
uv sync
uv run pytest -q
uv run flask --app app run --host 127.0.0.1 --port 5000
```
- Các lệnh trên là **mẫu**, chỉ chạy sau khi đối chiếu pyproject/requirements hiện tại. Nếu repo chỉ có `requirements.txt`, cân nhắc `uv pip install -r requirements.txt` trong venv hoặc chuyển có kiểm soát bằng `uv add -r requirements.txt`; vẫn giữ `requirements.txt` cho grading từ PDF B (có thể export from lock).
- Dev dependencies ví dụ: `uv add --dev pytest pytest-cov ruff` nếu thiếu; Flask, PyJWT, bcrypt/argon2 theo repo/đề. Không cài Redis/Celery/resilience library trọn gói thay thuật toán pattern.
- `flask --app app run` có thể được yêu cầu bởi PDF B, đảm bảo cú pháp cũ hoạt động ngay cả khi dùng uv.

## Separation of concerns
Proposed API → auth & role guard → validation → service(domain + authorization) → store/repository → external adapter/fake. Mọi service quan trọng phải tự kiểm tra object permissions (không chỉ route). `create_app(config=None)` đọc seed mới nếu PDF B áp dụng. Timeouts, clock, dispatch, email, plagiarism checker là injectable dependencies để test deterministic.

## Gợi ý endpoints (không phải endpoint được nêu trong PDF)
- GET `/courses/<course_id>/dashboard` (P6)
- POST `/courses/<course_id>/submissions/<id>/plagiarism-check` (P5)
- POST `/quizzes/<quiz_id>/attempts`, POST `/attempts/<id>/submit` (P7)
- POST `/courses/<course_id>/enroll` (P8)
- GET `/courses/<course_id>/grades/export` (P9)
- POST `/classes/<class_id>/reservations`, POST `/reservations/<id>/confirm` (P10)
Những URL này chỉ là drafts: Agent phải kiểm tra design của team trước khi tạo route.

## Data model decisions
Mỗi pattern tối đa 1 bảng mới. P6 có thể **0 bảng** (read projection/fallback cache ephemeral). P5 0–1 table tùy metrics persistence; P7 1 table `quiz_attempts`; P8 1 table `outbox_events` (tái sử dụng enrollment hiện hữu); P9 0–1 table; P10 1 table `seat_reservations`. Nếu thiếu `enrollments` hay `classes`, cần làm rõ chủ sở hữu bảng nền và giới hạn áp dụng. Đừng đặt trạng thái breaker hay semaphore vào các bảng không cần thiết. Không dùng real email/real plagiarism provider trong tests.

## Shared concerns
- Deadline propagation & service timeout riêng, không nuốt `Forbidden/Unauthenticated/ValidationError` thành fallback 200.
- Không serialize tokens, seed passwords, raw provider responses, stack traces vào dashboard/export.
- Các endpoint mới mặc định deny-by-default nếu đề B áp dụng, và quyền trên course/student check trong service.
- Trả fallback kèm metadata (`isFallback`, `asOf`, `reasonCode`) **chỉ khi team chấp thuận contract**, không hiển thị error stack.
