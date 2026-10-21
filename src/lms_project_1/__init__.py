"""miniLMS Application Factory & Defense in Depth Integration."""

from __future__ import annotations

import os
import sys
from typing import Any

from flask import Flask, Response, g, jsonify, request

from lms_project_1 import schemas, services
from lms_project_1.audit import log_grade_change, setup_audit_logging
from lms_project_1.auth import BruteForceTracker, auth_bp
from lms_project_1.errors import NotFound, Unauthenticated, ValidationError, register_error_handlers
from lms_project_1.gate import setup_gate
from lms_project_1.guards import require_role
from lms_project_1.store import Store


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Application factory for miniLMS.

    - Validates mandatory JWT_SECRET (min 32 chars); raises RuntimeError if missing/too short.
    - Reloads seed.json on every call into fresh in-memory Store.
    - Config overrides environment variables.
    - Registers all 8 security layers.
    """
    app = Flask("lms_project_1")

    # 1. Config loading & JWT_SECRET verification (Layer 6 requirement)
    jwt_secret = (config.get("JWT_SECRET") if config else None) or os.environ.get("JWT_SECRET")
    if not jwt_secret or len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET is required and must be at least 32 characters long")

    app.config["JWT_SECRET"] = jwt_secret
    raw_ttl: Any = (config.get("TOKEN_TTL_SECONDS") if config else None) or os.environ.get(
        "TOKEN_TTL_SECONDS", 900
    )
    app.config["TOKEN_TTL_SECONDS"] = int(raw_ttl)
    app.config["AUDIT_LOG_PATH"] = (
        config.get("AUDIT_LOG_PATH") if config else None
    ) or os.environ.get("AUDIT_LOG_PATH", "audit.log")

    if config:
        for k, v in config.items():
            app.config[k] = v

    # 2. Data store initialization from seed.json
    seed_path = (config.get("SEED_PATH") if config else None) or os.environ.get("SEED_PATH")
    store = Store(seed_path=seed_path)
    app.store = store  # type: ignore[attr-defined]
    app.config["STORE"] = store
    services.set_store(store)

    # 3. Isolated brute-force tracker for login lockout (Layer 7)
    app.config["BRUTE_FORCE_TRACKER"] = BruteForceTracker()

    # 4. Layer 6: Centralized error handling and output sanitization
    register_error_handlers(app)

    # 5. Layer 2: Deny-by-default gatekeeper before_request hook
    setup_gate(app)

    # 6. Layer 8: Audit logging setup
    setup_audit_logging(app)

    # 7. Register Auth Blueprint (Layer 1, 7: POST /auth/login)
    app.register_blueprint(auth_bp)

    # 8. Register Protected Endpoints
    @app.route("/me", methods=["GET"])
    def get_me() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        return jsonify(
            {
                "id": actor["id"],
                "email": actor["email"],
                "role": actor["role"],
            }
        ), 200

    @app.route("/courses/<course_id>/grades", methods=["GET"])
    def get_course_grades(course_id: str) -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        # Services enforces 404 (môn) -> 403 (role/matrix)
        grades = services.get_grades(actor, course_id, store=store)
        return jsonify(grades), 200

    @app.route("/courses/<course_id>/grades/<student_id>", methods=["PUT"])
    @require_role("INSTRUCTOR")
    def put_course_grade(course_id: str, student_id: str) -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        # 1. Check course existence (404 môn)
        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        # 2. Check instructor assignment (403) - Defense in Depth if @require_role removed
        if actor.get("role") != "INSTRUCTOR" or course.get("instructorId") != actor.get("id"):
            from lms_project_1.errors import Forbidden

            raise Forbidden("Only the assigned instructor may update grades")

        # 3. Validate body schema (400)
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False)
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        score = schemas.validate_update_grade_payload(body)

        # 4. Check enrollment & update (404 ghi danh)
        result = services.update_grade(actor, course_id, student_id, score, store=store)
        old_score = result.pop("_old_score", None)

        # 5. Audit log grade update (Layer 8)
        if old_score is not None:
            log_grade_change(
                log_path=app.config.get("AUDIT_LOG_PATH", "audit.log"),
                actor_id=actor["id"],
                course_id=course_id,
                student_id=student_id,
                old_score=float(old_score),
                new_score=float(score),
            )

        return jsonify(result), 200

    return app


def main() -> None:
    """Entry point for CLI script."""
    print("Hello from lms-project-1!")


# Setup `app` namespace aliases to support `import app...` and `flask --app app run`
current_pkg = sys.modules.get(__name__)
if current_pkg:
    sys.modules.setdefault("app", current_pkg)
    for mod_name in ("audit", "auth", "errors", "gate", "guards", "schemas", "services", "store"):
        full_sub = f"lms_project_1.{mod_name}"
        if full_sub in sys.modules:
            sys.modules.setdefault(f"app.{mod_name}", sys.modules[full_sub])
