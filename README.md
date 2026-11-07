# EduShield Codex Fresh Kit (mới hoàn toàn)

Bộ hướng dẫn **repo-local cho Codex** để tiếp tục phát triển EduShield miniLMS trên Python/Flask/uv. Đây là bộ file **mới tạo**, không bao gồm `AGENT.md` cũ, không trộn cấu hình Antigravity, không sao chép `PROJECT_SUMMARY.md`, Excel hay mã nguồn ứng dụng từ ZIP trước.

## LƯU Ý QUAN TRỌNG TRƯỚC KHI XÓA

**Chỉ xóa/di chuyển bộ hướng dẫn agent cũ nếu bạn muốn thay thế nó.** Đừng xóa `src/`, `frontend/`, `tests/`, `pyproject.toml`, `uv.lock`, `database/`, `.github/`, `.git/` của ứng dụng nếu muốn tiếp tục phát triển tính năng trên code hiện tại. ZIP này **không** chứa app có thể chạy độc lập.

Nếu bạn cố ý muốn làm lại từ repository trống: Codex sẽ phải đọc tài liệu, đề xuất thiết kế và scaffold ứng dụng theo yêu cầu đã xác nhận. Khi đó, số test/coverage trong báo cáo cũ không áp dụng.

## Cài đặt vào repo có sẵn

1. Sao lưu hoặc commit trạng thái hiện tại của repository. Tránh ghi đè file đang có mà không review diff.
2. Giải nén **nội dung** ZIP vào thư mục gốc chứa `pyproject.toml` và `uv.lock` (không đặt thành một thư mục lồng bên trong repo).
3. Kiểm tra `git status --short` và `git check-ignore -v AGENTS.md .agents/skills/edushield-gap-audit/SKILL.md`; điều chỉnh `.gitignore` **có chọn lọc** nếu đang bỏ qua skill.
4. Tự kiểm tra bộ kit (không cần uv): `python tools/validate_codex_kit.py` và `python -m unittest discover -s tests_codex_kit -v`.
5. Mở Codex **tại root repo**, xem `PROMPTS.md`, dùng prompt audit đầu tiên. **Không cho triển khai tính năng ngay** trước khi Codex phân loại lại gap bằng code thực.

> Nếu hệ thống của bạn đã có `AGENTS.md`, cần tự quyết định merge/replace trước khi giải nén, đừng ghi đè vô điều kiện.

## Cấu trúc

```text
AGENTS.md                   # Hướng dẫn chính, Codex tự đọc ở repo root
GOALS.md                    # Kết quả mong muốn và giới hạn
PLANS.md                    # Quy trình lập/duyệt kế hoạch
PROMPTS.md                  # Prompt sẵn dùng
.agents/skills/             # 4 skill chuyên biệt, SKILL.md + metadata
backlog/features.csv        # 63 yêu cầu từ Excel, giữ nguyên nội dung gốc
backlog/gap_assessment.csv  # Nhận định sơ bộ, cần audit bằng mã nguồn
backlog/PRIORITY_GUIDE.md   # Cách chọn scope theo độ ưu tiên

docs/                       # Kiến trúc tham chiếu, bảo mật, test, nguồn
  templates/                # Biểu mẫu kế hoạch, review, test report
tools/backlog.py            # CLI đọc/tra cứu/filter; không sửa repository
tools/validate_codex_kit.py # Kiểm tra integrity của bộ kit
tests_codex_kit/            # Test cho tool trong kit; khác test ứng dụng
```

## Bắt đầu nhanh

```bash
python tools/backlog.py stats
python tools/backlog.py list --priority P1 --assessment not_reported
python tools/backlog.py show AUTH-02
python tools/validate_codex_kit.py
```

Dùng đoạn **Prompt 1** trong `PROMPTS.md` để yêu cầu Codex khảo sát repository trước khi sửa mã nguồn.

## Tình trạng bằng chứng

- Excel: 63 đầu việc (`Backlog!A2:M64`); lịch theo W2–W11 và danh sách phân công là **kế hoạch tháng 6–8/2026**, không tự động trở thành deadline hiện tại.
- `PROJECT_SUMMARY.md`: ghi mốc báo cáo `main` commit `076902b`, ngày 2026-11-06; 120/120 test, coverage 74% và Ruff pass tại thời điểm báo cáo. **Bộ kit không tự tái chạy các test ứng dụng**.
- Những cột `assessment` của `gap_assessment.csv` mới chỉ là phỏng đoán có căn cứ từ báo cáo, không phải xác nhận rằng code thiếu/chạy được.

## Tài liệu Codex tham khảo

- https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
- https://developers.openai.com/blog/skills-agents-sdk
- https://developers.openai.com/api/reference/cli

**Không bao gồm file thực thi cài đặt dependency hoặc thay đổi app.** Bộ kit chỉ phục vụ quy trình hướng dẫn, kiểm toán và phát triển sau đó bằng Codex.
