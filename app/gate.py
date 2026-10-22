from __future__ import annotations

from flask import Flask, g, request

from app.auth import verify_access_token
from app.errors import Unauthenticated
from app.store import store

PUBLIC_ALLOWLIST: set[tuple[str, str]] = {
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/reset-password"),
    ("GET", "/"),
    ("GET", "/api/public/courses"),
}


def init_gate(app: Flask) -> None:
    @app.before_request
    def enforce_default_deny():
        path = request.path
        method = request.method.upper()

        if method == "GET" and (path.startswith("/static/") or path == "/favicon.ico"):
            return None

        clean_path = path.rstrip("/") or "/"
        if (method, clean_path) in PUBLIC_ALLOWLIST or (method, path) in PUBLIC_ALLOWLIST:
            return None

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise Unauthenticated()

        token = auth_header[len("Bearer ") :].strip()
        if not token:
            raise Unauthenticated()

        payload = verify_access_token(
            token=token,
            secret=app.config["JWT_SECRET"],
        )
        user_id = payload.get("sub")
        if not user_id or not isinstance(user_id, str):
            raise Unauthenticated()

        actor = store.get_public_actor(user_id)
        if not actor:
            raise Unauthenticated()

        g.current_actor = actor
        g.actor = actor
        return None
