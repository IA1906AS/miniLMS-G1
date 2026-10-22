from __future__ import annotations

from typing import Any

from app.errors import ValidationError


def validate_score_value(score: Any) -> float:
    # Disallow bool explicitly because in Python bool is a subclass of int
    if isinstance(score, bool):
        raise ValidationError()
    if not isinstance(score, (int, float)):
        raise ValidationError()
    val = float(score)
    if val < 0.0 or val > 10.0:
        raise ValidationError()
    return val


def validate_put_grade_body(data: Any) -> float:
    if not isinstance(data, dict):
        raise ValidationError()
    if set(data.keys()) != {"score"}:
        raise ValidationError()
    return validate_score_value(data["score"])


def validate_login_body(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise ValidationError()
    if set(data.keys()) != {"email", "password"}:
        raise ValidationError()
    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise ValidationError()
    if not email.strip() or not password:
        raise ValidationError()
    return email.strip(), password
