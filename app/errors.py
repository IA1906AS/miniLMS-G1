from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, error_code: str | None = None, status_code: int | None = None) -> None:
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.error_code)


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class InvalidCredentials(AppError):
    status_code = 401
    error_code = "INVALID_CREDENTIALS"


class Unauthenticated(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    error_code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class AccountLocked(AppError):
    status_code = 429
    error_code = "ACCOUNT_LOCKED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify({"error": err.error_code}), err.status_code

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": "NOT_FOUND"}), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({"error": "NOT_FOUND"}), 405

    @app.errorhandler(400)
    def handle_400(_err):
        return jsonify({"error": "VALIDATION_ERROR"}), 400

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        code = err.code or 500
        mapping = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "NOT_FOUND",
            429: "ACCOUNT_LOCKED",
        }
        return jsonify({"error": mapping.get(code, "INTERNAL_ERROR")}), code

    @app.errorhandler(Exception)
    def handle_unexpected_exception(_err: Exception):
        # Fail closed: never leak stack trace
        return jsonify({"error": "INTERNAL_ERROR"}), 500
