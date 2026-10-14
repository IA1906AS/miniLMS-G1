# Bước 1: Khởi tạo Dự án & Môi trường Phát triển với `uv`

Tài liệu này hướng dẫn cài đặt `uv`, tạo dự án theo chuẩn `src-layout` và thêm các gói phụ thuộc cho giai đoạn phát triển.

---

## 1. Kiểm tra / Cài đặt `uv`

`uv` là công cụ quản lý gói và môi trường ảo siêu tốc viết bằng Rust bởi Astral (nhóm phát triển Ruff).

### Cài đặt lệnh:
- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

> **Lưu ý:** Sau khi cài đặt, hãy đóng và mở lại Terminal để cập nhật biến môi trường `PATH`.

### Kiểm tra cài đặt thành công:
```bash
uv --version
```

---

## 2. Khởi tạo Dự án `demo-ci`

Khởi tạo dự án dạng thư viện (`--lib`) sử dụng phiên bản Python 3.13:

```bash
uv init --lib --python 3.13 demo-ci
cd demo-ci
```

### Ý nghĩa các thông số:
- `--lib`: Tạo cấu trúc `src-layout` (code chính nằm trong thư mục `src/`), giúp tránh lỗi import khi chạy test.
- `--python 3.13`: Ghim phiên bản Python 3.13 cho dự án. Nếu máy chưa có, `uv` sẽ tự động tải về.
- Lệnh `uv init` cũng tự động tạo repository Git (`git init`) và file `.gitignore`.

---

## 3. Cài đặt các Công cụ Phát triển (Dev Dependencies)

Thêm các công cụ linter, type checker, test framework và pre-commit vào nhóm `dev`:

```bash
uv add --dev ruff mypy pytest pre-commit
```

Lệnh này sẽ:
1. Tạo môi trường ảo `.venv/` (nếu chưa có) và cài đặt các gói vào đó.
2. Cập nhật nhóm `[dependency-groups]` trong file `pyproject.toml`.
3. Tạo / cập nhật file khóa `uv.lock` để ghim chính xác phiên bản các gói phụ thuộc.

---

## 4. Kiểm tra Môi trường

Chạy các lệnh kiểm tra công cụ đã sẵn sàng trong môi trường ảo qua `uv run`:

```bash
uv run ruff --version
uv run mypy --version
uv run pytest --version
uv run pre-commit --version
```

> **Mẹo:** Lệnh `uv run` sẽ tự động đồng bộ môi trường `.venv` với `uv.lock` trước khi thực thi lệnh.