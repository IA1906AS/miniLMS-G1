"""Layer 5: Input Validation & Schema Enforcement (schemas.py)."""

from __future__ import annotations

import math
from typing import Any

from lms_project_1.errors import ValidationError


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


def validate_update_profile_payload(data: Any) -> dict[str, str]:
    """Validate PUT /account/profile payload.

    Allows only a subset of: fullName, phone, bio, avatarUrl.
    Strictly forbids modifying id, email, role, or credentials (IDOR protection).
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    allowed_keys = {"fullName", "phone", "bio", "avatarUrl"}
    unknown_keys = set(data.keys()) - allowed_keys
    if unknown_keys:
        disallowed = ", ".join(sorted(unknown_keys))
        raise ValidationError(f"Disallowed fields in profile update: {disallowed}")

    result: dict[str, str] = {}
    for key in allowed_keys:
        if key in data:
            val = data[key]
            if not isinstance(val, str):
                raise ValidationError(f"Field '{key}' must be a string")
            val_str = val.strip()
            if key == "fullName" and len(val_str) > 120:
                raise ValidationError("'fullName' exceeds maximum length of 120 characters")
            if key == "phone" and len(val_str) > 30:
                raise ValidationError("'phone' exceeds maximum length of 30 characters")
            if key == "bio" and len(val_str) > 1000:
                raise ValidationError("'bio' exceeds maximum length of 1000 characters")
            if key == "avatarUrl" and len(val_str) > 1000:
                raise ValidationError("'avatarUrl' exceeds maximum length of 1000 characters")
            result[key] = val_str

    return result


def validate_change_password_payload(data: Any) -> tuple[str, str]:
    """Validate PUT /account/change-password payload.

    Requires exactly 'oldPassword' and 'newPassword'.
    Enforces minimum length of 8 characters on 'newPassword'.
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    if set(data.keys()) != {"oldPassword", "newPassword"}:
        raise ValidationError("Request body must contain only 'oldPassword' and 'newPassword'")

    old_pwd = data.get("oldPassword")
    new_pwd = data.get("newPassword")

    if not isinstance(old_pwd, str) or not old_pwd:
        raise ValidationError("'oldPassword' must be a non-empty string")
    if not isinstance(new_pwd, str) or not new_pwd:
        raise ValidationError("'newPassword' must be a non-empty string")

    if len(new_pwd) < 8:
        raise ValidationError("Mật khẩu mới phải có tối thiểu 8 ký tự")

    return old_pwd, new_pwd


def validate_notifications_payload(data: Any) -> dict[str, bool]:
    """Validate PUT /account/notifications payload."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    allowed_keys = {"emailNewCourses", "emailAssignments", "emailGradeUpdates"}
    unknown_keys = set(data.keys()) - allowed_keys
    if unknown_keys:
        raise ValidationError(f"Disallowed notification keys: {', '.join(sorted(unknown_keys))}")

    if not data:
        raise ValidationError("At least one notification preference must be provided")

    result: dict[str, bool] = {}
    for key, val in data.items():
        if not isinstance(val, bool):
            raise ValidationError(f"Notification setting '{key}' must be a boolean")
        result[key] = val

    return result
