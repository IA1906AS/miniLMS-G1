"""miniLMS Application Factory & Defense in Depth Integration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, request

from lms_project_1 import schemas, services
from lms_project_1.audit import log_grade_change, setup_audit_logging
from lms_project_1.auth import BruteForceTracker, auth_bp
from lms_project_1.database import init_db
from lms_project_1.errors import NotFound, Unauthenticated, ValidationError, register_error_handlers
from lms_project_1.gate import setup_gate
from lms_project_1.guards import require_role
from lms_project_1.store import Store


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Application factory for miniLMS.

    - Validates mandatory JWT_SECRET (min 32 chars); raises RuntimeError if missing/too short.
    - Reloads seed.json on every call into fresh in-memory Store or PostgreSQL DB.
    - Config overrides environment variables.
    - Registers all 8 security layers and RBAC routes.
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

    # 2. Database connection & Data store initialization
    db_url = (config.get("DATABASE_URL") if config else None) or os.environ.get("DATABASE_URL")
    db_session = init_db(app, database_url=db_url) if db_url else None

    seed_path = (config.get("SEED_PATH") if config else None) or os.environ.get("SEED_PATH")
    store = Store(seed_path=seed_path, db_session=db_session)
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

    # 7. Register Auth Blueprint (Layer 1, 7: /auth/login, /auth/register, etc.)
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
    @require_role("INSTRUCTOR", "teacher")
    def put_course_grade(course_id: str, student_id: str) -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        # 1. Check course existence (404 môn)
        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        # 2. Check instructor assignment (403) - Defense in Depth if @require_role removed
        actor_role = str(actor.get("role", "")).upper()
        if actor_role not in ("INSTRUCTOR", "TEACHER") or course.get("instructorId") != actor.get(
            "id"
        ):
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

    @app.route("/users/<user_id>/role", methods=["PATCH"])
    @require_role("ADMIN", "admin")
    def patch_user_role(user_id: str) -> tuple[Response, int]:
        """Admin-only endpoint for role management (RBAC TC04, TC05)."""
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False)
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        new_role = schemas.validate_update_role_payload(body)
        target_user = store.get_user_by_id(user_id)
        if target_user is None:
            raise NotFound(f"User '{user_id}' not found")

        store.update_user_role(user_id, new_role)
        return (
            jsonify({"id": user_id, "role": new_role, "message": "Role updated successfully"}),
            200,
        )

    @app.route("/courses/<course_id>/assignments", methods=["POST"])
    @require_role("TEACHER", "teacher", "INSTRUCTOR", "instructor", "ADMIN", "admin")
    def post_course_assignment(course_id: str) -> tuple[Response, int]:
        """Teacher/Admin assignment creation endpoint (RBAC TC02, TC03)."""
        course = store.get_course_by_id(course_id)
        if course is None:
            raise NotFound(f"Course '{course_id}' not found")

        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False) or {}
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        title = str(body.get("title", "Untitled Assignment"))
        return jsonify({"courseId": course_id, "title": title, "status": "created"}), 201

    # 9. Home & Dashboard Endpoints
    @app.route("/home", methods=["GET"])
    @app.route("/api/home", methods=["GET"])
    def get_home() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        dashboard = services.get_home_dashboard(actor, store=store)
        return jsonify(dashboard), 200

    # 10. Account & Profile Endpoints
    @app.route("/account/profile", methods=["GET"])
    @app.route("/api/account/profile", methods=["GET"])
    def get_account_profile() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        account_data = services.get_account_data(actor, store=store)
        return jsonify(account_data), 200

    @app.route("/account/profile", methods=["PUT"])
    @app.route("/api/account/profile", methods=["PUT"])
    def put_account_profile() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False)
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        validated = schemas.validate_update_profile_payload(body)
        updated = services.update_profile(actor, validated, store=store)
        return jsonify({"message": "Cập nhật hồ sơ thành công", "profile": updated}), 200

    @app.route("/account/change-password", methods=["PUT"])
    @app.route("/api/account/change-password", methods=["PUT"])
    def put_account_password() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False)
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        old_pwd, new_pwd = schemas.validate_change_password_payload(body)
        services.change_password(actor, old_pwd, new_pwd, store=store)
        return jsonify({"message": "Đổi mật khẩu thành công"}), 200

    @app.route("/account/notifications", methods=["PUT"])
    @app.route("/api/account/notifications", methods=["PUT"])
    def put_account_notifications() -> tuple[Response, int]:
        actor = getattr(g, "actor", None)
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        try:
            body = request.get_json(silent=False)
        except Exception as exc:
            raise ValidationError("Malformed JSON") from exc

        validated = schemas.validate_notifications_payload(body)
        updated = services.update_notifications(actor, validated, store=store)
        return (
            jsonify({"message": "Cài đặt thông báo đã được lưu", "notifications": updated}),
            200,
        )

    # 11. Home Page & Public Course Catalog
    @app.route("/", methods=["GET"])
    def home_page() -> Any:
        from flask import send_from_directory

        frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
        if (frontend_dir / "index.html").is_file():
            return send_from_directory(str(frontend_dir), "index.html")
        templates_dir = Path(__file__).resolve().parent / "templates"
        if (templates_dir / "index.html").is_file():
            return send_from_directory(str(templates_dir), "index.html")
        return jsonify({"status": "miniLMS Web Portal Online"}), 200

    @app.route("/api/public/courses", methods=["GET"])
    def get_public_courses() -> tuple[Response, int]:
        courses_list = []
        for cid, c in store.courses.items():
            inst = store.get_user_by_id(c.get("instructorId", ""))
            inst_email = inst.get("email", "") if inst else ""
            inst_name = inst.get("fullName") or inst.get("full_name") or "" if inst else ""
            enrolled_count = sum(
                1 for (course_id, _), _ in store.enrollments.items() if course_id == cid
            )
            courses_list.append(
                {
                    "id": cid,
                    "title": c.get("title", ""),
                    "description": c.get("description", ""),
                    "instructorId": c.get("instructorId", ""),
                    "instructorEmail": inst_email,
                    "instructorName": inst_name,
                    "enrolledCount": enrolled_count,
                    "thumbnail": c.get("thumbnail", ""),
                    "durationHours": c.get("durationHours", 30),
                    "isFeatured": c.get("isFeatured", False),
                }
            )
        return jsonify(courses_list), 200

    @app.route("/api/admin/audit-logs", methods=["GET"])
    @require_role("ADMIN", "admin")
    def get_admin_audit_logs() -> tuple[Response, int]:
        log_path = app.config.get("AUDIT_LOG_PATH", "audit.log")
        from lms_project_1.audit import read_audit_logs

        records = read_audit_logs(limit=100, log_path=log_path)
        return jsonify(records), 200

    return app


def main() -> None:
    """Entry point for CLI script."""
    print("Hello from lms-project-1!")


# Setup `app` namespace aliases to support `import app...` and `flask --app app run`
current_pkg = sys.modules.get(__name__)
if current_pkg:
    sys.modules.setdefault("app", current_pkg)
    for mod_name in (
        "audit",
        "auth",
        "database",
        "errors",
        "gate",
        "guards",
        "models",
        "schemas",
        "services",
        "store",
    ):
        full_sub = f"lms_project_1.{mod_name}"
        if full_sub in sys.modules:
            sys.modules.setdefault(f"app.{mod_name}", sys.modules[full_sub])
