"""Comprehensive Test Suite for LMS Academic Management Features.

Covers:
- POST /auth/refresh (Token refresh flow and validation)
- Course Management: Creation, Details, Student Enrollment
- Lesson Management: Addition, Completion, Progress tracking
- Assignment Management: Creation, Listing, Student Submission, Grading
- Layer 2 Gatekeeper, Layer 3 RBAC, Layer 4 Object-Level Authorization
- Layer 5 Input Validation, Layer 6 Fail-Closed & Output Sanitization
- Layer 8 Audit Logging
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from lms_project_1 import create_app

TEST_SECRET = "super_secret_test_key_at_least_32_chars_long"


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    audit_file = tmp_path / "test_academic_audit.log"
    return create_app(
        {
            "JWT_SECRET": TEST_SECRET,
            "TOKEN_TTL_SECONDS": 900,
            "AUDIT_LOG_PATH": str(audit_file),
            "TESTING": True,
        }
    )


@pytest.fixture
def client(app: Flask) -> Any:
    return app.test_client()


def login_user(client: Any, email: str, password: str = "Lms@2026") -> dict[str, Any]:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"
    return res.get_json()


# =========================================================================
# 1. Token Refresh Flow (/auth/refresh)
# =========================================================================


def test_token_refresh_success(client: Any) -> None:
    """POST /auth/refresh with valid refresh token returns new access and refresh tokens."""
    auth_data = login_user(client, "chi.sv@lms.test")
    refresh_token = auth_data["refreshToken"]

    # 1. Refresh via JSON body
    res = client.post("/auth/refresh", json={"refreshToken": refresh_token})
    assert res.status_code == 200
    data = res.get_json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["expiresIn"] == 900

    # 2. Use the new access token to call protected endpoint
    new_token = data["accessToken"]
    res_me = client.get("/me", headers={"Authorization": f"Bearer {new_token}"})
    assert res_me.status_code == 200
    assert res_me.get_json()["email"] == "chi.sv@lms.test"


def test_token_refresh_via_bearer_header(client: Any) -> None:
    """POST /auth/refresh accepts refreshToken in Authorization header."""
    auth_data = login_user(client, "an.gv@lms.test")
    refresh_token = auth_data["refreshToken"]

    res = client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})
    assert res.status_code == 200
    data = res.get_json()
    assert "accessToken" in data


def test_token_refresh_invalid_or_missing(client: Any) -> None:
    """POST /auth/refresh with invalid, missing or wrong-type token fails securely."""
    # Missing token
    res = client.post("/auth/refresh", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "VALIDATION_ERROR"

    # Malformed token
    res_bad = client.post("/auth/refresh", json={"refreshToken": "not.a.valid.jwt"})
    assert res_bad.status_code == 401
    assert res_bad.get_json()["error"] == "UNAUTHENTICATED"

    # Access token passed instead of refresh token (type mismatch)
    auth_data = login_user(client, "chi.sv@lms.test")
    access_token = auth_data["accessToken"]
    res_type = client.post("/auth/refresh", json={"refreshToken": access_token})
    assert res_type.status_code == 401


# =========================================================================
# 2. Course Creation & Details
# =========================================================================


def test_create_course_teacher_success(client: Any) -> None:
    """Teacher creates a new course; instructorId is assigned automatically."""
    auth_data = login_user(client, "an.gv@lms.test")
    token = auth_data["accessToken"]

    payload = {
        "title": "Bảo mật Điện toán Đám mây",
        "description": "Các kỹ thuật phòng thủ trên AWS và Google Cloud.",
        "durationHours": 40,
    }
    res = client.post(
        "/courses",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["title"] == "Bảo mật Điện toán Đám mây"
    assert data["instructorId"] == "u2"
    assert data["durationHours"] == 40
    assert len(data["lessons"]) >= 1


def test_create_course_admin_success(client: Any) -> None:
    """Admin creates a new course and can assign it to a specific instructor."""
    auth_data = login_user(client, "admin@lms.test")
    token = auth_data["accessToken"]

    payload = {
        "title": "Trí Tuệ Nhân Tạo Ứng Dụng",
        "description": "Nhập môn AI & Machine Learning.",
        "durationHours": 50,
        "instructorId": "u3",
    }
    res = client.post(
        "/courses",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data["instructorId"] == "u3"


def test_create_course_student_forbidden(client: Any) -> None:
    """Student attempting to create a course receives 403 FORBIDDEN."""
    auth_data = login_user(client, "chi.sv@lms.test")
    token = auth_data["accessToken"]

    res = client.post(
        "/courses",
        json={"title": "Khóa học trái phép"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403
    assert res.get_json()["error"] == "FORBIDDEN"


def test_create_course_validation_errors(client: Any) -> None:
    """Course creation validates title and durationHours strictly."""
    auth_data = login_user(client, "an.gv@lms.test")
    token = auth_data["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    # Empty title
    res1 = client.post("/courses", json={"title": ""}, headers=headers)
    assert res1.status_code == 400

    # Negative duration
    res2 = client.post(
        "/courses", json={"title": "Test Course", "durationHours": -5}, headers=headers
    )
    assert res2.status_code == 400

    # Non-JSON body
    res3 = client.post("/courses", data="not json", headers=headers)
    assert res3.status_code == 400


def test_get_course_detail(client: Any) -> None:
    """GET /courses/<course_id> returns course info and student enrollment status."""
    auth_data = login_user(client, "chi.sv@lms.test")
    token = auth_data["accessToken"]

    # Chi is enrolled in c1
    res = client.get("/courses/c1", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == "c1"
    assert data["title"] == "Lập trình Web"
    assert data["isEnrolled"] is True
    assert "studentScore" in data
    assert len(data["lessons"]) >= 1

    # Chi is not enrolled in c2
    res2 = client.get("/courses/c2", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    assert res2.get_json()["isEnrolled"] is False

    # Non-existent course returns 404
    res_none = client.get(
        "/courses/nonexistent_course", headers={"Authorization": f"Bearer {token}"}
    )
    assert res_none.status_code == 404
    assert res_none.get_json()["error"] == "NOT_FOUND"


# =========================================================================
# 3. Student Course Enrollment & Lessons
# =========================================================================


def test_student_enroll_in_course_success(client: Any) -> None:
    """Student can self-enroll in a course they haven't enrolled yet."""
    auth_data = login_user(client, "chi.sv@lms.test")
    token = auth_data["accessToken"]

    # Chi enrolls in c2
    res = client.post("/courses/c2/enroll", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["enrollment"]["courseId"] == "c2"
    assert data["enrollment"]["studentId"] == "u4"
    assert data["enrollment"]["score"] == 0.0

    # Check detail now shows enrolled
    res_detail = client.get("/courses/c2", headers={"Authorization": f"Bearer {token}"})
    assert res_detail.get_json()["isEnrolled"] is True


def test_student_enroll_duplicate_rejected(client: Any) -> None:
    """Enrolling again in the same course returns 400 Bad Request."""
    auth_data = login_user(client, "chi.sv@lms.test")
    token = auth_data["accessToken"]

    # Chi is already enrolled in c1
    res = client.post("/courses/c1/enroll", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert res.get_json()["error"] == "VALIDATION_ERROR"


def test_teacher_cannot_enroll_in_course(client: Any) -> None:
    """Teacher cannot enroll in course as student -> 403 FORBIDDEN."""
    auth_data = login_user(client, "an.gv@lms.test")
    token = auth_data["accessToken"]

    res = client.post("/courses/c1/enroll", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.get_json()["error"] == "FORBIDDEN"


def test_add_lesson_to_course(client: Any) -> None:
    """Assigned teacher can add lessons; unauthorized teacher is blocked (Layer 4)."""
    an_token = login_user(client, "an.gv@lms.test")["accessToken"]
    binh_token = login_user(client, "binh.gv@lms.test")["accessToken"]
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]

    # An (teaches c1) adds lesson to c1 -> 201
    res_an = client.post(
        "/courses/c1/lessons",
        json={"title": "Bài 5: Triển khai & CI/CD Pipeline"},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_an.status_code == 201
    lesson_data = res_an.get_json()
    assert "c1-l" in lesson_data["id"]
    assert lesson_data["title"] == "Bài 5: Triển khai & CI/CD Pipeline"

    # Binh (teaches c2, NOT c1) attempts to add lesson to c1 -> 403 FORBIDDEN (BOLA Defense)
    res_binh = client.post(
        "/courses/c1/lessons",
        json={"title": "Bài trái phép"},
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert res_binh.status_code == 403
    assert res_binh.get_json()["error"] == "FORBIDDEN"

    # Chi (Student) attempts to add lesson -> 403
    res_chi = client.post(
        "/courses/c1/lessons",
        json={"title": "Bài học sinh viên"},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res_chi.status_code == 403


def test_complete_lesson_flow(client: Any) -> None:
    """Enrolled student completes a lesson; non-enrolled receives 403."""
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]

    # Chi is enrolled in c1, completes lesson c1-l3
    res = client.post(
        "/courses/c1/lessons/c1-l3/complete",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "c1-l3" in data["completedLessons"]
    assert data["progress"] > 0

    # Chi attempts to complete lesson in c2 (not enrolled) -> 403
    res_c2 = client.post(
        "/courses/c2/lessons/c2-l1/complete",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res_c2.status_code == 403

    # Non-existent lesson returns 404
    res_none = client.post(
        "/courses/c1/lessons/c1-nonexistent/complete",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res_none.status_code == 404


# =========================================================================
# 4. Assignments & Submissions & Grading
# =========================================================================


def test_assignment_full_lifecycle(app: Flask, client: Any) -> None:
    """Full lifecycle: Teacher creates assignment -> Student submits -> Teacher grades."""
    an_token = login_user(client, "an.gv@lms.test")["accessToken"]
    binh_token = login_user(client, "binh.gv@lms.test")["accessToken"]
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]

    # 1. Teacher An creates assignment in c1
    res_create = client.post(
        "/courses/c1/assignments",
        json={
            "title": "Bài tập lớn: REST API & Bảo mật",
            "description": "Xây dựng hệ thống REST API hoàn chỉnh với Flask.",
            "maxScore": 10.0,
        },
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_create.status_code == 201
    assign_id = res_create.get_json()["id"]
    assert assign_id is not None

    # 2. Teacher Binh tries to create assignment in c1 -> 403 (Layer 4 IDOR Defense)
    res_binh_create = client.post(
        "/courses/c1/assignments",
        json={"title": "Assignment trái phép"},
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert res_binh_create.status_code == 403

    # 3. Student Chi lists assignments for c1 -> 200
    res_list = client.get(
        "/courses/c1/assignments", headers={"Authorization": f"Bearer {chi_token}"}
    )
    assert res_list.status_code == 200
    assignments = res_list.get_json()
    assert any(a["id"] == assign_id for a in assignments)

    # 4. Student Chi submits the assignment -> 201
    res_sub = client.post(
        f"/courses/c1/assignments/{assign_id}/submit",
        json={"content": "https://github.com/chilinh/mini-lms-project-submission"},
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res_sub.status_code == 201
    sub_data = res_sub.get_json()["submission"]
    assert sub_data["studentId"] == "u4"
    assert sub_data["score"] is None

    # 5. Teacher An views submissions for the assignment -> 200
    res_view = client.get(
        f"/courses/c1/assignments/{assign_id}/submissions",
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_view.status_code == 200
    submissions = res_view.get_json()
    assert len(submissions) >= 1
    assert any(s["studentId"] == "u4" for s in submissions)

    # 6. Student Chi tries to view submissions -> 403 (Teacher/Admin only)
    res_chi_view = client.get(
        f"/courses/c1/assignments/{assign_id}/submissions",
        headers={"Authorization": f"Bearer {chi_token}"},
    )
    assert res_chi_view.status_code == 403

    # 7. Teacher Binh tries to grade Chi's submission in c1 -> 403 (Teacher Binh does not teach c1)
    res_binh_grade = client.put(
        f"/courses/c1/assignments/{assign_id}/submissions/u4/grade",
        json={"score": 8.0, "feedback": "Làm bài tốt"},
        headers={"Authorization": f"Bearer {binh_token}"},
    )
    assert res_binh_grade.status_code == 403

    # 8. Teacher An grades Chi's submission -> 200
    res_grade = client.put(
        f"/courses/c1/assignments/{assign_id}/submissions/u4/grade",
        json={"score": 9.5, "feedback": "Code clean, xử lý lỗi an toàn và đầy đủ test."},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    assert res_grade.status_code == 200
    grade_data = res_grade.get_json()["submission"]
    assert grade_data["score"] == 9.5
    assert grade_data["feedback"] == "Code clean, xử lý lỗi an toàn và đầy đủ test."

    # 9. Verify Layer 8 Audit Logging
    audit_file = Path(app.config["AUDIT_LOG_PATH"])
    assert audit_file.is_file()
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    grade_logs = [
        json.loads(line_entry) for line_entry in lines if "GRADE_ASSIGNMENT" in line_entry
    ]
    assert len(grade_logs) >= 1
    last_log = grade_logs[-1]
    assert last_log["actorId"] == "u2"
    assert last_log["newScore"] == 9.5
    assert last_log["result"] == "SUCCESS"


def test_assignment_grade_validation_errors(client: Any) -> None:
    """Grading submission validates score domain within [0, maxScore]."""
    an_token = login_user(client, "an.gv@lms.test")["accessToken"]
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]

    # Create assignment
    res_c = client.post(
        "/courses/c1/assignments",
        json={"title": "Quiz 1", "maxScore": 10.0},
        headers={"Authorization": f"Bearer {an_token}"},
    )
    aid = res_c.get_json()["id"]

    # Submit
    client.post(
        f"/courses/c1/assignments/{aid}/submit",
        json={"content": "Answer content"},
        headers={"Authorization": f"Bearer {chi_token}"},
    )

    headers = {"Authorization": f"Bearer {an_token}"}
    grade_url = f"/courses/c1/assignments/{aid}/submissions/u4/grade"

    # Score > maxScore (11 > 10)
    res1 = client.put(grade_url, json={"score": 11.0}, headers=headers)
    assert res1.status_code == 400
    assert res1.get_json()["error"] == "VALIDATION_ERROR"

    # Score < 0
    res2 = client.put(grade_url, json={"score": -1.0}, headers=headers)
    assert res2.status_code == 400

    # Score as boolean
    res3 = client.put(grade_url, json={"score": True}, headers=headers)
    assert res3.status_code == 400

    # Score as string
    res4 = client.put(grade_url, json={"score": "9"}, headers=headers)
    assert res4.status_code == 400
