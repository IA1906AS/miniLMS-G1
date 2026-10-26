# miniLMS (Group 1 - IAW301)

[![CI](https://github.com/IA1906AS/miniLMS-G1/actions/workflows/ci.yml/badge.svg)](https://github.com/IA1906AS/miniLMS-G1/actions/workflows/ci.yml)

Hệ thống quản trị học tập thu nhỏ (miniLMS) được xây dựng và chuẩn hóa quy trình phát triển bằng **Python** và **uv** (Astral).

---

## 1. Yêu cầu Hệ thống

- **Python**: `>= 3.13` (Mặc định `3.14`)
- **uv**: Trình quản lý gói và môi trường ảo siêu tốc ([Cài đặt uv](https://docs.astral.sh/uv/getting-started/installation/))
- **Git**: Quản lý phiên bản mã nguồn

---

## 2. Cài đặt Môi trường Phát triển

1. **Clone repository về máy:**
   ```bash
   git clone https://github.com/IA1906AS/miniLMS-G1.git
   cd miniLMS-G1
   ```

2. **Cài đặt các gói phụ thuộc (bao gồm nhóm dev):**
   ```bash
   uv sync
   ```

3. **Cài đặt Git Pre-commit Hooks:**
   ```bash
   uv run pre-commit install
   ```

---

## 3. Các Lệnh Kiểm tra Chất lượng Mã Nguồn (CI & Local)

Dự án áp dụng bộ công cụ nghiêm ngặt để đảm bảo chất lượng mã nguồn trước khi tích hợp:

| Mục tiêu | Lệnh thực thi | Mô tả |
| :--- | :--- | :--- |
| **Linting** | `uv run ruff check` | Kiểm tra lỗi cú pháp, quy ước code và imports (`--fix` để tự động sửa) |
| **Formatting** | `uv run ruff format --check` | Kiểm tra định dạng code chuẩn PEP 8 |
| **Type Checking** | `uv run mypy` | Kiểm tra kiểu dữ liệu tĩnh nghiêm ngặt (Strict mode) |
| **Unit Testing** | `uv run pytest` | Chạy bộ kiểm thử tự động |
| **Test Coverage** | `uv run pytest --cov` | Báo cáo tỷ lệ bao phủ kiểm thử (Test Coverage) |
| **SAST Security** | `uv run semgrep scan --config=.semgrep/minilms_rules.yaml --metrics=off` | Quét tĩnh phát hiện lỗ hổng bảo mật và quy tắc phòng thủ miniLMS |
| **Pre-commit Run** | `uv run pre-commit run --all-files` | Chạy thử nghiệm tất cả các hook trên toàn bộ tệp |

---

## 4. Cấu trúc Dự án (`src-layout`)

```text
IAW301-Project_Group_1/
├── .github/
│   └── workflows/
│       └── ci.yml             # Workflow GitHub Actions tự động kiểm tra CI
├── src/
│   └── lms_project_1/
│       ├── __init__.py        # Điểm khởi chạy chính của ứng dụng
│       ├── audit.py           # Module kiểm toán và log thao tác
│       ├── auth.py            # Module xác thực người dùng
│       ├── errors.py          # Định nghĩa lỗi hệ thống
│       ├── gate.py            # Cổng kiểm soát truy cập và bảo vệ API
│       ├── guards.py          # Ràng buộc điều kiện và kiểm tra quyền
│       ├── schemas.py         # Mô hình dữ liệu và lược đồ
│       ├── services.py        # Logic nghiệp vụ chính
│       └── store.py           # Quản lý lưu trữ và dữ liệu
├── tests/
│   └── test_basic.py          # Kiểm thử cơ bản hàm main
├── .gitignore                 # Danh sách các tệp/thư mục bỏ qua khi commit
├── .pre-commit-config.yaml    # Cấu hình Git Hook tự động chạy Ruff & Mypy
├── .python-version            # Khóa phiên bản Python (3.14)
├── pyproject.toml             # Cấu hình dự án, gói phụ thuộc và các công cụ
├── requirements.txt           # Danh sách các gói phụ thuộc
├── seed.json                  # Dữ liệu khởi tạo ban đầu
├── uv.lock                    # Khóa phiên bản dependencies chính xác
└── README.md                  # Tài liệu giới thiệu và hướng dẫn dự án
```

---

## 5. Quy trình Phát triển Tính năng Mới

1. Tạo nhánh mới từ `main` hoặc `master`:
   ```bash
   git switch -c feat/<ten-tinh-nang>
   ```
2. Phát triển tính năng trong thư mục `src/lms_project_1/`.
3. Viết đầy đủ unit tests bổ sung vào thư mục `tests/`.
4. Chạy kiểm tra toàn bộ trước khi commit:
   ```bash
   uv run ruff check --fix
   uv run ruff format
   uv run mypy
   uv run semgrep scan --config=.semgrep/minilms_rules.yaml --metrics=off
   uv run pytest --cov
   ```
5. Commit code (Pre-commit hook sẽ tự động chạy để kiểm tra lại một lần nữa).
6. Tạo Pull Request lên GitHub và kiểm tra trạng thái CI Actions.
