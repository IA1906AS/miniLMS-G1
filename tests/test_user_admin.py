"""USR-01..USR-03 administration acceptance tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lms_project_1 import create_app

SECRET = "user_admin_test_secret_at_least_32_characters"


def make_client(tmp_path: Path, *, database: bool = False) -> Any:
    config: dict[str, Any] = {
        "TESTING": True,
        "JWT_SECRET": SECRET,
        "AUDIT_LOG_PATH": str(tmp_path / "users.log"),
    }
    if database:
        config["DATABASE_URL"] = f"sqlite:///{tmp_path / 'users.db'}"
    return create_app(config).test_client()


def login(client: Any, email: str) -> dict[str, Any]:
    response = client.post("/auth/login", json={"email": email, "password": "Lms@2026"})
    assert response.status_code == 200
    return dict(response.get_json())


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_search_filter_and_pagination(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = login(client, "admin@lms.test")

    response = client.get(
        "/api/admin/users?q=chi&role=student&status=active&page=1&per_page=2",
        headers=auth(admin["accessToken"]),
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["pagination"] == {"page": 1, "perPage": 2, "total": 1, "pages": 1}
    assert [item["email"] for item in data["items"]] == ["chi.sv@lms.test"]
    assert "password_hash" not in data["items"][0]


def test_non_admin_cannot_list_or_change_users(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    student = login(client, "chi.sv@lms.test")
    headers = auth(student["accessToken"])

    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert (
        client.patch(
            "/api/admin/users/u5/status",
            json={"active": False, "reason": "violation"},
            headers=headers,
        ).status_code
        == 403
    )


def test_lock_invalidates_access_and_unlock_restores_login(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    admin = login(client, "admin@lms.test")
    student = login(client, "dung.sv@lms.test")
    admin_headers = auth(admin["accessToken"])

    locked = client.patch(
        "/api/admin/users/u5/status",
        json={"active": False, "reason": "policy violation"},
        headers=admin_headers,
    )
    assert locked.status_code == 200
    assert client.get("/me", headers=auth(student["accessToken"])).status_code == 401
    assert (
        client.post(
            "/auth/login",
            json={"email": "dung.sv@lms.test", "password": "Lms@2026"},
        ).status_code
        == 401
    )

    unlocked = client.patch(
        "/api/admin/users/u5/status",
        json={"active": True},
        headers=admin_headers,
    )
    assert unlocked.status_code == 200
    assert login(client, "dung.sv@lms.test")["accessToken"]


def test_soft_delete_is_visible_but_blocks_login_and_self_delete(tmp_path: Path) -> None:
    client = make_client(tmp_path, database=True)
    admin = login(client, "admin@lms.test")
    headers = auth(admin["accessToken"])

    assert client.delete("/api/admin/users/u6", headers=headers).status_code == 204
    deleted = client.get("/api/admin/users?status=deleted", headers=headers).get_json()
    assert [item["id"] for item in deleted["items"]] == ["u6"]
    assert (
        client.post(
            "/auth/login",
            json={"email": "em.sv@lms.test", "password": "Lms@2026"},
        ).status_code
        == 401
    )
    assert client.delete("/api/admin/users/u1", headers=headers).status_code == 409
