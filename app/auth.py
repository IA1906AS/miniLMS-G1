from __future__ import annotations

import time
from typing import Any

import bcrypt
import jwt

from app.audit import write_audit_log
from app.errors import AccountLocked, InvalidCredentials, Unauthenticated, ValidationError
from app.store import store

_DUMMY_HASH: bytes = bcrypt.hashpw(b"DummyPassword@2026", bcrypt.gensalt(rounds=10))

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 15 * 60


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(user_id: str, secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        return payload
    except Exception as exc:
        raise Unauthenticated() from exc


def _check_and_update_lockout(email_key: str) -> dict[str, Any]:
    now = time.time()
    record = store.login_attempts.get(email_key)
    if not record:
        record = {"count": 0, "locked_until": 0.0}
        store.login_attempts[email_key] = record

    if record["locked_until"] > now:
        raise AccountLocked()

    if record["locked_until"] != 0.0 and record["locked_until"] <= now:
        record["count"] = 0
        record["locked_until"] = 0.0

    return record


def _record_failed_attempt(email_key: str) -> None:
    now = time.time()
    record = store.login_attempts.setdefault(email_key, {"count": 0, "locked_until": 0.0})
    record["count"] += 1
    if record["count"] >= MAX_FAILED_ATTEMPTS:
        record["locked_until"] = now + LOCKOUT_DURATION_SECONDS


def authenticate_user(email: str, password: str, secret: str, ttl_seconds: int) -> dict[str, Any]:
    email_key = email.strip().lower()
    attempt_record = _check_and_update_lockout(email_key)

    user = store.get_user_by_email(email_key)
    if not user:
        bcrypt.checkpw(password.encode("utf-8"), _DUMMY_HASH)
        _record_failed_attempt(email_key)
        raise InvalidCredentials()

    if not verify_password(password, user["password_hash"]):
        _record_failed_attempt(email_key)
        raise InvalidCredentials()

    attempt_record["count"] = 0
    attempt_record["locked_until"] = 0.0

    token = create_access_token(user["id"], secret=secret, ttl_seconds=ttl_seconds)
    return {
        "accessToken": token,
        "expiresIn": int(ttl_seconds),
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
        },
    }


def register_new_user(email: str, password: str, role: str = "STUDENT") -> dict[str, str]:
    email_key = email.strip().lower()
    if store.get_user_by_email(email_key) is not None:
        raise ValidationError()

    norm_role = role.strip().upper()
    if norm_role == "TEACHER":
        norm_role = "INSTRUCTOR"
    if norm_role not in {"STUDENT", "INSTRUCTOR", "GUEST"}:
        raise ValidationError()

    new_index = len(store.users_by_id) + 1
    new_id = f"u{new_index}"
    while new_id in store.users_by_id:
        new_index += 1
        new_id = f"u{new_index}"

    user_record = {
        "id": new_id,
        "email": email_key,
        "password_hash": hash_password(password),
        "role": norm_role,
    }
    store.users_by_id[new_id] = user_record
    store.users_by_email[email_key] = user_record
    store.id_aliases[new_id] = new_id

    write_audit_log(
        actor_id=new_id,
        action="REGISTER_USER",
        resource=f"/users/{new_id}",
        result="SUCCESS",
    )
    return {
        "id": new_id,
        "email": email_key,
        "role": norm_role,
    }


def reset_user_password(email: str, new_password: str) -> dict[str, str]:
    email_key = email.strip().lower()
    _check_and_update_lockout(email_key)

    user = store.get_user_by_email(email_key)
    if not user:
        bcrypt.checkpw(new_password.encode("utf-8"), _DUMMY_HASH)
        raise ValidationError()

    user["password_hash"] = hash_password(new_password)
    store.login_attempts[email_key] = {"count": 0, "locked_until": 0.0}

    write_audit_log(
        actor_id=user["id"],
        action="RESET_PASSWORD",
        resource=f"/users/{user['id']}",
        result="SUCCESS",
    )
    return {"status": "PASSWORD_UPDATED"}
