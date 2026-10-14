# Bước 4: Kiểm tra CI, Thử nghiệm Bắt lỗi & Checklist Hoàn thành

Tài liệu này hướng dẫn cách kiểm tra trạng thái CI trên GitHub, thử nghiệm tạo Pull Request lỗi để xác minh CI hoạt động, xử lý các sự cố phổ biến và danh sách kiểm tra hoàn thành.

---

## 1. Kiểm tra CI trên GitHub

1. Mở repository trên GitHub -> Chọn tab **Actions**.
2. Tìm workflow tương ứng với commit vừa push.
3. Bấm vào job để xem chi tiết từng bước thực thi (`Install uv`, `Ruff lint`, `mypy type check`, `pytest`).

---

## 2. Thử nghiệm CI Bắt Lỗi (Giả lập PR Lỗi)

Để kiểm chứng CI thực sự hoạt động và chặn code lỗi:

1. Tạo nhánh mới:
   ```bash
   git switch -c thu-loi-ci
   ```
2. Thêm một hàm bị lỗi kiểu dữ liệu vào cuối file `src/demo_ci/calculator.py`:
   ```python
   def double(x: int) -> int:
       return str(x * 2)  # Lỗi: Khai báo trả về int nhưng thực tế trả về str
   ```
3. Commit và bỏ qua pre-commit hook (để giả lập trường hợp ai đó lách kiểm tra ở máy cá nhân):
   ```bash
   git commit -am "Cố ý gây lỗi kiểu" --no-verify
   git push -u origin thu-loi-ci
   ```
4. Mở **Pull Request** trên GitHub.
5. **Kết quả kỳ vọng**: CI chạy và báo đỏ (Fail) ở bước `mypy type check`. PR sẽ hiển thị cảnh báo lỗi.
6. Sửa lại code cho đúng (`return x * 2`), commit và push lại -> CI tự động chuyển sang màu xanh (Passed).

---

## 3. Thêm Badge Trạng thái CI vào `README.md`

Thêm dòng sau vào đầu file `README.md` để hiển thị huy hiệu trạng thái của dự án (thay `<user>` bằng tài khoản GitHub):

```markdown
![CI](https://github.com/<user>/demo-ci/actions/workflows/ci.yml/badge.svg)
```

---

## 4. Xử lý Sự cố Thường gặp (Troubleshooting)

| Sự cố | Nguyên nhân & Cách khắc phục |
| :--- | :--- |
| **Tab Actions trống / Không chạy** | Kiểm tra thư mục `.github/workflows/` (phải có dấu `.`). Kiểm tra tên nhánh mặc định (`main` thay vì `master`). |
| **CI lỗi tại `uv sync --locked`** | Bạn vừa cập nhật `pyproject.toml` nhưng chưa cập nhật `uv.lock`. Chạy `uv lock` ở máy local rồi commit/push lại file `uv.lock`. |
| **Pre-commit không chặn lỗi / Báo command not found** | Môi trường terminal hoặc IDE chưa nhận `uv`. Chạy lại `uv run pre-commit install`. |
| **ModuleNotFoundError: No module named 'demo_ci'** | Chạy test bằng `uv run pytest` thay vì gọi trực tiếp `pytest`. |

---

## 5. Checklist Kiểm tra Hoàn thành

Đánh dấu vào các mục dưới đây sau khi thực hiện xong:

- [x] `uv --version` chạy thành công.
- [x] Dự án khởi tạo đúng cấu trúc với `pyproject.toml`, `uv.lock`, `.python-version`, `src/` và `tests/`.
- [x] Lệnh `uv run ruff check` báo không có lỗi (`All checks passed!`).
- [x] Lệnh `uv run ruff format --check` báo code đã đúng định dạng.
- [x] Lệnh `uv run mypy` báo `Success: no issues found`.
- [x] Lệnh `uv run pytest` chạy vượt qua toàn bộ unit tests.
- [x] `uv run pre-commit run --all-files` vượt qua toàn bộ các hooks.
- [ ] Mã nguồn và workflow `.github/workflows/ci.yml` đã push lên GitHub.
- [ ] Tab **Actions** trên GitHub chạy thành công (xanh) trên nhánh `main`.
- [ ] Thử nghiệm PR lỗi bị CI phát hiện thành công.