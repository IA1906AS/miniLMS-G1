"""LRN-01..LRN-07 learning experience acceptance and authorization tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lms_project_1 import create_app

SECRET = "learning_test_secret_at_least_32_characters"


@pytest.fixture(params=[False, True], ids=["memory", "sqlite"])
def client(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    config: dict[str, Any] = {
        "TESTING": True,
        "JWT_SECRET": SECRET,
        "AUDIT_LOG_PATH": str(tmp_path / "learning.log"),
    }
    if request.param:
        config["DATABASE_URL"] = f"sqlite:///{tmp_path / 'learning.db'}"
    return create_app(config).test_client()


def token(client: Any, email: str) -> str:
    response = client.post("/auth/login", json={"email": email, "password": "Lms@2026"})
    assert response.status_code == 200
    return str(response.get_json()["accessToken"])


def auth(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_free_enrollment_lesson_access_progress_notification_and_certificate(client: Any) -> None:
    student = auth(token(client, "em.sv@lms.test"))
    other_student = auth(token(client, "dung.sv@lms.test"))

    assert client.get("/api/courses/c3/lessons/c3-l1", headers=student).status_code == 403
    enrolled = client.post("/api/courses/c3/enroll", headers=student)
    assert enrolled.status_code == 201
    assert enrolled.get_json()["status"] == "ACTIVE"
    assert client.post("/api/courses/c3/enroll", headers=student).status_code == 409

    lesson = client.get("/api/courses/c3/lessons/c3-l1", headers=student)
    assert lesson.status_code == 200
    assert lesson.get_json()["title"]

    for lesson_id in ("c3-l1", "c3-l2", "c3-l3", "c3-l4"):
        completed = client.put(f"/api/courses/c3/lessons/{lesson_id}/progress", headers=student)
        assert completed.status_code == 200
    repeated = client.put("/api/courses/c3/lessons/c3-l4/progress", headers=student)
    assert repeated.status_code == 200
    assert repeated.get_json()["percent"] == 100
    assert repeated.get_json()["completedLessons"] == 4

    notifications = client.get("/api/notifications", headers=student).get_json()
    assert notifications["unread"] >= 2
    notification_id = notifications["items"][0]["id"]
    assert (
        client.patch(
            f"/api/notifications/{notification_id}/read", headers=other_student
        ).status_code
        == 404
    )
    assert (
        client.patch(f"/api/notifications/{notification_id}/read", headers=student).status_code
        == 200
    )

    certificate = client.post("/api/courses/c3/certificate", headers=student)
    assert certificate.status_code == 201
    certificate_id = certificate.get_json()["id"]
    assert client.post("/api/courses/c3/certificate", headers=student).status_code == 200
    download = client.get(f"/api/certificates/{certificate_id}/download", headers=student)
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]
    assert (
        client.get(
            f"/api/certificates/{certificate_id}/download", headers=other_student
        ).status_code
        == 404
    )


def test_paid_course_requires_order_activation(client: Any) -> None:
    teacher = auth(token(client, "an.gv@lms.test"))
    admin = auth(token(client, "admin@lms.test"))
    student = auth(token(client, "em.sv@lms.test"))
    course = client.post(
        "/api/courses",
        json={"title": "Paid", "description": "Paid course", "durationHours": 2, "price": 500},
        headers=teacher,
    ).get_json()
    chapter = client.post(
        f"/api/courses/{course['id']}/chapters", json={"title": "Start"}, headers=teacher
    ).get_json()
    client.post(f"/api/chapters/{chapter['id']}/lessons", json={"title": "Lesson"}, headers=teacher)
    client.post(f"/api/courses/{course['id']}/submit", headers=teacher)
    client.post(
        f"/api/admin/courses/{course['id']}/decision", json={"decision": "APPROVE"}, headers=admin
    )

    assert client.post(f"/api/courses/{course['id']}/enroll", headers=student).status_code == 409
    activated = client.post(
        f"/api/admin/courses/{course['id']}/activate-enrollment",
        json={"studentId": "u6", "orderId": "order-paid-1"},
        headers=admin,
    )
    assert activated.status_code == 201
    assert activated.get_json()["activatedByOrderId"] == "order-paid-1"


def test_incomplete_student_cannot_get_certificate(client: Any) -> None:
    student = auth(token(client, "chi.sv@lms.test"))
    assert client.post("/api/courses/c1/certificate", headers=student).status_code == 409


def test_teacher_roster_progress_report_and_idor(client: Any) -> None:
    owner = auth(token(client, "an.gv@lms.test"))
    other_teacher = auth(token(client, "binh.gv@lms.test"))
    roster = client.get("/api/teacher/courses/c1/students", headers=owner)
    assert roster.status_code == 200
    assert roster.get_json()["total"] >= 1
    report = client.get("/api/teacher/courses/c1/progress", headers=owner)
    assert report.status_code == 200
    assert report.get_json()["students"]
    assert client.get("/api/teacher/courses/c1/students", headers=other_teacher).status_code == 403


def test_progress_certificate_and_notifications_survive_sqlite_restart(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'restart.db'}"
    config = {
        "TESTING": True,
        "JWT_SECRET": SECRET,
        "DATABASE_URL": database_url,
        "AUDIT_LOG_PATH": str(tmp_path / "restart.log"),
    }
    first = create_app(config).test_client()
    first_student = auth(token(first, "em.sv@lms.test"))
    assert first.post("/api/courses/c3/enroll", headers=first_student).status_code == 201
    for lesson_id in ("c3-l1", "c3-l2", "c3-l3", "c3-l4"):
        assert (
            first.put(
                f"/api/courses/c3/lessons/{lesson_id}/progress", headers=first_student
            ).status_code
            == 200
        )
    certificate_id = first.post("/api/courses/c3/certificate", headers=first_student).get_json()[
        "id"
    ]

    second = create_app(config).test_client()
    second_student = auth(token(second, "em.sv@lms.test"))
    progress = second.get("/api/courses/c3/progress", headers=second_student)
    assert progress.status_code == 200
    assert progress.get_json()["percent"] == 100
    assert (
        second.post("/api/courses/c3/certificate", headers=second_student).get_json()["id"]
        == certificate_id
    )
    before = second.get("/api/notifications", headers=second_student).get_json()["items"]
    second.put("/api/courses/c3/lessons/c3-l4/progress", headers=second_student)
    after = second.get("/api/notifications", headers=second_student).get_json()["items"]
    assert len(after) == len(before)
