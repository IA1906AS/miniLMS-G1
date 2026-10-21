"""Layer 8: Audit Logging for Grade Updates & 403 Forbidden Events (audit.py)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, current_app, g, request


def log_event(
    log_path: str | Path,
    actor_id: str,
    action: str,
    resource: str,
    result: str,
    old_score: float | None = None,
    new_score: float | None = None,
    **extra: Any,
) -> None:
    """Append a single JSON log line to AUDIT_LOG_PATH.

    Required keys: ts, actorId, action, resource, result.
    If score is updated, includes oldScore and newScore.
    Never logs passwords or tokens.
    """
    entry: dict[str, Any] = {
        "ts": int(time.time()),
        "actorId": actor_id,
        "action": action,
        "resource": resource,
        "result": result,
    }

    if old_score is not None:
        entry["oldScore"] = old_score
    if new_score is not None:
        entry["newScore"] = new_score

    # Exclude any sensitive keys
    forbidden_keys = {"password", "token", "password_hash", "passwordHash", "secret"}
    for k, v in extra.items():
        if k.lower() not in forbidden_keys:
            entry[k] = v

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def log_grade_change(
    log_path: str | Path,
    actor_id: str,
    course_id: str,
    student_id: str,
    old_score: float,
    new_score: float,
) -> None:
    """Log successful score modification."""
    resource = f"/courses/{course_id}/grades/{student_id}"
    log_event(
        log_path=log_path,
        actor_id=actor_id,
        action="UPDATE_GRADE",
        resource=resource,
        result="SUCCESS",
        old_score=old_score,
        new_score=new_score,
    )


def log_forbidden_event(
    log_path: str | Path,
    actor_id: str,
    resource: str,
    action: str = "ACCESS",
) -> None:
    """Log 403 FORBIDDEN event."""
    log_event(
        log_path=log_path,
        actor_id=actor_id,
        action=action,
        resource=resource,
        result="FORBIDDEN",
    )


def setup_audit_logging(app: Flask) -> None:
    """Hook audit logging into the Flask application."""

    @app.after_request
    def record_audit_logs(response: Response) -> Response:
        log_path = current_app.config.get("AUDIT_LOG_PATH", "audit.log")
        actor = getattr(g, "actor", None)
        actor_id = actor.get("id", "anonymous") if isinstance(actor, dict) else "anonymous"

        # Log every 403 Forbidden event
        if response.status_code == 403:
            log_forbidden_event(
                log_path=log_path,
                actor_id=actor_id,
                resource=request.path,
                action=request.method,
            )

        # Successful grade change audit logging is triggered directly on PUT 200
        # or if g._grade_change is set
        grade_info = getattr(g, "_audit_grade_change", None)
        if grade_info and response.status_code == 200:
            log_grade_change(
                log_path=log_path,
                actor_id=actor_id,
                course_id=grade_info["courseId"],
                student_id=grade_info["studentId"],
                old_score=grade_info["oldScore"],
                new_score=grade_info["newScore"],
            )

        return response
