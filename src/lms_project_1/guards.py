"""Layer 3: Role-Based Access Control Guards (guards.py)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

from flask import current_app, g

from lms_project_1.errors import Forbidden, NotFound

F = TypeVar("F", bound=Callable[..., Any])


def require_role(*roles: str) -> Callable[[F], F]:
    """Decorator asserting that the authenticated actor possesses one of the required roles.

    Extracts user role from request context (g.actor set by Layer 2).
    Follows check order: 401 -> 404 (course) -> 403 (role).
    Raises Forbidden (HTTP 403 {"error": "FORBIDDEN"}) on mismatch.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Check order: 404 (môn) before 403 (vai trò)
            course_id = kwargs.get("course_id")
            if course_id is not None:
                store = getattr(current_app, "store", None) or (
                    current_app.config.get("STORE") if hasattr(current_app, "config") else None
                )
                if (
                    store is not None
                    and hasattr(store, "get_course_by_id")
                    and store.get_course_by_id(course_id) is None
                ):
                    raise NotFound(f"Course '{course_id}' not found")

            actor = getattr(g, "actor", None) or getattr(g, "user", None)
            if not actor or not isinstance(actor, dict):
                raise Forbidden("Unauthenticated actor context")

            user_role = actor.get("role")
            if user_role not in roles:
                raise Forbidden("Insufficient role permissions")

            return fn(*args, **kwargs)

        return cast(F, wrapper)

    return decorator
