from __future__ import annotations

from functools import wraps

from flask import g, request

from app.audit import write_audit_log
from app.errors import Forbidden, Unauthenticated


def require_role(*allowed_roles: str):
    normalized_roles = {r.upper() for r in allowed_roles}
    if "TEACHER" in normalized_roles:
        normalized_roles.add("INSTRUCTOR")
    if "INSTRUCTOR" in normalized_roles:
        normalized_roles.add("TEACHER")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor = getattr(g, "current_actor", None) or getattr(g, "actor", None)
            if not actor:
                raise Unauthenticated()

            actor_role = str(actor.get("role", "")).upper()
            if actor_role not in normalized_roles:
                write_audit_log(
                    actor_id=actor.get("id"),
                    action=f"{request.method} {request.path}",
                    resource=request.path,
                    result="FORBIDDEN",
                )
                raise Forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator
