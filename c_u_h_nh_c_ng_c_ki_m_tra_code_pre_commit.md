# Bước 2: Cấu hình Công cụ Linter, Type Checker, Test & Pre-commit

Tài liệu này hướng dẫn cấu hình toàn bộ các công cụ phát triển vào tệp `pyproject.toml`, thiết lập `.pre-commit-config.yaml` và tạo mã nguồn mẫu để thử nghiệm.

---

## 1. Cấu hình `pyproject.toml`

Mở file `pyproject.toml` ở thư mục gốc và cập nhật nội dung theo mẫu chuẩn dưới đây:

```toml
[project]
name = "demo-ci"
version = "0.1.0"
description = "Demo linter, type checker & CI với uv"
readme = "README.md"
requires-python = ">=3.13"
dependencies = []

[build-system]
requires = ["uv_build>=0.4.0,<0.5.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "mypy>=2.4.0",
    "pre-commit>=4.7.0",
    "pytest>=9.1.1",
    "ruff>=0.17.0",
]

# ==============================================================================
# Ruff Configuration (Linter & Formatter)
# ==============================================================================
[tool.ruff]
line-length = 88
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes (unused imports, undefined variables)
    "I",   # isort (import sorting)
    "B",   # flake8-bugbear (common bugs)
    "UP",  # pyupgrade (modern Python syntax)
    "SIM", # flake8-simplify
    "N",   # pep8-naming
]

[tool.ruff.format]
quote-style = "double"

# ==============================================================================
# Mypy Configuration (Static Type Checker)
# ==============================================================================
[tool.mypy]
python_version = "3.13"
strict = true
files = ["src", "tests"]

# ==============================================================================
# Pytest Configuration (Testing)
# ==============================================================================
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

---

## 2. Viết Mã Nguồn Mẫu & Unit Test

### 2.1. Mã nguồn module tính toán
Tạo file `src/demo_ci/calculator.py`:

```python
def average(numbers: list[float]) -> float:
    if len(numbers) == 0:
        return 0.0
    return sum(numbers) / len(numbers)


def greet(name: str) -> str:
    return "Xin chào, " + name


def total_length(words: list[str]) -> int:
    return sum(len(w) for w in words)
```

### 2.2. Đánh dấu gói hỗ trợ Type Hint
Tạo file rỗng `src/demo_ci/py.typed` để báo cho Mypy biết package này có chú thích kiểu đầy đủ.

### 2.3. Viết Unit Test
Tạo file `tests/test_calculator.py`:

```python
from demo_ci.calculator import average, greet


def test_average() -> None:
    assert average([1.0, 2.0, 3.0]) == 2.0


def test_average_empty() -> None:
    assert average([]) == 0.0


def test_greet() -> None:
    assert greet("An") == "Xin chào, An"
```

---

## 3. Chạy Kiểm tra Thủ công

Chạy thử bộ lệnh kiểm tra để đảm bảo code không còn lỗi:

```bash
# 1. Kiểm tra Linter
uv run ruff check

# 2. Kiểm tra Format
uv run ruff format --check

# 3. Kiểm tra Kiểu dữ liệu
uv run mypy

# 4. Chạy Unit Test
uv run pytest
```

---

## 4. Thiết lập Pre-commit Hooks

Pre-commit giúp tự động chạy Ruff và Mypy trước khi lệnh `git commit` được thực thi trên máy cá nhân.

### 4.1. Tạo `.pre-commit-config.yaml`
Tạo file `.pre-commit-config.yaml` tại thư mục gốc:

```yaml
# Dùng hook "local" với `uv run` để đảm bảo dùng đúng phiên bản đã khóa trong uv.lock
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]

      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]

      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: false
```

### 4.2. Cài đặt Git Hook và Chạy thử
```bash
# Cài đặt hook vào .git/hooks/
uv run pre-commit install

# Chạy thử nghiệm trên toàn bộ các file hiện có
uv run pre-commit run --all-files
```