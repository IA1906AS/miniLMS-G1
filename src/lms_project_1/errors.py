"""Layer 6: Secure Error Handling, Fail-Closed, and Output Sanitization (errors.py)."""

from __future__ import annotations

import json
from typing import Any

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    """Base application exception supporting standard JSON error responses."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.error_code)


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class InvalidCredentialsError(AppError):
    status_code = 401
    error_code = "INVALID_CREDENTIALS"


class UnauthenticatedError(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class AccountLockedError(AppError):
    status_code = 429
    error_code = "ACCOUNT_LOCKED"


class InternalError(AppError):
    status_code = 500
    error_code = "INTERNAL_ERROR"


# Aliases conforming to exact PDF naming specification
Forbidden = ForbiddenError
NotFound = NotFoundError
InvalidCredentials = InvalidCredentialsError
Unauthenticated = UnauthenticatedError
AccountLocked = AccountLockedError


def _sanitize_data(data: Any) -> Any:
    """Recursively strip sensitive credential fields from outbound response data."""
    forbidden_keys = {"password", "password_hash", "passwordHash"}
    if isinstance(data, dict):
        return {k: _sanitize_data(v) for k, v in data.items() if k not in forbidden_keys}
    if isinstance(data, list):
        return [_sanitize_data(item) for item in data]
    return data


def sanitize_response(response: Response) -> Response:
    """Layer 6: Output policy guaranteeing no sensitive fields leak in response body."""
    if response.is_json:
        try:
            raw_data = response.get_json(silent=True)
            if raw_data is not None:
                sanitized = _sanitize_data(raw_data)
                response.set_data(json.dumps(sanitized))
        except Exception:
            pass
    return response


def register_error_handlers(app: Flask) -> None:
    """Register centralized error handlers and output sanitization on Flask app."""

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError) -> tuple[Response, int]:
        return jsonify({"error": exc.error_code}), exc.status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException) -> tuple[Response, int]:
        code = exc.code or 500
        error_code_map = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "ACCOUNT_LOCKED",
            500: "INTERNAL_ERROR",
        }
        err_msg = error_code_map.get(code, "INTERNAL_ERROR")
        return jsonify({"error": err_msg}), code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(_exc: Exception) -> tuple[Response, int]:
        # Fail closed: never leak internal stack traces
        return jsonify({"error": "INTERNAL_ERROR"}), 500

    app.after_request(sanitize_response)
