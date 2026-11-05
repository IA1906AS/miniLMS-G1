# Evidence register / ghi nhận kết quả thực

| Evidence ID | Test ID | Timestamp TZ | Commit SHA | Env | Command / Steps | Expected | Observed | Status PASS/FAIL/NOT RUN/N/A | Artifact path |
|---|---|---|---|---|---|---|---|---|---|
| EV-001 | TT-02 | TODO | TODO | 127.0.0.1:5000 | TODO | response bounded, scoped cache | TODO | NOT RUN | TODO |
| EV-002 | AUTH-02 | TODO | TODO | local | TODO | forbid IDOR | TODO | NOT RUN | TODO |

## Chuẩn dữ liệu log
- CSV: `timestamp,commit,scenario,request_id,latency_ms,http_status,is_fallback,notes`.
- Context: OS, Python version, uv version, Flask version, run mode, workers, DB, server ports, latency cutoff, upstream fake config, test count.
- Sanitization: `[REDACTED_TOKEN]`, `[REDACTED_PASSWORD]`, loại bỏ email cá nhân/dữ liệu sinh viên, screenshot trước khi nộp.
- Chứng cứ FAIL nên có reproduction ổn định, expected vs actual và fix commit; PASS cần raw test output hoặc capture (được bảo vệ).
- Nếu không chạy được tool (ZAP, Burp, SQLMap), ghi NOT RUN/NOT APPLICABLE, lý do, không thay bằng output tưởng tượng.
