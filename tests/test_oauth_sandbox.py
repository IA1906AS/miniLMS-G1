"""AUTH-03 OAuth state/PKCE sandbox contract tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from lms_project_1 import create_app

TEST_SECRET = "oauth_sandbox_test_secret_at_least_32_chars"


def make_client(tmp_path: Path, profile: dict[str, Any] | None = None) -> Any:
    def exchange(provider: str, code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
        assert provider == "google"
        assert code == "sandbox-code"
        assert len(verifier) >= 43
        assert redirect_uri == "http://localhost/auth/oauth/google/callback"
        return profile or {
            "subject": "google-subject-1",
            "email": "oauth.student@lms.test",
            "email_verified": True,
            "name": "OAuth Student",
        }

    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET": TEST_SECRET,
            "AUDIT_LOG_PATH": str(tmp_path / "oauth.log"),
            "OAUTH_PROVIDERS": {
                "google": {
                    "client_id": "sandbox-client",
                    "authorization_endpoint": "https://accounts.example.test/authorize",
                    "redirect_uri": "http://localhost/auth/oauth/google/callback",
                }
            },
            "OAUTH_EXCHANGE": exchange,
            "OAUTH_COOKIE_SECURE": False,
        }
    )
    return app.test_client()


def start_flow(client: Any) -> str:
    response = client.get("/auth/oauth/google/start")
    assert response.status_code == 200
    url = response.get_json()["authorizationUrl"]
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    return query["state"][0]


def test_oauth_sandbox_callback_creates_session_and_blocks_replay(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    state = start_flow(client)

    callback = client.get(
        "/auth/oauth/google/callback",
        query_string={"code": "sandbox-code", "state": state},
    )

    assert callback.status_code == 200
    data = callback.get_json()
    assert data["user"]["email"] == "oauth.student@lms.test"
    assert (
        client.get("/me", headers={"Authorization": f"Bearer {data['accessToken']}"}).status_code
        == 200
    )

    replay = client.get(
        "/auth/oauth/google/callback",
        query_string={"code": "sandbox-code", "state": state},
    )
    assert replay.status_code == 401


def test_oauth_rejects_state_mismatch_and_unverified_email(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        {
            "subject": "subject-unverified",
            "email": "unverified@lms.test",
            "email_verified": False,
        },
    )
    state = start_flow(client)

    mismatch = client.get(
        "/auth/oauth/google/callback",
        query_string={"code": "sandbox-code", "state": "wrong-state"},
    )
    assert mismatch.status_code == 401

    # Restart because mismatch must not consume the valid server-side state.
    state = start_flow(client)
    unverified = client.get(
        "/auth/oauth/google/callback",
        query_string={"code": "sandbox-code", "state": state},
    )
    assert unverified.status_code == 401


def test_oauth_refuses_implicit_link_to_existing_password_account(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        {
            "subject": "attacker-controlled-subject",
            "email": "admin@lms.test",
            "email_verified": True,
            "name": "Not Admin",
        },
    )
    state = start_flow(client)

    response = client.get(
        "/auth/oauth/google/callback",
        query_string={"code": "sandbox-code", "state": state},
    )

    assert response.status_code == 409
