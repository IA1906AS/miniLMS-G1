"""CRS-01..CRS-10 course management and governance acceptance tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from lms_project_1 import create_app

SECRET = "course_management_test_secret_at_least_32_chars"


@pytest.fixture(params=[False, True], ids=["memory", "sqlite"])
def client(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    config: dict[str, Any] = {
        "TESTING": True,
        "JWT_SECRET": SECRET,
        "AUDIT_LOG_PATH": str(tmp_path / "course.log"),
    }
    if request.param:
        config["DATABASE_URL"] = f"sqlite:///{tmp_path / 'course.db'}"
    config["UPLOAD_ROOT"] = str(tmp_path / "uploads")
    return create_app(config).test_client()


def login(client: Any, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": "Lms@2026"})
    assert response.status_code == 200
    return str(response.get_json()["accessToken"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_public_catalog_search_filter_pagination_and_detail(client: Any) -> None:
    response = client.get("/api/public/courses?q=web&category=general&page=1&per_page=2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["total"] >= 1
    assert len(data["items"]) <= 2

    detail = client.get(f"/api/public/courses/{data['items'][0]['id']}")
    assert detail.status_code == 200
    body = detail.get_json()
    assert {"description", "instructor", "price", "curriculum", "roadmap"} <= body.keys()


def test_category_crud_is_admin_only_and_protects_references(client: Any) -> None:
    admin = auth(login(client, "admin@lms.test"))
    teacher = auth(login(client, "an.gv@lms.test"))
    assert (
        client.post(
            "/api/admin/categories", json={"name": "AI", "slug": "ai"}, headers=teacher
        ).status_code
        == 403
    )

    created = client.post("/api/admin/categories", json={"name": "AI", "slug": "ai"}, headers=admin)
    assert created.status_code == 201
    category_id = created.get_json()["id"]
    updated = client.put(
        f"/api/admin/categories/{category_id}",
        json={"name": "Applied AI", "slug": "applied-ai"},
        headers=admin,
    )
    assert updated.status_code == 200
    assert client.delete(f"/api/admin/categories/{category_id}", headers=admin).status_code == 204


def test_course_authoring_curriculum_roadmap_resource_and_governance(client: Any) -> None:
    teacher = auth(login(client, "an.gv@lms.test"))
    other_teacher = auth(login(client, "binh.gv@lms.test"))
    admin = auth(login(client, "admin@lms.test"))

    created = client.post(
        "/api/courses",
        json={
            "title": "Secure Flask",
            "description": "Build and defend a production Flask application.",
            "durationHours": 12,
            "price": 0,
        },
        headers=teacher,
    )
    assert created.status_code == 201
    course_id = created.get_json()["id"]
    assert created.get_json()["status"] == "DRAFT"
    assert (
        client.put(
            f"/api/courses/{course_id}", json={"title": "Stolen"}, headers=other_teacher
        ).status_code
        == 403
    )

    chapter = client.post(
        f"/api/courses/{course_id}/chapters",
        json={"title": "Foundation", "orderIndex": 1},
        headers=teacher,
    )
    assert chapter.status_code == 201
    lesson = client.post(
        f"/api/chapters/{chapter.get_json()['id']}/lessons",
        json={
            "title": "Threat model",
            "contentType": "VIDEO",
            "videoUrl": "https://cdn.example.test/video.mp4",
            "orderIndex": 1,
        },
        headers=teacher,
    )
    assert lesson.status_code == 201
    lesson_id = lesson.get_json()["id"]

    roadmap = client.post(
        f"/api/courses/{course_id}/roadmap",
        json={"title": "Model threats", "orderIndex": 1},
        headers=teacher,
    )
    assert roadmap.status_code == 201
    resource = client.post(
        f"/api/lessons/{lesson_id}/resources",
        json={
            "title": "Cheat sheet",
            "resourceUrl": "https://cdn.example.test/sheet.pdf",
            "mimeType": "application/pdf",
            "sizeBytes": 1024,
        },
        headers=teacher,
    )
    assert resource.status_code == 201
    uploaded = client.post(
        f"/api/lessons/{lesson_id}/resources/upload",
        data={"title": "Notes", "file": (BytesIO(b"safe notes"), "notes.txt", "text/plain")},
        headers=teacher,
    )
    assert uploaded.status_code == 201
    download = client.get(f"/api/resources/{uploaded.get_json()['id']}/download", headers=teacher)
    assert download.status_code == 200
    assert download.data == b"safe notes"
    assert (
        client.post(
            f"/api/lessons/{lesson_id}/resources",
            json={"title": "Bad", "resourceUrl": "javascript:alert(1)", "sizeBytes": 1},
            headers=teacher,
        ).status_code
        == 400
    )

    submitted = client.post(f"/api/courses/{course_id}/submit", headers=teacher)
    assert submitted.status_code == 200
    assert submitted.get_json()["status"] == "PENDING"
    assert client.get(f"/api/public/courses/{course_id}").status_code == 404

    approved = client.post(
        f"/api/admin/courses/{course_id}/decision", json={"decision": "APPROVE"}, headers=admin
    )
    assert approved.status_code == 200
    assert client.get(f"/api/public/courses/{course_id}").status_code == 200

    hidden = client.patch(
        f"/api/admin/courses/{course_id}/visibility", json={"visible": False}, headers=admin
    )
    assert hidden.status_code == 200
    assert client.get(f"/api/public/courses/{course_id}").status_code == 404

    archived = client.delete(f"/api/admin/courses/{course_id}", headers=admin)
    assert archived.status_code == 200
    assert archived.get_json()["status"] == "ARCHIVED"


def test_rejection_requires_reason(client: Any) -> None:
    teacher = auth(login(client, "an.gv@lms.test"))
    admin = auth(login(client, "admin@lms.test"))
    created = client.post(
        "/api/courses",
        json={"title": "Review me", "description": "Complete description", "durationHours": 1},
        headers=teacher,
    ).get_json()
    chapter = client.post(
        f"/api/courses/{created['id']}/chapters", json={"title": "One"}, headers=teacher
    ).get_json()
    client.post(f"/api/chapters/{chapter['id']}/lessons", json={"title": "One"}, headers=teacher)
    client.post(f"/api/courses/{created['id']}/submit", headers=teacher)
    assert (
        client.post(
            f"/api/admin/courses/{created['id']}/decision",
            json={"decision": "REJECT"},
            headers=admin,
        ).status_code
        == 400
    )
