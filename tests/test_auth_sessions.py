"""AUTH-02/AUTH-05 session revocation and profile acceptance tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask

from lms_project_1 import create_app

TEST_SECRET = "auth_session_test_secret_at_least_32_characters"


def make_app(tmp_path: Path, *, database: bool = False) -> Flask:
    config: dict[str, Any] = {
        "TESTING": True,
        "JWT_SECRET": TEST_SECRET,
        "AUDIT_LOG_PATH": str(tmp_path / "auth-session.log"),
    }
    if database:
        config["DATABASE_URL"] = f"sqlite:///{tmp_path / 'auth-session.db'}"
    return create_app(config)


def login(client: Any, email: str = "chi.sv@lms.test") -> dict[str, Any]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "Lms@2026"},
    )
    assert response.status_code == 200
    return dict(response.get_json())


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_logout_revokes_access_and_refresh_tokens(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()
    tokens = login(client)

    response = client.post(
        "/auth/logout",
        json={"refreshToken": tokens["refreshToken"]},
        headers=bearer(tokens["accessToken"]),
    )

    assert response.status_code == 204
    assert client.get("/me", headers=bearer(tokens["accessToken"])).status_code == 401
    assert (
        client.post("/auth/refresh", json={"refreshToken": tokens["refreshToken"]}).status_code
        == 401
    )


def test_refresh_rotation_rejects_replay_and_keeps_new_token_valid(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()
    first = login(client)

    rotated = client.post("/auth/refresh", json={"refreshToken": first["refreshToken"]})
    assert rotated.status_code == 200
    second = rotated.get_json()

    replay = client.post("/auth/refresh", json={"refreshToken": first["refreshToken"]})
    assert replay.status_code == 401
    assert replay.get_json() == {"error": "UNAUTHENTICATED"}

    valid = client.post("/auth/refresh", json={"refreshToken": second["refreshToken"]})
    assert valid.status_code == 200


def test_session_revocation_persists_with_sqlalchemy_store(tmp_path: Path) -> None:
    app = make_app(tmp_path, database=True)
    client = app.test_client()
    tokens = login(client)

    assert (
        client.post(
            "/auth/logout",
            json={"refreshToken": tokens["refreshToken"]},
            headers=bearer(tokens["accessToken"]),
        ).status_code
        == 204
    )
    assert client.get("/me", headers=bearer(tokens["accessToken"])).status_code == 401


def test_profile_updates_unique_email_and_avatar(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()
    tokens = login(client)

    response = client.put(
        "/account/profile",
        json={
            "email": "chi.updated@lms.test",
            "fullName": "Chi Updated",
            "avatarUrl": "https://cdn.example.test/avatar/chi.png",
        },
        headers=bearer(tokens["accessToken"]),
    )

    assert response.status_code == 200
    profile = response.get_json()["profile"]
    assert profile["email"] == "chi.updated@lms.test"
    assert profile["avatarUrl"].endswith("/chi.png")
    assert login(client, "chi.updated@lms.test")["user"]["email"] == "chi.updated@lms.test"


def test_profile_rejects_duplicate_email_and_unsafe_avatar_scheme(tmp_path: Path) -> None:
    client = make_app(tmp_path).test_client()
    tokens = login(client)
    headers = bearer(tokens["accessToken"])

    duplicate = client.put(
        "/account/profile",
        json={"email": "admin@lms.test"},
        headers=headers,
    )
    unsafe_avatar = client.put(
        "/account/profile",
        json={"avatarUrl": "javascript:alert(1)"},
        headers=headers,
    )

    assert duplicate.status_code == 409
    assert unsafe_avatar.status_code == 400
