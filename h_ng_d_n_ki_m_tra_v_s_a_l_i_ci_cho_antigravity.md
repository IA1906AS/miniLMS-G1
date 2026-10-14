# Hướng dẫn Kiểm tra & Sửa lỗi GitHub Actions (Chuyển sang Tích Xanh)

Tài liệu này dành cho **Antigravity** (hoặc thành viên phát triển) để rà soát, phát hiện nguyên nhân CI báo đỏ (X) trên GitHub Actions và thực hiện quy trình khắc phục từng bước.

---

## 🚀 QUY TRÌNH QUICK-START (Thực hiện nhanh)

Chạy tổ hợp lệnh sau tại máy local trước khi push. Nếu lệnh này vượt qua, CI trên GitHub **chắc chắn sẽ xanh**:

```bash
uv run ruff check --fix && \
uv run ruff format && \
uv run mypy . && \
uv run pytest
```

---

## 🔍 BƯỚC 1: XÁC ĐỊNH BƯỚC LỖI TRÊN GITHUB ACTIONS

1. Truy cập Repository trên GitHub -> Tab **Actions**.
2. Chọn workflow lượt push gần nhất đang báo **Đỏ (Failed)**.
3. Nhấp vào Job (ví dụ: `Lint, type-check & test (Python 3.13)`).
4. Quan sát bước có dấu **X màu đỏ** và đối chiếu bên dưới:

---|---|---
`Install dependencies` | Lockfile không khớp hoặc thiếu file | Xem Mục 2.1
`Ruff lint` | Dư thừa/thiếu import, lỗi syntax | Xem Mục 2.2
`Ruff format check` | Code chưa định dạng đúng chuẩn | Xem Mục 2.3
`mypy type check` | Thiếu hoặc sai kiểu dữ liệu (Type hint) | Xem Mục 2.4
`pytest unit tests` | Code chạy sai logic hoặc test hỏng | Xem Mục 2.5

---

## 🛠️ BƯỚC 2: CÁC NGUYÊN NHÂN PHỔ BIẾN & CÁCH KHẮC PHỤC

### 2.1. Lỗi tại bước `Install dependencies` (`uv sync --locked`)
* **Nguyên nhân:** File `pyproject.toml` đã bị chỉnh sửa nhưng file `uv.lock` chưa được cập nhật hoặc quên commit `uv.lock`.
* **Cách sửa:**
  ```bash
  # 1. Cập nhật lại file khóa
  uv lock

  # 2. Đồng bộ kiểm tra lại local
  uv sync

  # 3. Commit lại uv.lock
  git add uv.lock pyproject.toml
  git commit -m "fix(ci): update uv.lock to match pyproject.toml"
  ```

---

### 2.2. Lỗi tại bước `Ruff lint`
* **Nguyên nhân:** Có import không sử dụng, sai thứ tự import, hoặc dùng cú pháp chưa tối ưu.
* **Cách sửa:**
  ```bash
  # Tự động sửa các lỗi linter sửa được
  uv run ruff check --fix
  ```
  *Nếu vẫn còn lỗi không tự sửa được, hãy mở terminal xem file & dòng cụ thể mà Ruff báo để sửa thủ công.*

---

### 2.3. Lỗi tại bước `Ruff format check`
* **Nguyên nhân:** Định dạng dấu ngoặc, thụt lề hoặc dấu nháy không tuân thủ quy chuẩn của Ruff.
* **Cách sửa:**
  ```bash
  # Tự động định dạng lại toàn bộ mã nguồn
  uv run ruff format
  ```

---

## 2.4. Lỗi tại bước `mypy type check`
* **Nguyên nhân:** Khai báo kiểu dữ liệu sai, thiếu Type Hint ở các tham số / giá trị trả về của hàm, hoặc gọi hàm thiếu type context.
* **Cách kiểm tra:**
  ```bash
  uv run mypy .
  ```
* **Ví dụ các lỗi thường gặp & cách sửa:**

  * **Lỗi thiếu type parameter:**
    * ❌ `def process(data: list) -> None:`
    * ✅ `def process(data: list[str]) -> None:`

  * **Lỗi trả về sai kiểu (Incompatible return type):**
    * ❌ `def add(a: int, b: int) -> int: return str(a + b)`
    * ✅ `def add(a: int, b: int) -> int: return a + b`

  * **Lỗi biến có thể nhận `None` (Item "None" of "Optional[...]"):**
    * ❌ `return user.name` (nếu `user` có thể là `None`)
    * ✅ `if user is None: return ""` \ `return user.name`

---

### 2.5. Lỗi tại bước `pytest unit tests`
* **Nguyên nhân:** Logic trong mã nguồn bị sai khiến `assert` thất bại.
* **Cách sửa:**
  ```bash
  # Chạy test chi tiết với flag hiện traceback
  uv run pytest -vv
  ```
  Sửa lại logic trong hàm hoặc cập nhật file test trong thư mục `tests/`.

---

## 📦 BƯỚC 3: QUY TRÌNH COMMIT VÀ PUSH SỬA LỖI

Sau khi đã chạy thành công bộ 4 lệnh ở **Quick-Start**, Antigravity thực hiện push code lên GitHub:

```bash
# 1. Kiểm tra các file đã thay đổi
git status

# 2. Chạy pre-commit trên toàn bộ file
uv run pre-commit run --all-files

# 3. Add và Commit
git add .
git commit -m "fix(ci): resolved linter, type-check and formatting issues"

# 4. Push lên GitHub
git push origin main
```

---

## 📝 CHECKLIST DÀNH CHO ANTIGRAVITY TRƯỚC KHIN PUSH
- [ ] Đã chạy `uv lock` (nếu có chỉnh sửa thư viện trong `pyproject.toml`).
- [ ] Đã chạy `uv run ruff check --fix`.
- [ ] Đã chạy `uv run ruff format`.
- [ ] Lệnh `uv run mypy .` trả về `Success: no issues found`.
- [ ] Lệnh `uv run pytest` trả về `passed`.
- [ ] File `uv.lock` đã được `git add` và nằm trong commit.