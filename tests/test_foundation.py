"""Acceptance and regression tests for Foundation phase FND-01 through FND-06."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask

from lms_project_1 import create_app
from lms_project_1.audit import log_event

TEST_SECRET = "foundation_test_secret_that_is_at_least_32_chars"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_app(tmp_path: Path, name: str = "foundation") -> Flask:
    return create_app(
        {
            "TESTING": True,
            "JWT_SECRET": TEST_SECRET,
            "AUDIT_LOG_PATH": str(tmp_path / f"{name}.log"),
        }
    )


def login(client: Any, email: str = "admin@lms.test") -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "Lms@2026"},
    )
    assert response.status_code == 200
    return str(response.get_json()["accessToken"])


def test_application_factory_instances_are_isolated(tmp_path: Path) -> None:
    first = make_app(tmp_path, "first")
    second = make_app(tmp_path, "second")

    assert first is not second
    assert first.config["STORE"] is not second.config["STORE"]
    assert first.config["BRUTE_FORCE_TRACKER"] is not second.config["BRUTE_FORCE_TRACKER"]


def test_spa_uses_shared_responsive_design_system(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/static/design-system.css"' in html
    assert 'class="es-skip-link"' in html
    assert 'id="main-content"' in html
    assert 'aria-label="Điều hướng chính"' in html
    assert 'aria-label="Điều hướng di động"' in html
    assert "isStudent()" in html
    assert "isInstructor()" in html
    assert "isAdmin()" in html


def test_design_system_asset_has_tokens_and_accessibility_guards(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()

    response = client.get("/static/design-system.css")

    assert response.status_code == 200
    css = response.get_data(as_text=True)
    assert "--es-color-brand-600" in css
    assert ".es-skip-link" in css
    assert ".es-mobile-nav" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_error_convention_hides_exception_and_sets_security_headers(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    @app.get("/foundation-test-error")
    def foundation_test_error() -> None:
        raise RuntimeError("database password should never reach the response")

    @app.get("/foundation-test-output")
    def foundation_test_output() -> dict[str, str]:
        return {"Password-Hash": "must-not-leak", "safe": "kept"}

    client = app.test_client()
    token = login(client)
    response = client.get(
        "/foundation-test-error",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert response.get_json() == {"error": "INTERNAL_ERROR"}
    assert "database password" not in response.get_data(as_text=True)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    sanitized = client.get(
        "/foundation-test-output",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sanitized.get_json() == {"safe": "kept"}


def test_audit_log_normalizes_and_removes_sensitive_extra_keys(tmp_path: Path) -> None:
    audit_path = tmp_path / "sanitized.log"

    log_event(
        audit_path,
        actor_id="u1",
        action="FOUNDATION_TEST",
        resource="/foundation",
        result="SUCCESS",
        passwordHash="must-not-log",
        accessToken="must-not-log",
        Authorization="Bearer must-not-log",
        safeField="kept",
    )

    entry = json.loads(audit_path.read_text(encoding="utf-8"))
    assert entry["safeField"] == "kept"
    assert "passwordHash" not in entry
    assert "accessToken" not in entry
    assert "Authorization" not in entry


def test_foundation_documents_are_present_and_traceable() -> None:
    expected_content = {
        "REQUIREMENTS_BASELINE.md": ("FND-01", "Student", "Teacher", "Admin"),
        "SYSTEM_ARCHITECTURE.md": ("FND-02", "create_app", "frontend/index.html"),
        "DEVELOPMENT_WORKFLOW.md": ("FND-04", "uv run", "branch protection"),
        "DESIGN_SYSTEM.md": ("FND-05", "Public", "Student", "Teacher", "Admin"),
        "API_CONVENTIONS.md": ("FND-06", "VALIDATION_ERROR", "INTERNAL_ERROR"),
    }
    for filename, markers in expected_content.items():
        content = (PROJECT_ROOT / "docs" / filename).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in content, f"{marker!r} missing from {filename}"
