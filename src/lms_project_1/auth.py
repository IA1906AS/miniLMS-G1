from __future__ import annotations

import hashlib
import secrets
import time
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import bcrypt
import jwt
from flask import Blueprint, Response, current_app, g, jsonify, request

from lms_project_1 import schemas


# Authentication and validation exception classes (compatible with Layer 6 error handling)
class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.error_code)


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class InvalidCredentialsError(AppError):
    status_code = 401
    error_code = "INVALID_CREDENTIALS"


class UnauthenticatedError(AppError):
    status_code = 401
    error_code = "UNAUTHENTICATED"


class AccountLockedError(AppError):
    status_code = 429
    error_code = "ACCOUNT_LOCKED"


InvalidCredentials = InvalidCredentialsError
Unauthenticated = UnauthenticatedError
AccountLocked = AccountLockedError


# Cost >= 10 as specified in Technical Requirements
BCRYPT_ROUNDS = 10

# Precomputed dummy hash for timing-attack mitigation (constant-time verification)
DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"dummy_constant_time_protection", bcrypt.gensalt(10)).decode(
    "utf-8"
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.errorhandler(AppError)
def handle_auth_app_error(e: AppError) -> tuple[Response, int]:
    """Blueprint-level error handler ensuring consistent JSON error responses."""
    return jsonify({"error": e.error_code}), e.status_code


def hash_password(plain_password: str, rounds: int = BCRYPT_ROUNDS) -> str:
    """Hash a plain text password using bcrypt with cost >= 10.

    Raw passwords must never be stored in memory or persisted.
    """
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return str(hashed.decode("utf-8"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verify a plain text password against a bcrypt hash."""
    try:
        return bool(
            bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        )
    except Exception:
        return False


def create_access_token(
    user_id: str,
    secret: str,
    ttl_seconds: int = 900,
    role: str | None = None,
    email: str | None = None,
    jti: str | None = None,
) -> str:
    """Generate a signed JWT access token containing sub, iat, exp, and optional role/email."""
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be configured and >= 32 characters")

    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": jti or secrets.token_urlsafe(24),
    }
    if role:
        payload["role"] = role
    if email:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    user_id: str,
    secret: str,
    ttl_days: int = 7,
    *,
    jti: str | None = None,
    family_id: str | None = None,
) -> str:
    """Generate a signed JWT refresh token valid for 7-30 days."""
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be configured and >= 32 characters")

    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + (ttl_days * 86400),
        "jti": jti or secrets.token_urlsafe(24),
        "family": family_id or secrets.token_urlsafe(24),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    """Decode and verify a JWT token using HS256 algorithm only.

    Strictly rejects alg: none, invalid signatures, expired tokens, or tokens
    missing required sub/iat/exp claims.
    """
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be configured and >= 32 characters")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "require": ["sub", "iat", "exp"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_signature": True,
            },
        )
        if not isinstance(payload, dict) or "sub" not in payload:
            raise Unauthenticated("Token payload missing subject")
        return payload
    except (jwt.PyJWTError, Exception) as exc:
        raise Unauthenticated("Invalid or expired token") from exc


def decode_refresh_token(token: str, secret: str) -> dict[str, Any]:
    """Decode and verify a JWT refresh token using HS256 algorithm only."""
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be configured and >= 32 characters")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "require": ["sub", "iat", "exp", "type", "jti", "family"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_signature": True,
            },
        )
        if not isinstance(payload, dict) or payload.get("type") != "refresh":
            raise Unauthenticated("Invalid refresh token type")
        return payload
    except (jwt.PyJWTError, Exception) as exc:
        raise Unauthenticated("Invalid or expired refresh token") from exc


def _issue_oauth_token_pair(user: dict[str, Any], store: Any) -> dict[str, Any]:
    """Issue and persist the initial token pair after an OAuth callback."""
    secret = str(current_app.config.get("JWT_SECRET", ""))
    ttl = int(current_app.config.get("TOKEN_TTL_SECONDS", 900))
    access_jti = secrets.token_urlsafe(24)
    refresh_jti = secrets.token_urlsafe(24)
    family_id = secrets.token_urlsafe(24)
    access_token = create_access_token(
        str(user["id"]),
        secret,
        ttl_seconds=ttl,
        role=str(user.get("role", "student")),
        email=str(user.get("email", "")),
        jti=access_jti,
    )
    refresh_token = create_refresh_token(
        str(user["id"]), secret, jti=refresh_jti, family_id=family_id
    )
    payload = decode_refresh_token(refresh_token, secret)
    store.create_refresh_session(
        jti=refresh_jti,
        user_id=str(user["id"]),
        family_id=family_id,
        token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
    )
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresIn": ttl,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name", user.get("fullName", "")),
            "role": user.get("role", "student"),
        },
    }


class BruteForceTracker:
    """Layer 7: Brute-force protection tracking failed login attempts per email.

    5 consecutive failed attempts lock the email for 15 minutes (900 seconds),
    returning 429 ACCOUNT_LOCKED even when the correct password is entered.
    Logging in successfully before reaching 5 attempts resets the counter.
    """

    def __init__(self, max_attempts: int = 5, lock_duration_seconds: int = 900) -> None:
        self.max_attempts = max_attempts
        self.lock_duration_seconds = lock_duration_seconds
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, email: str) -> bool:
        normalized = email.strip().lower()
        lock_time = self._locked_until.get(normalized)
        if lock_time is None:
            return False
        if time.time() < lock_time:
            return True
        # Lockout period expired; reset counters
        del self._locked_until[normalized]
        self._failures[normalized] = 0
        return False

    def record_failure(self, email: str) -> bool:
        normalized = email.strip().lower()
        if self.is_locked(normalized):
            return True
        failures = self._failures.get(normalized, 0) + 1
        self._failures[normalized] = failures
        if failures >= self.max_attempts:
            self._locked_until[normalized] = time.time() + self.lock_duration_seconds
            return True
        return False

    def record_success(self, email: str) -> None:
        normalized = email.strip().lower()
        self._failures[normalized] = 0
        self._locked_until.pop(normalized, None)

    def reset(self) -> None:
        self._failures.clear()
        self._locked_until.clear()


default_tracker = BruteForceTracker()


def authenticate_token(
    auth_header: str | None,
    secret: str,
    store: Any = None,
) -> dict[str, Any]:
    """Verify Bearer token from header and return authenticated actor dict.

    Actor contains strictly {"id", "email", "role"}.
    Raises Unauthenticated if token is missing, expired, invalid, or user no
    longer exists in store.
    """
    if not auth_header:
        raise Unauthenticated("Missing Authorization header")

    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1].strip():
        raise Unauthenticated("Invalid Authorization header format")

    token = parts[1].strip()
    payload = decode_access_token(token, secret)
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise Unauthenticated("Invalid token subject")

    if store is not None:
        user = store.get_user_by_id(user_id)
        if user is None:
            raise Unauthenticated("User not found or no longer exists")
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
        }

    return {"id": user_id}


@auth_bp.post("/register")
def register() -> tuple[Response, int]:
    """POST /auth/register endpoint (Section 3.1 & TC01, TC02).

    Validates {email, password, full_name, role?}.
    Rejects duplicate email with 400 Bad Request.
    Persists user with bcrypt password hash and role 'guest' by default.
    Returns 201 Created without sensitive fields.
    """
    if not request.is_json:
        raise ValidationError("Request body must be JSON")

    try:
        body = request.get_json(silent=False)
    except Exception as exc:
        raise ValidationError("Malformed JSON") from exc

    validated_data = schemas.validate_register_payload(body)
    email = validated_data["email"]
    password = validated_data["password"]
    full_name = validated_data["full_name"]
    role = validated_data.get("role", "guest")

    store: Any = current_app.config.get("STORE")
    if not store:
        raise AppError("Data store not configured")

    # TC02: Email uniqueness check
    existing_user = store.get_user_by_email(email)
    if existing_user is not None:
        raise ValidationError("Email already registered")

    pwd_hash = hash_password(password)
    user = store.create_user(
        email=email,
        password_hash=pwd_hash,
        full_name=full_name,
        role=role,
        is_active=True,
        is_verified=False,
    )

    return jsonify(
        {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "is_active": user["is_active"],
            "is_verified": user["is_verified"],
        }
    ), 201


@auth_bp.post("/login")
def login() -> tuple[Response, int]:
    """POST /auth/login endpoint (Section 3.2 & TC03, TC04).

    Validates payload {email, password}, applies brute-force rate-limiting,
    verifies credentials with constant-time protection, and returns
    200 {accessToken, refreshToken, expiresIn, user}.
    """
    if not request.is_json:
        raise ValidationError("Request body must be JSON")

    try:
        data = request.get_json(silent=False)
    except Exception as exc:
        raise ValidationError("Malformed JSON") from exc

    if not isinstance(data, dict):
        raise ValidationError("JSON body must be an object")

    # Reject extra or missing fields
    expected_fields = {"email", "password"}
    if set(data.keys()) != expected_fields:
        raise ValidationError("Request body must strictly contain 'email' and 'password'")

    email = data.get("email")
    password = data.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        raise ValidationError("'email' and 'password' must be strings")

    tracker: BruteForceTracker = current_app.config.get("BRUTE_FORCE_TRACKER", default_tracker)
    store: Any = current_app.config.get("STORE")
    secret: str = current_app.config.get("JWT_SECRET", "")
    ttl: int = int(current_app.config.get("TOKEN_TTL_SECONDS", 900))

    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be configured and >= 32 characters")

    # Layer 7: Brute force lockout check
    if tracker.is_locked(email):
        raise AccountLocked("Account is temporarily locked")

    user = store.get_user_by_email(email) if store else None

    if user is None:
        # Constant-time mitigation against user enumeration
        verify_password(password, DUMMY_BCRYPT_HASH)
        tracker.record_failure(email)
        raise InvalidCredentials("Invalid credentials")

    password_hash = user.get("password_hash", "")
    if not verify_password(password, password_hash):
        tracker.record_failure(email)
        raise InvalidCredentials("Invalid credentials")

    # Login successful: reset failed attempt counter
    tracker.record_success(email)

    if not user.get("is_active", True):
        raise InvalidCredentials("Invalid credentials")

    access_jti = secrets.token_urlsafe(24)
    refresh_jti = secrets.token_urlsafe(24)
    family_id = secrets.token_urlsafe(24)
    access_token = create_access_token(
        user["id"],
        secret=secret,
        ttl_seconds=ttl,
        role=user.get("role"),
        email=user.get("email"),
        jti=access_jti,
    )
    refresh_token = create_refresh_token(
        user["id"], secret=secret, jti=refresh_jti, family_id=family_id
    )
    refresh_payload = decode_refresh_token(refresh_token, secret)
    store.create_refresh_session(
        jti=refresh_jti,
        user_id=str(user["id"]),
        family_id=family_id,
        token_hash=hashlib.sha256(refresh_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.fromtimestamp(int(refresh_payload["exp"]), UTC),
    )

    return jsonify(
        {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresIn": ttl,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name", ""),
                "role": user.get("role", "guest"),
            },
        }
    ), 200


@auth_bp.post("/forgot-password")
def forgot_password() -> tuple[Response, int]:
    """POST /auth/forgot-password endpoint (Section 3.3).

    Accepts {email}. Generates a cryptographically secure random reset token,
    hashes the token using SHA-256, and saves it with a 15-minute expiration.
    Returns generic success message to prevent user enumeration.
    """
    if not request.is_json:
        raise ValidationError("Request body must be JSON")

    try:
        body = request.get_json(silent=False)
    except Exception as exc:
        raise ValidationError("Malformed JSON") from exc

    email = schemas.validate_forgot_password_payload(body)
    store: Any = current_app.config.get("STORE")

    reset_token: str | None = None
    if store:
        user = store.get_user_by_email(email)
        if user is not None:
            # Generate 32-byte secure random string
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            expires_at = datetime.now(UTC) + timedelta(minutes=15)
            store.create_password_reset_token(
                user_id=user["id"],
                token_hash=token_hash,
                expires_at=expires_at,
            )
            reset_token = raw_token

    response_payload: dict[str, Any] = {
        "message": "If the email is registered, a password reset link has been sent."
    }
    # For testing and dev convenience, include token when in TESTING or DEBUG mode
    if current_app.config.get("TESTING") and reset_token:
        response_payload["resetToken"] = reset_token

    return jsonify(response_payload), 200


@auth_bp.post("/reset-password")
def reset_password() -> tuple[Response, int]:
    """POST /auth/reset-password endpoint (Section 3.3 & TC05, TC06).

    Accepts {token, new_password}.
    Validates token existence, expiration, and unused status.
    Updates hashed password, marks token as used, and returns 200 OK.
    """
    if not request.is_json:
        raise ValidationError("Request body must be JSON")

    try:
        body = request.get_json(silent=False)
    except Exception as exc:
        raise ValidationError("Malformed JSON") from exc

    token, new_password = schemas.validate_reset_password_payload(body)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    store: Any = current_app.config.get("STORE")
    if not store:
        raise AppError("Data store not configured")

    token_rec = store.get_password_reset_token(token_hash)
    if token_rec is None:
        raise ValidationError("Invalid or expired reset token")

    # TC06: Check if token has already been used
    if token_rec.get("is_used"):
        raise ValidationError("Reset token has already been used")

    # Check token expiration
    expires_at = token_rec.get("expires_at")
    if expires_at is not None and isinstance(expires_at, datetime):
        now = datetime.now(UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now > expires_at:
            raise ValidationError("Reset token has expired")

    # Update user password with new hash
    new_hash = hash_password(new_password)
    store.update_user_password(token_rec["user_id"], new_hash)

    # Invalidate reset token
    store.mark_password_reset_token_used(token_rec["id"])

    return jsonify({"message": "Password has been successfully reset."}), 200


@auth_bp.post("/refresh")
def refresh() -> tuple[Response, int]:
    """POST /auth/refresh endpoint.

    Accepts {"refreshToken": "..."} in body or Bearer token in Authorization header.
    Validates token and returns new accessToken and new refreshToken.
    """
    token_str: str | None = None
    if request.is_json:
        try:
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                token_str = body.get("refreshToken")
        except Exception:
            pass

    if not token_str:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token_str = auth_header.split(" ", 1)[1].strip()

    if not token_str or not isinstance(token_str, str):
        raise ValidationError("Missing refreshToken in request body or Authorization header")

    secret: str = current_app.config.get("JWT_SECRET", "")
    ttl: int = int(current_app.config.get("TOKEN_TTL_SECONDS", 900))
    store: Any = current_app.config.get("STORE")

    payload = decode_refresh_token(token_str.strip(), secret)
    user_id = str(payload.get("sub", ""))
    old_jti = str(payload.get("jti", ""))
    family_id = str(payload.get("family", ""))
    session = store.get_refresh_session(old_jti) if store else None
    token_hash = hashlib.sha256(token_str.strip().encode("utf-8")).hexdigest()
    if (
        session is None
        or session.get("revoked_at") is not None
        or not secrets.compare_digest(str(session.get("token_hash", "")), token_hash)
    ):
        raise Unauthenticated("Refresh token was revoked or replayed")
    user = store.get_user_by_id(user_id) if store else None
    if not user or not user.get("is_active", True):
        raise Unauthenticated("User not found or inactive")

    new_access_jti = secrets.token_urlsafe(24)
    new_refresh_jti = secrets.token_urlsafe(24)
    new_access_token = create_access_token(
        user["id"],
        secret=secret,
        ttl_seconds=ttl,
        role=user.get("role"),
        email=user.get("email"),
        jti=new_access_jti,
    )
    new_refresh_token = create_refresh_token(
        user["id"],
        secret=secret,
        jti=new_refresh_jti,
        family_id=family_id,
    )
    new_refresh_payload = decode_refresh_token(new_refresh_token, secret)
    rotated = store.rotate_refresh_session(
        old_jti,
        new_jti=new_refresh_jti,
        user_id=user_id,
        family_id=family_id,
        token_hash=hashlib.sha256(new_refresh_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.fromtimestamp(int(new_refresh_payload["exp"]), UTC),
    )
    if not rotated:
        raise Unauthenticated("Refresh token was revoked or replayed")

    return jsonify(
        {
            "accessToken": new_access_token,
            "refreshToken": new_refresh_token,
            "expiresIn": ttl,
        }
    ), 200


@auth_bp.post("/logout")
def logout() -> tuple[str, int]:
    """Revoke the current access token and optional refresh token."""
    store: Any = current_app.config.get("STORE")
    payload = getattr(g, "jwt_payload", {})
    actor = getattr(g, "actor", {})
    access_jti = str(payload.get("jti", ""))
    access_exp = payload.get("exp")
    if not store or not access_jti or not isinstance(access_exp, int):
        raise Unauthenticated("Invalid access session")

    store.revoke_access_token(
        jti=access_jti,
        user_id=str(actor.get("id", "")),
        expires_at=datetime.fromtimestamp(access_exp, UTC),
    )

    if request.data:
        if not request.is_json:
            raise ValidationError("Request body must be JSON")
        body = request.get_json(silent=False)
        if not isinstance(body, dict) or set(body) != {"refreshToken"}:
            raise ValidationError("Request body must contain only 'refreshToken'")
        refresh_token = body.get("refreshToken")
        if not isinstance(refresh_token, str):
            raise ValidationError("'refreshToken' must be a string")
        refresh_payload = decode_refresh_token(
            refresh_token, str(current_app.config.get("JWT_SECRET", ""))
        )
        if str(refresh_payload.get("sub")) != str(actor.get("id")):
            raise Unauthenticated("Refresh token owner mismatch")
        store.revoke_refresh_session(str(refresh_payload.get("jti", "")))

    return "", 204


@auth_bp.get("/oauth/<provider>/start")
def oauth_start(provider: str) -> tuple[Response, int]:
    """Start a configured OAuth sandbox flow with state and PKCE S256."""
    provider_name = provider.lower()
    providers = current_app.config.get("OAUTH_PROVIDERS", {})
    config = providers.get(provider_name) if isinstance(providers, dict) else None
    if not isinstance(config, dict):
        raise ValidationError("OAuth provider is not configured")

    required = {"client_id", "authorization_endpoint", "redirect_uri"}
    if not required.issubset(config):
        raise ValidationError("OAuth provider configuration is incomplete")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    store: Any = current_app.config.get("STORE")
    store.create_oauth_state(
        state_hash=hashlib.sha256(state.encode()).hexdigest(),
        provider=provider_name,
        code_verifier=verifier,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": config.get("scope", "openid email profile"),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    response = jsonify(
        {
            "provider": provider_name,
            "authorizationUrl": f"{config['authorization_endpoint']}?{query}",
        }
    )
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=bool(current_app.config.get("OAUTH_COOKIE_SECURE", not current_app.testing)),
        samesite="Lax",
    )
    return response, 200


@auth_bp.get("/oauth/<provider>/callback")
def oauth_callback(provider: str) -> tuple[Response, int]:
    """Validate OAuth state, exchange a sandbox code and create a local session."""
    provider_name = provider.lower()
    state = request.args.get("state", "")
    code = request.args.get("code", "")
    cookie_state = request.cookies.get("oauth_state", "")
    if not state or not code or not secrets.compare_digest(state, cookie_state):
        raise Unauthenticated("OAuth state validation failed")

    store: Any = current_app.config.get("STORE")
    state_record = store.consume_oauth_state(
        hashlib.sha256(state.encode()).hexdigest(), provider_name
    )
    if state_record is None:
        raise Unauthenticated("OAuth state expired or replayed")

    providers = current_app.config.get("OAUTH_PROVIDERS", {})
    config = providers.get(provider_name) if isinstance(providers, dict) else None
    exchange = current_app.config.get("OAUTH_EXCHANGE")
    if not isinstance(config, dict) or not callable(exchange):
        raise ValidationError("OAuth sandbox exchange is not configured")
    profile = exchange(
        provider_name,
        code,
        str(state_record["code_verifier"]),
        str(config["redirect_uri"]),
    )
    if not isinstance(profile, dict):
        raise Unauthenticated("OAuth provider returned an invalid profile")
    subject = str(profile.get("subject", "")).strip()
    email = schemas.validate_email_format(profile.get("email"))
    if not subject or profile.get("email_verified") is not True:
        raise Unauthenticated("OAuth email is not verified")

    linked_user_id = store.get_oauth_identity(provider_name, subject)
    user = store.get_user_by_id(linked_user_id) if linked_user_id else None
    if user is None:
        if store.get_user_by_email(email) is not None:
            from lms_project_1.errors import ConflictError

            raise ConflictError("Sign in first to link this OAuth identity")
        user = store.create_user(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(48)),
            full_name=str(profile.get("name") or email.split("@", 1)[0]),
            role="student",
            is_active=True,
            is_verified=True,
        )
        store.link_oauth_identity(provider_name, subject, str(user["id"]))

    response = jsonify(_issue_oauth_token_pair(user, store))
    response.delete_cookie("oauth_state", samesite="Lax")
    return response, 200
