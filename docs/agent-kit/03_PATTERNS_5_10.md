# Spec kỹ thuật cho 5 pattern còn lại (trừ #6)

Tất cả các route, timeout/threshold là đề xuất, **không có số liệu định lượng trong PDF**. Phase 0 phải xác nhận domain, quyền và DB.

## #5 Circuit Breaker — kiểm tra đạo văn
- Tính năng duy nhất: plagiarism check của submission hợp lệ. User chỉ check bài mình hoặc giảng viên sở hữu môn theo policy. Provider adapter callable, fake failure/delay.
- Thuật toán tự viết: `CLOSED`: pass calls, đếm lỗi upstream theo cửa sổ/threshold; `OPEN`: từ chối nhanh (`503`/status unavailable); hết cooldown → `HALF_OPEN`, cho tối đa một số probe; probe pass → `CLOSED`, fail → `OPEN`. Đồng bộ state bằng lock nếu multi-thread; nếu multi-worker state local thì ghi giới hạn.
- Timeout provider **tại adapter** để request không treo. Đừng giấu lỗi xác thực/validation bằng breaker. Không coi 4xx nghiệp vụ là lỗi provider; chỉ tính timeout/5xx/network exceptions.
- Tests: C5-01 success; C5-02 trips threshold; C5-03 open fast-fail không gọi provider; C5-04 recovery half-open; C5-05 simultaneous probes bounded; C5-06 auth unauthorized; C5-07 reset/cooldown using fake clock; C5-08 response không lộ provider secrets.

## #7 State Machine — lượt làm bài kiểm tra
- Tính năng: quiz attempt. Proposed states `CREATED → IN_PROGRESS → SUBMITTED`, thêm `EXPIRED`/`CANCELLED` nếu domain cần. Không cho `SUBMITTED→IN_PROGRESS`, không nộp sau deadline, không sửa đáp án sau submit; mọi transition xác minh actor, ownership, thời gian; DB transaction/optimistic lock hoặc atomic update để tránh double submit.
- Ghi transition table cùng expected HTTP. Thiết kế phân biệt `start`, `save_answer`, `submit`, `expire`, bài chưa bắt đầu, course not enrolled, quiz closed.
- Tests: S7-01 normal start/save/submit; S7-02 save after submit blocked; S7-03 submit expired blocked; S7-04 skip steps blocked; S7-05 student A mutate B blocked; S7-06 concurrent double submit only one succeeds; S7-07 invalid content rejected.

## #8 Transactional Outbox — email xác nhận ghi danh
- Tính năng duy nhất: **email xác nhận đăng ký khóa học**. Trong một DB transaction: ghi enrollment và **outbox event** (tối đa 1 bảng mới cho pattern là outbox). Worker riêng đọc pending/lease, gửi qua fake mailer/SMTP adapter, đánh dấu sent; lỗi retry bounded, backoff có kiểm soát, dead-letter/failed state. Không ghi password/token vào event.
- Nếu data **in-memory** hoàn toàn, không thể hứa durable event qua process crash. Ghi rõ hạn chế và xin giảng viên quyết định storage. Tránh dùng package outbox triển khai sẵn.
- Idempotency: dedupe bằng khóa enrollment+event type, xử lý at-least-once không hứa exactly-once delivery. Đề xuất `event_id` nhận biết trùng; nếu có thể email gửi trước khi worker crash, email vẫn có thể gửi lại.
- Tests: O8-01 commit both; O8-02 rollback both; O8-03 worker retry after failure; O8-04 duplicate event/enrollment no duplicate logical row; O8-05 crash/restart persistence (nếu DB); O8-06 secrets redaction; O8-07 unauthorized enrollment prevented.

## #9 Bulkhead — xuất báo cáo điểm
- Tính năng duy nhất: export report. Cô lập bằng bounded semaphore + worker pool/queue riêng hoặc process pool cho CPU-heavy, tài nguyên có mức trần; quá tải trả `429/503` với thông báo an toàn, không làm nghẽn `/me`/dashboard.
- Đừng dùng Flask dev server để kết luận định lượng về production isolation. CPU heavy cần process pool/queue ngoài HTTP worker, thread pool không đủ cách ly CPU-bound trên mọi runtime. Queue capacity/busy metrics được ghi lại.
- Tests: B9-01 normal authorized export; B9-02 simultaneous exports bounded; B9-03 saturation yields quick controlled response; B9-04 unrelated endpoint latency bounded under load; B9-05 export never leaks other students outside permitted scope; B9-06 server cleanup cancellation/errors.

## #10 Reservation with Expiration — giữ chỗ có thời hạn
- Tính năng duy nhất: đăng ký lớp giới hạn sĩ số, không nhầm `enroll` của P8 là pattern thứ hai trên cùng tính năng. Định nghĩa rõ reservation vs confirmed enrollment. Bảng proposed `seat_reservations(id,class_id,user_id,expires_at,status)`; cấp phát chỗ phải **atomic** transaction/lock, đếm `CONFIRMED + ACTIVE_UNEXPIRED_HOLDS` <= capacity.
- Confirm chỉ bởi chủ hold và trước expiry; expire bằng server-side clock; tránh phụ thuộc duy nhất cron để giải phóng chỗ: khi reserve mới, đếm loại trừ giữ chỗ quá hạn hoặc cleanup transactional. Một user không chiếm nhiều holds cùng lớp; kiểm tra multi-process DB lock.
- Tests: R10-01 reserve/confirm; R10-02 hold expires returns capacity; R10-03 100 concurrent contenders never overbook; R10-04 forged/other-user confirm blocked; R10-05 duplicate reserve blocked; R10-06 boundary expiration deterministic; R10-07 cancel releases seat.

## Constraints review
Trước khi viết: table count/module count mỗi pattern, own logic vs third-party, existing route behavior, teammate ownership. Sau khi viết: acceptance test + security test + README demo + evidence link.
