"""Module tính toán và tiện ích mẫu cho dự án."""


def average(numbers: list[float]) -> float:
    """Tính giá trị trung bình của danh sách số thực."""
    if len(numbers) == 0:
        return 0.0
    return sum(numbers) / len(numbers)


def greet(name: str) -> str:
    """Tạo lời chào mừng."""
    return "Xin chào, " + name


def total_length(words: list[str]) -> int:
    """Tính tổng độ dài của danh sách các từ."""
    return sum(len(w) for w in words)
