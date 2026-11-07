"""Layer 5: Input Validation & Schema Enforcement (schemas.py)."""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

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

    payload = dict(data)
    if "fullName" in payload and "full_name" not in payload:
        payload["full_name"] = payload.pop("fullName")
    elif "full_name" not in payload and "email" in payload and isinstance(payload["email"], str):
        local_part = payload["email"].split("@")[0].replace(".", " ").title()
        payload["full_name"] = local_part or "Học viên"

    allowed_keys = {"email", "password", "full_name", "role", "fullName"}
    required_keys = {"email", "password", "full_name"}
    data_keys = set(payload.keys())

    if not required_keys.issubset(data_keys):
        missing = required_keys - data_keys
        raise ValidationError(f"Missing required fields: {', '.join(sorted(missing))}")

    if not data_keys.issubset(allowed_keys):
        extra = data_keys - allowed_keys
        raise ValidationError(f"Unexpected extra fields: {', '.join(sorted(extra))}")

    email = validate_email_format(payload["email"])
    password = validate_password_strength(payload["password"])

    full_name = payload.get("full_name")
    if not isinstance(full_name, str) or not full_name.strip():
        raise ValidationError("full_name must be a non-empty string")
    if len(full_name.strip()) > 100:
        raise ValidationError("full_name cannot exceed 100 characters")

    role = payload.get("role", "guest")
    if not isinstance(role, str) or role.lower() not in VALID_ROLES:
        role = "student" if str(role).lower() in ("student", "sinh vien") else "guest"

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


def validate_update_profile_payload(data: Any) -> dict[str, str]:
    """Validate PUT /account/profile payload.

    Allows only a subset of: fullName, phone, bio, avatarUrl.
    Strictly forbids modifying id, email, role, or credentials (IDOR protection).
    """
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    allowed_keys = {"email", "fullName", "phone", "bio", "avatarUrl"}
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
            if key == "email":
                val_str = validate_email_format(val_str)
            if key == "phone" and len(val_str) > 30:
                raise ValidationError("'phone' exceeds maximum length of 30 characters")
            if key == "bio" and len(val_str) > 1000:
                raise ValidationError("'bio' exceeds maximum length of 1000 characters")
            if key == "avatarUrl" and len(val_str) > 1000:
                raise ValidationError("'avatarUrl' exceeds maximum length of 1000 characters")
            if key == "avatarUrl" and val_str:
                parsed = urlparse(val_str)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValidationError("'avatarUrl' must be an absolute HTTP(S) URL")
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


def validate_create_course_payload(data: Any) -> dict[str, Any]:
    """Validate course creation payload: {title, description?, durationHours?, instructorId?}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    if "title" not in data or not isinstance(data["title"], str) or not data["title"].strip():
        raise ValidationError("'title' must be a non-empty string")

    title = data["title"].strip()
    if len(title) > 200:
        raise ValidationError("'title' cannot exceed 200 characters")

    description = ""
    if "description" in data:
        if not isinstance(data["description"], str):
            raise ValidationError("'description' must be a string")
        description = data["description"].strip()
        if len(description) > 1000:
            raise ValidationError("'description' cannot exceed 1000 characters")

    duration_hours = 30
    if "durationHours" in data:
        val = data["durationHours"]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
            raise ValidationError("'durationHours' must be a positive number")
        duration_hours = int(val)

    result: dict[str, Any] = {
        "title": title,
        "description": description,
        "durationHours": duration_hours,
    }
    if "instructorId" in data and isinstance(data["instructorId"], str):
        result["instructorId"] = data["instructorId"].strip()

    return result


def validate_add_lesson_payload(data: Any) -> str:
    """Validate add lesson payload: strictly requires non-empty {title}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("'title' must be a non-empty string")

    title_str = title.strip()
    if len(title_str) > 200:
        raise ValidationError("'title' cannot exceed 200 characters")

    return title_str


def validate_create_assignment_payload(data: Any) -> dict[str, Any]:
    """Validate assignment creation payload: {title, description?, maxScore?}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("'title' must be a non-empty string")

    title_str = title.strip()
    if len(title_str) > 200:
        raise ValidationError("'title' cannot exceed 200 characters")

    description = ""
    if "description" in data:
        if not isinstance(data["description"], str):
            raise ValidationError("'description' must be a string")
        description = data["description"].strip()
        if len(description) > 1000:
            raise ValidationError("'description' cannot exceed 1000 characters")

    max_score = 10.0
    if "maxScore" in data:
        val = data["maxScore"]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0 or val > 100:
            raise ValidationError("'maxScore' must be a positive number up to 100")
        max_score = float(val)

    return {
        "title": title_str,
        "description": description,
        "maxScore": max_score,
    }


def validate_submit_assignment_payload(data: Any) -> str:
    """Validate assignment submission payload: {content}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("'content' must be a non-empty string")

    content_str = content.strip()
    if len(content_str) > 5000:
        raise ValidationError("'content' cannot exceed 5000 characters")

    return content_str


def validate_submission_request_payload(data: Any) -> dict[str, Any]:
    """Validate assignment submission request: {course_id, content, assignment_id?}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    course_id = data.get("course_id") or data.get("courseId")
    if not course_id or not isinstance(course_id, str) or not course_id.strip():
        raise ValidationError("'course_id' is required and must be a non-empty string")

    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("'content' must be a non-empty string")
    content_str = content.strip()
    if len(content_str) > 5000:
        raise ValidationError("'content' cannot exceed 5000 characters")

    assignment_id = data.get("assignment_id") or data.get("assignmentId")
    aid = str(assignment_id).strip() if assignment_id else None

    return {
        "course_id": str(course_id).strip(),
        "content": content_str,
        "assignment_id": aid,
    }


def validate_grade_submission_payload(data: Any, max_score: float = 10.0) -> tuple[float, str]:
    """Validate assignment grading payload: {score, feedback?}."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")

    score = data.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValidationError("'score' must be a numeric value")

    if math.isnan(score) or math.isinf(score) or score < 0.0 or score > max_score:
        raise ValidationError(f"'score' must be within [0, {max_score}]")

    feedback = ""
    if "feedback" in data:
        if not isinstance(data["feedback"], str):
            raise ValidationError("'feedback' must be a string")
        feedback = data["feedback"].strip()
        if len(feedback) > 1000:
            raise ValidationError("'feedback' cannot exceed 1000 characters")

    return float(score), feedback
