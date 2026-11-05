---
name: minilms-implementation
description: Designs and implements Flask/uv miniLMS defensive patterns 5-10 using repository audit, per-feature constraints, tests, and safe incremental changes.
---

# Skill: miniLMS Pattern Implementation

## Khi dùng
Khi user yêu cầu xây dựng, sửa, review, test chức năng miniLMS liên quan Circuit Breaker, Timeout & Fallback, Quiz State Machine, Transactional Outbox, Bulkhead, Seat Reservation.

## Bắt buộc đọc theo thứ tự
1. `AGENTS.md` của workspace
2. `docs/agent-kit/01_REQUIREMENTS_TRACEABILITY.md`
3. `docs/agent-kit/00_MASTER_PLAN.md`
4. `docs/agent-kit/02_ARCHITECTURE_UV_FLASK.md`
5. `docs/agent-kit/04_TIMEOUT_FALLBACK_DESIGN.md` và `03_PATTERNS_5_10.md`
6. Hai PDF gốc nếu user đã đặt vào workspace.

## Workflow
1. PHASE 0 ONLY: scan project thật, vẽ map route/domain/DB/tests, git status, existing ownership. Trả bảng GAP. Không tạo source mới trước khi audit.
2. Xác định giới hạn: pattern duy nhất/tính năng, <=1 module và <=1 bảng/pattern; code core do nhóm viết, không phụ thuộc full implementation library. Note mọi giả định API/TTL/threshold.
3. Xây #6 đầu tiên; giữ baseline local cho report, sau đó patch; tạo test TT-01..TT-10 và benchmark (không ghi kết quả giả).
4. Xây #5, #7, #8, #9, #10 theo `03_PATTERNS_5_10.md`; mỗi phase chạy test, security negative, log file changes, commit riêng.
5. Kiểm tra ranh giới đồng đội trước khi merge; nếu `seed.json in-memory` của PDF B là yêu cầu bắt buộc, không tự đưa DB vào core. Đưa các lựa chọn tradeoff và xin xác nhận khi thực sự bị chặn.
6. Chuyển sang skill security audit sau khi code có thể chạy.

## Tiêu chuẩn output từng phase
- File list + diff summary; line references; route contract; module/table count.
- Command chạy thực tế trong repo, test names/cases, kết quả PASS/FAIL/NOT RUN.
- Bảo mật: RBAC + service authorization, no IDOR, validation, timeout handling, safe JSON, concurrency.
- Không commit secret; không deploy baseline thiếu timeout.
