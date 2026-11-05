# Ma trận kiểm thử bảo mật & reliability

## Quy tắc scope
**Chỉ** `127.0.0.1`, `localhost` hoặc lab mà bạn thực sự sở hữu/được phép. Không attack scan DNS/public URL, máy nhóm khác. Snapshot seed/DB. Không đo stress vô hạn; load giới hạn mặc định <=20 concurrent, <=60s (điều chỉnh phù hợp phần cứng). SQLMap `--risk=1 --level=1` và **không `--dump`, `--os-shell`, `--file-read`**. Trước scan xác nhận route dùng SQL, tránh SQLMap vô nghĩa cho Flask in-memory.

## Các nhóm test
| ID | Công cụ | Ý tưởng | Dự kiến | Evidence |
|---|---|---|---|---|
| AUTH-01 | pytest/curl/Burp | no/malformed/expired JWT | 401 (theo B nếu áp dụng) | response + server log |
| AUTH-02 | Burp | STUDENT đọc course/attempt học viên khác (IDOR) | 403/404 không data leak | request + response |
| AUTH-03 | pytest | bỏ route guard tạm trong test, gọi service | service vẫn cấm | traceback test expected |
| VAL-01 | Burp/pytest | sai JSON type, extra props, score bool/string | 400 nếu contract B | evidence |
| VAL-02 | Burp | payload XSS dạng text vô hại, kiểm tra escaping frontend | không thực thi trong browser | screenshots |
| DB-01 | SQLMap conditional | injection probe trên input sử dụng SQL | không xác nhận SQLi | output summary |
| P5-01 | pytest/fault simulator | upstream 5xx trip breaker | OPEN, reject fast, recover | state transitions |
| P6-01 | pytest/Burp/curl | delay stats upstream | baseline slow, patch bounded | paired latency |
| P6-02 | pytest/Burp | fallback cache cross-user/cross-course | denied or scoped | response |
| P7-01 | Burp | submit same quiz twice/after deadline | denied | timestamps |
| P8-01 | pytest | worker crash after DB commit | outbox retained | DB status + rerun |
| P9-01 | load bounded | 10 slow exports while GET /me | /me responsive | latency plot/table |
| P10-01 | parallel pytest | capacity=5, 20 reservations | active <=5 | DB count |
| LOG-01 | pytest/manual | scan responses and logs for JWT/password | none | grep summary (redacted) |
| A1-A19 | pytest | exact PDF B cases, if in scope | outputs per source | `pytest -q` |

## Test hierarchy
1. Unit test domain state/time and permissions with fake clock.
2. Integration Flask test client with state seeded per `create_app` and DB transaction rollback if applicable.
3. HTTP local test with Burp/ZAP/curl.
4. Reliability tests with fake provider, bounded concurrency.
5. DB injection review with sqlmap **chỉ khi project thật dùng SQL**.

## Output mỗi finding
`ID, severity, affected route, precondition, affected role, expectation, observed, reproduction steps, screenshots/log path, root cause, fix commit, retest result, residual risk`. Severity phải có lý do (impact + likelihood), không tự động gán Critical.

## Hướng dẫn về 401/403/404
Giữ thứ tự theo PDF B nếu áp dụng: 401 → 404(course) → 403 → 400 → 404(enrollment), nhưng không tiết lộ thông tin qua timing/response khác biệt không cần thiết. Route mới phải default denied nếu chưa authenticated.
