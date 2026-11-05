# Checklist phối hợp hai thành viên

## Trước khi code
- [ ] Chốt ai sở hữu những route/modules nào; pattern chính thức của hai người không trùng nhau.
- [ ] Chốt stack chính, ORM/DB policy, auth role contract, shared error JSON, frontend API, field names.
- [ ] Review mâu thuẫn `de-bai.pdf` in-memory vs persistence yêu cầu pattern #8/#10.
- [ ] Tạo feature branches độc lập, không sửa trực tiếp main.

## Contract freeze
- [ ] OpenAPI-ish endpoint contract: method, URL, body, auth, status, error envelope.
- [ ] Store/DB transaction boundaries, migrations ownership.
- [ ] Seed data dùng riêng test; không commit `.env`, keys, token.
- [ ] Pattern #6 report baseline chỉ local tag, không đưa bản lỗi vào main.

## Merge gate
- [ ] Merge 1 branch một lần, giải quyết conflict bằng review 2 người.
- [ ] `uv sync`, `uv run pytest -q`; nếu PDF B bắt buộc, A1–A19 check.
- [ ] Các route thêm mới vẫn auth-protected (deny default); service vẫn check ownership.
- [ ] Fault injection fake service có disable/canary; không chạy trong production.
- [ ] Logs redacted, no hardcoded real JWT_SECRET; `.env.example` tồn tại.
- [ ] Báo cáo mỗi người một pattern khác nhau, có before/after riêng.
