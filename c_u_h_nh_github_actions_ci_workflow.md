# Bước 3: Đưa Dự án lên GitHub và Cấu hình CI với GitHub Actions

Tài liệu này hướng dẫn đưa mã nguồn lên GitHub repository và tự động hóa quy trình kiểm tra mã nguồn (CI) bằng GitHub Actions.

---

## 1. Commit Mã Nguồn Ban Đầu

Trước khi push, kiểm tra chắc chắn đã có tệp `uv.lock` và không đưa thư mục `.venv/` vào Git.

```bash
git add -A
git status
git commit -m "Khởi tạo dự án với uv, ruff, mypy, pytest, pre-commit"
git branch -M main
```

---

## 2. Tạo Repository trên GitHub & Push Code

1. Truy cập [GitHub](https://github.com) và tạo một repository mới tên `demo-ci` (không chọn khởi tạo README / .gitignore).
2. Kết nối và push code từ máy cá nhân (thay `<user>` bằng tài khoản GitHub của bạn):

```bash
git remote add origin https://github.com/<user>/demo-ci.git
git push -u origin main
```

*(Hoặc dùng GitHub CLI nếu đã cài đặt: `gh repo create demo-ci --public --source=. --remote=origin --push`)*

---

## 3. Tạo File Workflow GitHub Actions

Tạo thư mục `.github/workflows/` và tạo file `ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  quality:
    name: Lint, type-check & test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.13", "3.14"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v9
        with:
          enable-cache: true
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --locked --all-extras --dev

      - name: Ruff lint
        run: uv run ruff check --output-format=github

      - name: Ruff format check
        run: uv run ruff format --check --diff

      - name: mypy type check
        run: uv run mypy

      - name: pytest unit tests
        run: uv run pytest
```

---

## 4. Giải thích Workflow CI

| Khối lệnh / Tham số | Chức năng |
| :--- | :--- |
| `on: [push, pull_request]` | Tự động kích hoạt khi push hoặc mở PR vào nhánh `main`. |
| `astral-sh/setup-uv@v9` | Action chính thức để cài đặt `uv` nhanh chóng và tự động cache dependencies. |
| `uv sync --locked` | Đảm bảo cài đặt chính xác các gói theo `uv.lock`, báo lỗi nếu `pyproject.toml` bị lệch so với lockfile. |
| `--output-format=github` | Định dạng thông báo lỗi của Ruff để hiển thị trực tiếp thành ghi chú trên dòng code trong giao diện GitHub. |
| `ruff format --check --diff` | Báo lỗi nếu code chưa được format đúng quy chuẩn mà không tự sửa file trên máy chủ CI. |

---

## 5. Commit và Push Workflow CI

```bash
git add .github/workflows/ci.yml
git commit -m "Thêm workflow CI kiểm tra tự động"
git push
```