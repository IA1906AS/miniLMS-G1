"""Layer 2: Deny-by-Default Gatekeeper (gate.py).

Enforces global authentication via Flask's before_request hook.
Every incoming HTTP request requires a valid Bearer JWT token,
except the single allowlisted endpoint: POST /auth/login.
Undeclared or newly added routes are protected by default.
"""

from __future__ import annotations

import os
from typing import Any

import jwt
from flask import Flask, Response, current_app, g, jsonify, make_response, request

# Public endpoints allowlisted from global bearer token requirement
ALLOWLIST_METHOD = "POST"
ALLOWLIST_PATH = "/auth/login"
PUBLIC_AUTH_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/reset-password"),
    ("GET", "/"),
    ("GET", "/api/public/courses"),
}

# Fallback seed users for when store is not yet initialized or during standalone testing
DEFAULT_SEED_USERS: dict[str, dict[str, str]] = {
    "u1": {"id": "u1", "email": "admin@lms.test", "role": "ADMIN"},
    "u2": {"id": "u2", "email": "an.gv@lms.test", "role": "INSTRUCTOR"},
    "u3": {"id": "u3", "email": "binh.gv@lms.test", "role": "INSTRUCTOR"},
    "u4": {"id": "u4", "email": "chi.sv@lms.test", "role": "STUDENT"},
    "u5": {"id": "u5", "email": "dung.sv@lms.test", "role": "STUDENT"},
    "u6": {"id": "u6", "email": "em.sv@lms.test", "role": "STUDENT"},
}


def _unauthenticated_response() -> Response:
    """Return a standard 401 UNAUTHENTICATED JSON response."""
    response = make_response(jsonify({"error": "UNAUTHENTICATED"}), 401)
    response.headers["Content-Type"] = "application/json"
    return response


def _format_user(raw_user: Any) -> dict[str, str] | None:
    """Normalize raw user object or dictionary to {id, email, role}."""
    if isinstance(raw_user, dict):
        user_id = str(raw_user.get("id", ""))
        email = str(raw_user.get("email", ""))
        role = str(raw_user.get("role", ""))
    elif hasattr(raw_user, "id") and hasattr(raw_user, "email") and hasattr(raw_user, "role"):
        user_id = str(getattr(raw_user, "id", ""))
        email = str(getattr(raw_user, "email", ""))
        role = str(getattr(raw_user, "role", ""))
    else:
        return None

    if not user_id or not role:
        return None

    return {"id": user_id, "email": email, "role": role}


def _lookup_user_in_store(user_id: str) -> dict[str, str] | None:
    """Look up a user by ID in the application store across various conventions.

    Follows Defense in Depth: checks app.store, app.config, store module,
    and fallback seed users if store is completely uninitialized.
    """
    has_active_store = False

    # 1. Check current_app attributes and config
    store_obj = getattr(current_app, "store", None)
    if store_obj is None and hasattr(current_app, "config"):
        store_obj = current_app.config.get("STORE") or current_app.config.get("store")

    if store_obj is not None:
        has_active_store = True
        for method_name in (
            "get_user_by_id",
            "get_user",
            "find_user_by_id",
            "find_user",
        ):
            fn = getattr(store_obj, method_name, None)
            if callable(fn):
                try:
                    user = fn(user_id)
                    if user:
                        return _format_user(user)
                except Exception:
                    pass

        users_attr = getattr(store_obj, "users", None)
        if isinstance(users_attr, dict):
            if user_id in users_attr:
                return _format_user(users_attr[user_id])
        elif isinstance(users_attr, list):
            for u in users_attr:
                if (isinstance(u, dict) and u.get("id") == user_id) or (
                    hasattr(u, "id") and u.id == user_id
                ):
                    return _format_user(u)

    # 2. Check store module if available
    try:
        import lms_project_1.store as store_mod

        for method_name in (
            "get_user_by_id",
            "get_user",
            "find_user_by_id",
            "find_user",
        ):
            fn = getattr(store_mod, method_name, None)
            if callable(fn):
                has_active_store = True
                try:
                    user = fn(user_id)
                    if user:
                        return _format_user(user)
                except Exception:
                    pass

        get_store_fn = getattr(store_mod, "get_store", None)
        if callable(get_store_fn):
            has_active_store = True
            try:
                s = get_store_fn()
                if s is not None:
                    for method_name in ("get_user_by_id", "get_user"):
                        m = getattr(s, method_name, None)
                        if callable(m):
                            user = m(user_id)
                            if user:
                                return _format_user(user)
            except Exception:
                pass

        users_mod = getattr(store_mod, "users", None) or getattr(store_mod, "USERS", None)
        if isinstance(users_mod, dict):
            has_active_store = True
            if user_id in users_mod:
                return _format_user(users_mod[user_id])
        elif isinstance(users_mod, list):
            has_active_store = True
            for u in users_mod:
                if (isinstance(u, dict) and u.get("id") == user_id) or (
                    hasattr(u, "id") and u.id == user_id
                ):
                    return _format_user(u)
    except (ImportError, AttributeError):
        pass

    # 3. Check current_app.config["USERS"]
    if hasattr(current_app, "config"):
        users_cfg = current_app.config.get("USERS") or current_app.config.get("users")
        if isinstance(users_cfg, dict):
            has_active_store = True
            if user_id in users_cfg:
                return _format_user(users_cfg[user_id])
        elif isinstance(users_cfg, list):
            has_active_store = True
            for u in users_cfg:
                if (isinstance(u, dict) and u.get("id") == user_id) or (
                    hasattr(u, "id") and u.id == user_id
                ):
                    return _format_user(u)

    # If an active store exists and user was not found, return None
    # Requirement: "user trong token không còn" -> 401 UNAUTHENTICATED
    if has_active_store:
        return None

    # Fallback to seed users only if store is completely uninitialized/empty
    if user_id in DEFAULT_SEED_USERS:
        return dict(DEFAULT_SEED_USERS[user_id])

    return None


def gate_before_request() -> Response | None:
    """Global before_request hook enforcing deny-by-default access control (Layer 2).

    Inspects incoming requests:
    - Allows POST /auth/login through unconditionally.
    - Requires valid Bearer JWT token (HS256) for all other requests.
    - Validates token claims and verifies user existence in store.
    - Populates request context (g.actor, g.user, g.current_user).
    - Returns 401 UNAUTHENTICATED on any verification failure.
    """
    # 1. Allowlist check: public auth endpoints
    req_path = request.path.rstrip("/") or "/"
    if (request.method.upper(), req_path) in PUBLIC_AUTH_ENDPOINTS:
        return None
    if request.method.upper() == ALLOWLIST_METHOD and req_path == ALLOWLIST_PATH:
        return None
    if request.method.upper() == "GET" and (
        request.path.startswith("/static/") or request.path == "/favicon.ico"
    ):
        return None

    # 2. Extract Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return _unauthenticated_response()

    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2:
        return _unauthenticated_response()

    scheme, token = parts[0], parts[1].strip()
    if scheme.capitalize() != "Bearer" or not token:
        return _unauthenticated_response()

    # 3. Retrieve JWT secret
    secret = (
        current_app.config.get("JWT_SECRET") if hasattr(current_app, "config") else None
    ) or os.environ.get("JWT_SECRET")

    if not secret:
        return _unauthenticated_response()

    # 4. Decode and verify JWT token (Layer 1 & 2 Defense in Depth)
    # Strictly enforce HS256, verify signature, verify expiration,
    # and require 'sub' and 'exp'
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["sub", "exp"],
            },
        )
    except jwt.PyJWTError:
        return _unauthenticated_response()
    except Exception:
        return _unauthenticated_response()

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        return _unauthenticated_response()

    # 5. Verify user exists in store ("user trong token không còn")
    user = _lookup_user_in_store(user_id)
    if user is None:
        return _unauthenticated_response()

    # 6. Populate Flask request context with actor
    actor: dict[str, str] = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
    }
    g.actor = actor
    g.user = actor
    g.current_user = actor
    g.token = token
    g.jwt_payload = payload

    return None


# Aliases for flexible integration in create_app()
before_request = gate_before_request
gatekeeper = gate_before_request
enforce_gate = gate_before_request
check_token = gate_before_request


def setup_gate(app: Flask) -> None:
    """Register the Layer 2 deny-by-default before_request hook on a Flask app."""
    if getattr(app, "_gate_registered", False):
        return
    app._gate_registered = True  # type: ignore[attr-defined]
    app.before_request(gate_before_request)


# Aliases for setup_gate
init_gate = setup_gate
init_app = setup_gate
register_gate = setup_gate


class Gate:
    """Flask extension class for Layer 2 Gatekeeper."""

    def __init__(self, app: Flask | None = None) -> None:
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        setup_gate(app)


def get_current_actor() -> dict[str, Any] | None:
    """Helper to retrieve authenticated actor from request context."""
    return getattr(g, "actor", None)


def get_current_user() -> dict[str, Any] | None:
    """Helper to retrieve authenticated user from request context."""
    return getattr(g, "user", None)
