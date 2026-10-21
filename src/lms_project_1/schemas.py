"""Layer 5: Input Validation & Schema Enforcement (schemas.py)."""

from __future__ import annotations

import math
import re
from typing import Any

from email_validator import EmailNotValidError, validate_email

from lms_project_1.errors import ValidationError

VALID_ROLES = {"guest", "student", "teacher", "admin", "instructor"}


def validate_email_format(email: Any) -> str:
    """Validate email address syntax using email-validator."""
    if not isinstance(email, str) or not email.strip():
        raise ValidationError("Email must be a non-empty string")
    try:
        validated = validate_email(email.strip(), check_deliverability=False, test_environment=True)
        return validated.normalized.lower()
    except EmailNotValidError as exc:
        raise ValidationError(f"Invalid email address: {exc}") from exc


def validate_password_strength(password: Any) -> str:
    """Validate password against security policy:

    - At least 8 characters long
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter
    - Contains at least one digit
    """
    if not isinstance(password, str):
        raise ValidationError("Password must be a string")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one digit")
    return password


def validate_register_payload(data: Any) -> dict[str, str]:
    """Validate registration payload: {email, password, full_name, role?}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    allowed_keys = {"email", "password", "full_name", "role"}
    required_keys = {"email", "password", "full_name"}
    data_keys = set(data.keys())

    if not required_keys.issubset(data_keys):
        missing = required_keys - data_keys
        raise ValidationError(f"Missing required fields: {', '.join(sorted(missing))}")

    if not data_keys.issubset(allowed_keys):
        extra = data_keys - allowed_keys
        raise ValidationError(f"Unexpected extra fields: {', '.join(sorted(extra))}")

    email = validate_email_format(data["email"])
    password = validate_password_strength(data["password"])

    full_name = data.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        raise ValidationError("full_name must be a non-empty string")
    if len(full_name.strip()) > 100:
        raise ValidationError("full_name cannot exceed 100 characters")

    role = data.get("role", "guest")
    if not isinstance(role, str) or role.lower() not in VALID_ROLES:
        raise ValidationError(f"Invalid role. Allowed roles: {', '.join(sorted(VALID_ROLES))}")

    return {
        "email": email,
        "password": password,
        "full_name": full_name.strip(),
        "role": role.lower(),
    }


def validate_forgot_password_payload(data: Any) -> str:
    """Validate forgot password payload: strictly {email}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    if set(data.keys()) != {"email"}:
        raise ValidationError("Request body must strictly contain 'email'")

    return validate_email_format(data["email"])


def validate_reset_password_payload(data: Any) -> tuple[str, str]:
    """Validate reset password payload: strictly {token, new_password}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    expected_keys = {"token", "new_password"}
    if set(data.keys()) != expected_keys:
        raise ValidationError("Request body must strictly contain 'token' and 'new_password'")

    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValidationError("Token must be a non-empty string")

    new_password = validate_password_strength(data.get("new_password"))
    return token.strip(), new_password


def validate_update_role_payload(data: Any) -> str:
    """Validate role update payload: strictly {role}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    if set(data.keys()) != {"role"}:
        raise ValidationError("Request body must strictly contain 'role'")

    role = data.get("role")
    if not isinstance(role, str) or role.lower() not in VALID_ROLES:
        raise ValidationError(f"Invalid role. Allowed roles: {', '.join(sorted(VALID_ROLES))}")

    return role.lower()


def validate_update_grade_payload(data: Any) -> float:
    """Validate PUT /courses/<course_id>/grades/<student_id> payload.

    Validation rules:
    - Body must be a JSON object.
    - Strictly disallow extra/unknown keys (e.g. 'courseId').
    - 'score' must be a numeric float or int within [0.0, 10.0].
    - Reject string numbers ("10"), booleans (true/false), null, NaN, and infinity.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    # Reject extra fields or missing 'score'
    if set(data.keys()) != {"score"}:
        raise ValidationError("Request body must contain only the 'score' field")

    score = data.get("score")

    # In Python, bool is a subclass of int, so explicitly check bool first
    if isinstance(score, bool):
        raise ValidationError("'score' must be a numeric value, not a boolean")

    if not isinstance(score, (int, float)):
        raise ValidationError("'score' must be a number")

    if math.isnan(score) or math.isinf(score):
        raise ValidationError("'score' must be a finite number")

    if score < 0.0 or score > 10.0:
        raise ValidationError("'score' must be within range [0, 10]")

    return float(score)


def validate_score_domain(score: Any) -> float:
    """Secondary domain validator used by services.py as Defense in Depth."""
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValidationError("'score' must be a numeric value")
    if math.isnan(score) or math.isinf(score) or score < 0.0 or score > 10.0:
        raise ValidationError("'score' must be within range [0, 10]")
    return float(score)
