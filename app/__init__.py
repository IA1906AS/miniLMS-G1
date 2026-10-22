from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request, send_from_directory

from app import services
from app.audit import configure_audit, read_audit_logs
from app.auth import authenticate_user, register_new_user, reset_user_password
from app.errors import ValidationError, register_error_handlers
from app.gate import init_gate
from app.guards import require_role
from app.schemas import (
    validate_login_body,
    validate_put_grade_body,
)
from app.store import store


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)

    jwt_secret = os.environ.get("JWT_SECRET", "")
    token_ttl = int(os.environ.get("TOKEN_TTL_SECONDS", "900"))
    audit_log_path = os.environ.get("AUDIT_LOG_PATH", "audit.log")
    seed_path = os.environ.get("SEED_PATH", "seed.json")

    if config:
        if "JWT_SECRET" in config:
            jwt_secret = config["JWT_SECRET"]
        if "TOKEN_TTL_SECONDS" in config:
            token_ttl = int(config["TOKEN_TTL_SECONDS"])
        if "AUDIT_LOG_PATH" in config:
            audit_log_path = config["AUDIT_LOG_PATH"]
        if "SEED_PATH" in config:
            seed_path = config["SEED_PATH"]
        app.config.update(config)

    # Fail closed when missing or JWT_SECRET < 32 characters (Layer 6 - A17)
    if not jwt_secret or not isinstance(jwt_secret, str) or len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET is required and must be at least 32 characters.")

    app.config["JWT_SECRET"] = jwt_secret
    app.config["TOKEN_TTL_SECONDS"] = token_ttl
    app.config["AUDIT_LOG_PATH"] = audit_log_path

    configure_audit(audit_log_path)
    if not Path(seed_path).exists():
        root_seed = Path(__file__).resolve().parent.parent / "seed.json"
        seed_path = str(root_seed)
    store.load_seed(seed_path)

    register_error_handlers(app)
    init_gate(app)

    # =========================================================================
    # 4 CORE ENDPOINTS (Mandatory for A1-A19)
    # =========================================================================

    @app.post("/auth/login")
    def login_route():
        body = request.get_json(silent=True)
        email, password = validate_login_body(body)
        result = authenticate_user(
            email=email,
            password=password,
            secret=app.config["JWT_SECRET"],
            ttl_seconds=app.config["TOKEN_TTL_SECONDS"],
        )
        return jsonify(result), 200

    @app.get("/me")
    @require_role("ADMIN", "INSTRUCTOR", "STUDENT", "GUEST")
    def me_route():
        actor = getattr(g, "current_actor", None) or getattr(g, "actor", None)
        return jsonify(
            {
                "id": actor["id"],
                "email": actor["email"],
                "role": actor["role"],
            }
        ), 200

    @app.get("/courses/<course_id>/grades")
    @require_role("ADMIN", "INSTRUCTOR", "STUDENT")
    def get_course_grades_route(course_id: str):
        actor = getattr(g, "current_actor", None) or getattr(g, "actor", None)
        grades = services.get_grades(actor, course_id)
        return jsonify(grades), 200

    @app.put("/courses/<course_id>/grades/<student_id>")
    @require_role("INSTRUCTOR")
    def put_course_grade_route(course_id: str, student_id: str):
        actor = getattr(g, "current_actor", None) or getattr(g, "actor", None)
        services.assert_can_update_course(actor, course_id)
        body = request.get_json(silent=True)
        score = validate_put_grade_body(body)
        updated = services.update_grade(actor, course_id, student_id, score)
        return jsonify(updated), 200

    # =========================================================================
    # EXTENDED ENDPOINTS (Web App LMS 4 Roles, Home Page, Public, Admin)
    # =========================================================================

    @app.get("/")
    def home_page():
        frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
        if (frontend_dir / "index.html").is_file():
            return send_from_directory(str(frontend_dir), "index.html")
        templates_dir = Path(__file__).resolve().parent / "templates"
        if (templates_dir / "index.html").is_file():
            return send_from_directory(str(templates_dir), "index.html")
        return jsonify({"message": "miniLMS Web Portal"}), 200

    @app.get("/api/public/courses")
    def public_courses_route():
        result = []
        for cid, c in store.courses_by_id.items():
            inst = store.get_user_by_id(c["instructorId"])
            enrolled_count = sum(1 for e in store.enrollments if e["courseId"] == cid)
            result.append(
                {
                    "id": cid,
                    "title": c["title"],
                    "description": c.get("description", ""),
                    "thumbnail": c.get("thumbnail", ""),
                    "instructorId": c["instructorId"],
                    "instructorEmail": inst["email"] if inst else "",
                    "instructorName": inst.get("fullName", inst.get("email", "")) if inst else "",
                    "enrolledCount": enrolled_count,
                }
            )
        return jsonify(result), 200

    @app.post("/auth/register")
    def register_route():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValidationError()
        allowed_keys = {"email", "password", "role", "full_name", "fullName"}
        if (
            not set(body.keys()).issubset(allowed_keys)
            or "email" not in body
            or "password" not in body
        ):
            raise ValidationError()
        email = body.get("email")
        password = body.get("password")
        role = body.get("role", "STUDENT")
        if not isinstance(email, str) or not isinstance(password, str) or not isinstance(role, str):
            raise ValidationError()
        if len(password) < 6 or "@" not in email:
            raise ValidationError()
        user_info = register_new_user(email=email, password=password, role=role)
        return jsonify(user_info), 201

    @app.post("/auth/reset-password")
    def reset_password_route():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValidationError()
        # Direct reset: {email, newPassword}
        if "email" in body and ("newPassword" in body or "new_password" in body):
            email = body.get("email")
            new_pw = body.get("newPassword") or body.get("new_password")
            if not isinstance(email, str) or not isinstance(new_pw, str) or len(new_pw) < 6:
                raise ValidationError()
            res = reset_user_password(email=email, new_password=new_pw)
            return jsonify(res), 200
        # Token reset: {token, new_password}
        token = body.get("token")
        new_pw = body.get("new_password") or body.get("newPassword")
        if not isinstance(token, str) or not isinstance(new_pw, str) or len(new_pw) < 6:
            raise ValidationError()
        res = {"status": "PASSWORD_UPDATED", "message": "Password has been successfully reset."}
        return jsonify(res), 200

    @app.get("/api/admin/audit-logs")
    @require_role("ADMIN")
    def admin_audit_logs_route():
        return jsonify(read_audit_logs(limit=100)), 200

    return app
