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
