# Master Plan — triển khai & kiểm thử miniLMS

## Thành quả đầu ra
(1) Tính năng #5–#10 có chức năng LMS cụ thể; (2) mỗi pattern có test chuẩn + negative + isolation; (3) riêng #6 có baseline vs patched có thể tái hiện; (4) user có runbook kiểm thử thủ công và bộ bằng chứng; (5) report rõ phát hiện và khắc phục; (6) không phá phần việc đồng đội.

## Phases / gates

| Phase | Công việc | Gate hoàn thành |
|---|---|---|
| 0 — Audit repo | `git status`, cây source, routes, models, DB, auth, test, requirements/uv, đề bài, ai sở hữu phần nào | GAP checklist, sơ đồ luồng, kế hoạch thay đổi; không code tùy tiện |
| 1 — Foundations | branch, dependency uv, tests, test seed, settings, explicit routes/auth, fake dependencies | test hiện có xanh; build reproducible; không làm mất hợp đồng API |
| 2 — #6 | Dashboard statistics + deadline timeout/fallback, isolated fault simulation | 6 scenario TT + security + baseline/patch run |
| 3 — #5 | Plagiarism endpoint + circuit breaker, simulated external checker | CLOSED/OPEN/HALF_OPEN tested, isolation |
| 4 — #7 | Quiz attempt lifecycle | transitions/expiry/ownership/race tests |
| 5 — #8 | Enrollment confirmation via outbox | atomicity, worker delivery, duplicate-safe, restart; DB decision documented |
| 6 — #9 | Grade report export with bounded worker isolation | saturation returns controlled error; other endpoints healthy |
| 7 — #10 | Capacity-limited reservations and expiration | concurrent reservations never exceed capacity, expiration reclaim |
| 8 — Integration | teammate contract freeze, merged branches, full CI, tests A1–A19 if applicable | regression and role matrix green; no merge conflicts |
| 9 — Security audit | pytest, Burp, ZAP, SQLMap if relevant, rate limits, fault injection | evidence index, PASS/FAIL/NOT RUN supported by artifacts |
| 10 — Report | methodology, before-vs-after #6, risk rating, remediation, screenshots, citations | reproducibility checklist, honest limitations |

## Chiến lược triển khai
- Mở `docs/agent-kit/01_REQUIREMENTS_TRACEABILITY.md` và map từng pattern sang **một** tính năng; tránh trộn logic cùng một pattern vào nhiều tính năng.
- Với mỗi pattern, cố gắng sửa files có sẵn; chỉ thêm **tối đa 1 module Python và 1 bảng dữ liệu** tính riêng pattern. Test và tài liệu là supporting files; nếu giảng viên tính những thứ này là module thì cần hỏi trước.
- Ưu tiên fake service có interface tương tự production; không cho worker lỗi giữ request mãi. Config thời gian nên injectable để test không phải `sleep` kéo dài.
- Chốt team interfaces: route, auth decorators, services, DB schema, error envelope, shared configuration, naming. Giữ schema migration thuận/nghịch và không xóa dữ liệu thật.
- Sau mỗi phase chạy `uv run pytest -q` (nếu pytest có trong env); `uv run ruff check .` (nếu ruff đã thiết lập), và API smoke tests. Nếu thiếu công cụ, cài như dev dependency sau khi kiểm tra repo.
- Dùng commits theo phase: `feat(pattern-6): ...`, `test(pattern-6): ...`, `fix(pattern-6): ...`; baseline lỗi là tag/branch local lab, không push lên deployment.

## Definition of Done
- UX/API có happy path, trạng thái lỗi, RBAC/IDOR kiểm thử, validation, output không lộ secret, timeout ổn định, đồng bộ concurrency (nếu có), log có correlation-id không có mật khẩu/token.
- Unit, integration, regression và fault-injection tests; tất cả kết quả có lệnh, timestamp, environment, commit SHA.
- Báo cáo không thay thế bằng lời khẳng định suông. Không đưa thống kê fabricated như '100% chống tấn công'.
