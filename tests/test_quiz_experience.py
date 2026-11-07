"""Playable quiz API acceptance, authorization, and answer-key safety tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lms_project_1 import create_app

SECRET = "quiz_experience_test_secret_at_least_32_chars"


@pytest.fixture(params=[False, True], ids=["memory", "sqlite"])
def client(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    config: dict[str, Any] = {
        "TESTING": True,
        "JWT_SECRET": SECRET,
        "AUDIT_LOG_PATH": str(tmp_path / "quiz-experience.log"),
    }
    if request.param:
        config["DATABASE_URL"] = f"sqlite:///{tmp_path / 'quiz-experience.db'}"
    return create_app(config).test_client()


def auth(client: Any, email: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": "Lms@2026"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['accessToken']}"}


def test_enrolled_student_can_list_and_complete_quiz_without_answer_key(client: Any) -> None:
    student = auth(client, "chi.sv@lms.test")
    for lesson_id in ("c1-l3", "c1-l4"):
        completed = client.put(f"/api/courses/c1/lessons/{lesson_id}/progress", headers=student)
        assert completed.status_code == 200
    assert completed.get_json()["percent"] == 100

    response = client.get("/api/courses/c1/quizzes", headers=student)
    assert response.status_code == 200
    quiz = response.get_json()["items"][0]
    assert quiz["id"] == "quiz_c1_01"
    assert quiz["questionCount"] == 5
    assert all("correctAnswer" not in question for question in quiz["questions"])

    started = client.post(f"/quizzes/{quiz['id']}/attempts", headers=student)
    assert started.status_code == 201
    attempt = started.get_json()
    assert attempt["course_id"] == "c1"
    resumed = client.post(f"/quizzes/{quiz['id']}/attempts", headers=student)
    assert resumed.status_code == 201
    assert resumed.get_json()["id"] == attempt["id"]

    invalid = client.put(
        f"/quizzes/{quiz['id']}/attempts/{attempt['id']}/answers",
        json={"answers": {"unknown": "A"}},
        headers=student,
    )
    assert invalid.status_code == 400

    saved = client.put(
        f"/quizzes/{quiz['id']}/attempts/{attempt['id']}/answers",
        json={"answers": {"q1": "A", "q2": "B", "q3": "C", "q4": "D", "q5": "A"}},
        headers=student,
    )
    assert saved.status_code == 200
    submitted = client.post(
        f"/quizzes/{quiz['id']}/attempts/{attempt['id']}/submit", headers=student
    )
    assert submitted.status_code == 200
    result = submitted.get_json()["attempt"]
    assert result["score"] == 10.0
    assert result["passed"] is True
    assert result["correct_count"] == 5


def test_quiz_access_requires_enrollment_and_course_ownership(client: Any) -> None:
    not_enrolled = auth(client, "em.sv@lms.test")
    other_teacher = auth(client, "binh.gv@lms.test")
    assert client.get("/api/courses/c1/quizzes", headers=not_enrolled).status_code == 403
    assert client.get("/api/courses/c1/quizzes", headers=other_teacher).status_code == 403
    assert client.post("/quizzes/quiz_c1_01/attempts", headers=not_enrolled).status_code == 403


def test_learning_ui_exposes_lesson_and_quiz_players() -> None:
    html = (Path(__file__).parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    assert '@click.stop="continueLearning(c)"' in html
    assert '@click.stop="openLearningCourse(c)"' in html
    assert '@click.self="closeLearningCenter()"' in html
    assert 'class="max-w-4xl' in html
    assert '@click.away="closeLearningCenter()"' not in html
    assert "async continueLearning(course)" in html
    assert "async openLesson(courseId, lessonId)" in html
    assert "if (progress?.percent >= 100)" in html
    assert "Bạn đã hoàn thành khóa học. Hãy chọn bài kiểm tra bên dưới." in html
    assert "async startQuiz(quiz)" in html
    assert "async saveQuizAnswers(showNotice = true)" in html
    assert "async submitQuiz()" in html
    assert "correctAnswer" not in html
