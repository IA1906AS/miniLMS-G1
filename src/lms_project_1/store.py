"""Data store for miniLMS supporting both in-memory cache and PostgreSQL database."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session, scoped_session

from lms_project_1.errors import ConflictError, ValidationError
from lms_project_1.models import (
    Assignment,
    Certificate,
    Course,
    CourseCategory,
    CourseChapter,
    CourseRoadmapItem,
    Enrollment,
    IdempotencyRecord,
    Lesson,
    LessonProgress,
    LessonResource,
    Notification,
    OAuthIdentity,
    PasswordResetToken,
    Quiz,
    RefreshSession,
    RevokedAccessToken,
    Submission,
    User,
)


def _quiz_questions_for_course(course_id: str) -> list[dict[str, Any]]:
    """Return a small server-side question bank without exposing its answer key."""
    topic = {
        "c1": "Flask và REST API",
        "c2": "PostgreSQL",
        "c3": "an toàn ứng dụng web",
    }.get(course_id.lower(), "nền tảng web")
    rows = [
        (
            "q1",
            f"Cách an toàn để đưa dữ liệu người dùng vào truy vấn {topic} là gì?",
            ("Truyền tham số", "Nối chuỗi", "Tắt validation", "Dùng quyền cao nhất"),
            "A",
        ),
        (
            "q2",
            "Mật khẩu nên được lưu theo cách nào?",
            ("Plain text", "Hash chậm có salt", "Base64", "Khóa trong source"),
            "B",
        ),
        (
            "q3",
            "Mã HTTP nào phù hợp khi đã xác thực nhưng không đủ quyền?",
            ("200", "401", "403", "500"),
            "C",
        ),
        (
            "q4",
            "Dữ liệu nào tuyệt đối không được ghi vào audit log?",
            ("Loại sự kiện", "Thời gian", "Mã người dùng", "Bearer token"),
            "D",
        ),
        (
            "q5",
            "Biện pháp chính chống IDOR/BOLA là gì?",
            ("Kiểm tra quyền trên từng tài nguyên", "Ẩn nút", "Dùng ID dài", "Đổi URL"),
            "A",
        ),
    ]
    return [
        {
            "id": question_id,
            "prompt": prompt,
            "options": [
                {"key": key, "label": label}
                for key, label in zip(("A", "B", "C", "D"), options, strict=True)
            ],
            "correctAnswer": correct_answer,
        }
        for question_id, prompt, options, correct_answer in rows
    ]


def _default_lesson_content(title: str) -> str:
    """Provide useful starter content when an imported lesson only has a title."""
    return (
        "Mục tiêu bài học\n"
        f"- Hiểu các khái niệm trọng tâm của {title}.\n"
        "- Áp dụng kiến thức qua ví dụ và bài thực hành.\n\n"
        "Nội dung\n"
        "Đọc phần giới thiệu, ghi lại các khái niệm chính và hoàn thành bài thực hành "
        "trước khi đánh dấu bài học là hoàn thành."
    )


class Store:
    """Store managing users, courses, enrollments, and password reset tokens."""

    def __init__(
        self,
        seed_path: str | Path | None = None,
        seed_data: dict[str, Any] | None = None,
        db_session: scoped_session[Session] | Session | None = None,
    ) -> None:
        self.db_session: scoped_session[Session] | Session | None = db_session
        self.users: dict[str, dict[str, Any]] = {}
        self.users_by_email: dict[str, dict[str, Any]] = {}
        self.courses: dict[str, dict[str, Any]] = {}
        self.course_categories: dict[str, dict[str, Any]] = {
            "cat-general": {"id": "cat-general", "name": "General", "slug": "general"}
        }
        self.course_chapters: dict[str, dict[str, Any]] = {}
        self.course_roadmap: dict[str, dict[str, Any]] = {}
        self.lesson_resources: dict[str, dict[str, Any]] = {}
        self.lesson_progress: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.notifications: dict[str, dict[str, Any]] = {}
        self.certificates: dict[str, dict[str, Any]] = {}
        # Key: (courseId, studentId) -> {"courseId": ..., "studentId": ..., "score": float}
        self.enrollments: dict[tuple[str, str], dict[str, Any]] = {}
        # In-memory reset tokens: token_hash -> record dict
        self.reset_tokens: dict[str, dict[str, Any]] = {}
        self.refresh_sessions: dict[str, dict[str, Any]] = {}
        self.revoked_access_tokens: dict[str, datetime] = {}
        self.auth_session_lock = threading.RLock()
        self.oauth_states: dict[str, dict[str, Any]] = {}
        self.oauth_identities: dict[tuple[str, str], str] = {}
        # Assignments: assignment_id -> dict
        self.assignments: dict[str, dict[str, Any]] = {}
        # Submissions: (assignment_id, student_id) -> dict
        self.submissions: dict[tuple[str, str], dict[str, Any]] = {}
        # Submissions log / all submissions (for duplicate detection in vulnerable vs patched)
        self.all_submissions: list[dict[str, Any]] = []
        # Idempotency cache: key -> record dict
        self.idempotency_cache: dict[str, dict[str, Any]] = {}
        self.idempotency_lock: threading.Lock = threading.Lock()
        # Pattern #6 Dashboard statistics cache: course_id -> {data: dict, cached_at: datetime}
        self.dashboard_cache: dict[str, dict[str, Any]] = {}
        self.dashboard_lock: threading.Lock = threading.Lock()
        # Pattern #7 Quiz attempts: attempt_id -> dict
        self.quizzes: dict[str, dict[str, Any]] = {}
        self.quiz_attempts: dict[str, dict[str, Any]] = {}
        self.quiz_attempts_lock: threading.Lock = threading.Lock()
        # Pattern #8 Transactional Outbox events
        self.outbox_events: list[dict[str, Any]] = []
        self.outbox_lock: threading.Lock = threading.Lock()
        # Pattern #10 Limited-capacity Seat Reservations
        self.classes: dict[str, dict[str, Any]] = {
            "lab_ai_101": {"id": "lab_ai_101", "name": "Lab AI Nâng Cao", "capacity": 2},
            "seminar_sec": {"id": "seminar_sec", "name": "Hội Thảo Bảo Mật Web", "capacity": 3},
        }
        self.seat_reservations: dict[str, dict[str, Any]] = {}
        self.reservation_lock: threading.RLock = threading.RLock()

        if seed_data is not None:
            self._load_data(seed_data)
        else:
            path = self._resolve_seed_path(seed_path)
            if path.is_file():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._load_data(data)
        if self.db_session is not None:
            self._hydrate_course_learning_from_db()

    def set_session(self, session: scoped_session[Session] | Session | None) -> None:
        """Bind an active database session."""
        self.db_session = session

    def _hydrate_course_learning_from_db(self) -> None:
        """Hydrate durable course/learning state after application restart."""
        if self.db_session is None:
            return
        for category_row in self.db_session.execute(select(CourseCategory)).scalars():
            self.course_categories[category_row.id] = {
                "id": category_row.id,
                "name": category_row.name,
                "slug": category_row.slug,
            }
        for course_row in self.db_session.execute(select(Course)).scalars():
            existing = self.courses.get(course_row.id, {})
            existing.update(
                {
                    "id": course_row.id,
                    "title": course_row.title,
                    "instructorId": course_row.instructor_id or "",
                    "categoryId": course_row.category_id or "",
                    "description": course_row.description,
                    "thumbnail": course_row.thumbnail,
                    "durationHours": course_row.duration_hours,
                    "price": course_row.price,
                    "status": course_row.status,
                    "isVisible": course_row.is_visible,
                    "rejectionReason": course_row.rejection_reason,
                    "isFeatured": existing.get("isFeatured", False),
                    "lessons": [],
                }
            )
            self.courses[course_row.id] = existing
        for chapter_row in self.db_session.execute(select(CourseChapter)).scalars():
            self.course_chapters[chapter_row.id] = {
                "id": chapter_row.id,
                "courseId": chapter_row.course_id,
                "title": chapter_row.title,
                "orderIndex": chapter_row.order_index,
            }
        for lesson_row in self.db_session.execute(select(Lesson)).scalars():
            course = self.courses.get(lesson_row.course_id)
            if course is not None:
                course.setdefault("lessons", []).append(
                    {
                        "id": lesson_row.id,
                        "courseId": lesson_row.course_id,
                        "chapterId": lesson_row.chapter_id,
                        "title": lesson_row.title,
                        "content": lesson_row.content or _default_lesson_content(lesson_row.title),
                        "contentType": lesson_row.content_type,
                        "videoUrl": lesson_row.video_url,
                        "orderIndex": lesson_row.order_index,
                    }
                )
        for roadmap_row in self.db_session.execute(select(CourseRoadmapItem)).scalars():
            self.course_roadmap[roadmap_row.id] = {
                "id": roadmap_row.id,
                "courseId": roadmap_row.course_id,
                "title": roadmap_row.title,
                "description": roadmap_row.description,
                "orderIndex": roadmap_row.order_index,
            }
        for resource_row in self.db_session.execute(select(LessonResource)).scalars():
            self.lesson_resources[resource_row.id] = {
                "id": resource_row.id,
                "lessonId": resource_row.lesson_id,
                "title": resource_row.title,
                "resourceUrl": resource_row.resource_url,
                "mimeType": resource_row.mime_type,
                "sizeBytes": resource_row.size_bytes,
            }
        for progress_row in self.db_session.execute(select(LessonProgress)).scalars():
            self.lesson_progress[
                (progress_row.course_id, progress_row.lesson_id, progress_row.student_id)
            ] = {"completedAt": progress_row.completed_at.isoformat()}
        for notification_row in self.db_session.execute(select(Notification)).scalars():
            self.notifications[notification_row.id] = {
                "id": notification_row.id,
                "userId": notification_row.user_id,
                "kind": notification_row.kind,
                "title": notification_row.title,
                "message": notification_row.message,
                "isRead": notification_row.is_read,
                "createdAt": notification_row.created_at.isoformat(),
            }
        for certificate_row in self.db_session.execute(select(Certificate)).scalars():
            course = self.courses.get(certificate_row.course_id, {})
            self.certificates[certificate_row.id] = {
                "id": certificate_row.id,
                "courseId": certificate_row.course_id,
                "studentId": certificate_row.student_id,
                "courseTitle": course.get("title", ""),
                "verificationCode": certificate_row.verification_code,
                "issuedAt": certificate_row.issued_at.isoformat(),
            }
        for quiz_row in self.db_session.execute(select(Quiz)).scalars():
            self.quizzes[quiz_row.id] = {
                "id": quiz_row.id,
                "courseId": quiz_row.course_id,
                "title": quiz_row.title,
                "timeLimitSeconds": quiz_row.time_limit_seconds,
                "questions": _quiz_questions_for_course(quiz_row.course_id),
                "passScore": 6.0,
            }

    def _resolve_seed_path(self, seed_path: str | Path | None) -> Path:
        if seed_path is not None:
            return Path(seed_path)
        candidates = [
            Path.cwd() / "seed.json",
            Path(__file__).resolve().parent / "seed.json",
            Path(__file__).resolve().parent.parent.parent / "seed.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return Path("seed.json")

    def _load_data(self, data: dict[str, Any]) -> None:
        raw_users = data.get("users", [])
        for u in raw_users:
            plain_pwd = u.get("password", "")
            salt = bcrypt.gensalt(rounds=10)
            pwd_hash = bcrypt.hashpw(plain_pwd.encode("utf-8"), salt).decode("utf-8")

            email = str(u["email"]).strip().lower()
            default_name = email.split("@")[0].replace(".", " ").title()

            user_record: dict[str, Any] = {
                "id": str(u["id"]),
                "email": email,
                "role": str(u["role"]),
                "password_hash": pwd_hash,
                "full_name": str(
                    u.get("fullName") or u.get("full_name") or u.get("name") or default_name
                ),
                "fullName": str(
                    u.get("fullName") or u.get("full_name") or u.get("name") or default_name
                ),
                "is_active": True,
                "is_verified": True,
                "locked_at": None,
                "locked_reason": None,
                "deleted_at": None,
                "phone": str(u.get("phone", "")),
                "bio": str(u.get("bio", "")),
                "avatarUrl": str(
                    u.get("avatarUrl")
                    or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150"
                ),
                "notifications": dict(
                    u.get(
                        "notifications",
                        {
                            "emailNewCourses": True,
                            "emailAssignments": True,
                            "emailGradeUpdates": True,
                        },
                    )
                ),
            }
            self.users[user_record["id"]] = user_record
            self.users_by_email[user_record["email"]] = user_record

        raw_courses = data.get("courses", [])
        for c in raw_courses:
            course_id = str(c["id"])
            default_lessons = [
                {"id": f"{course_id}-l1", "title": "Bài 1: Giới thiệu & Tổng quan"},
                {"id": f"{course_id}-l2", "title": "Bài 2: Cài đặt môi trường"},
                {"id": f"{course_id}-l3", "title": "Bài 3: Kiến thức cốt lõi"},
                {"id": f"{course_id}-l4", "title": "Bài 4: Thực hành & Đồ án"},
            ]
            lessons: list[dict[str, Any]] = []
            for index, raw_lesson in enumerate(c.get("lessons", default_lessons), start=1):
                lesson = dict(raw_lesson)
                lesson.setdefault("courseId", course_id)
                lesson.setdefault("chapterId", None)
                lesson.setdefault("orderIndex", index)
                lesson.setdefault("contentType", "TEXT")
                lesson.setdefault("videoUrl", None)
                lesson.setdefault(
                    "content",
                    (
                        "Mục tiêu bài học\n"
                        f"- Hiểu các khái niệm trọng tâm của {lesson.get('title', 'bài học')}.\n"
                        "- Áp dụng kiến thức qua ví dụ và bài thực hành.\n\n"
                        "Nội dung\n"
                        "Đọc phần giới thiệu, ghi lại các khái niệm chính và hoàn thành "
                        "bài thực hành trước khi đánh dấu bài học là hoàn thành."
                    ),
                )
                lessons.append(lesson)
            course_record: dict[str, Any] = {
                "id": course_id,
                "title": str(c.get("title", "")),
                "instructorId": str(c.get("instructorId", "")),
                "description": str(c.get("description", "")),
                "thumbnail": str(
                    c.get("thumbnail")
                    or "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600"
                ),
                "durationHours": int(c.get("durationHours", 30)),
                "isFeatured": bool(c.get("isFeatured", False)),
                "categoryId": str(c.get("categoryId", "cat-general")),
                "price": float(c.get("price", 0.0)),
                "status": str(c.get("status", "PUBLISHED")).upper(),
                "isVisible": bool(c.get("isVisible", True)),
                "rejectionReason": None,
                "lessons": lessons,
            }
            self.courses[course_record["id"]] = course_record

        raw_enrollments = data.get("enrollments", [])
        for e in raw_enrollments:
            course_id = str(e["courseId"])
            student_id = str(e["studentId"])
            score = float(e["score"])
            default_completed = (
                [f"{course_id}-l1", f"{course_id}-l2"] if score >= 7.0 else [f"{course_id}-l1"]
            )
            enrollment_record: dict[str, Any] = {
                "courseId": course_id,
                "studentId": student_id,
                "score": score,
                "enrolledAt": str(e.get("enrolledAt", "2026-02-15")),
                "completedLessons": list(e.get("completedLessons", default_completed)),
            }
            self.enrollments[(course_id, student_id)] = enrollment_record

        raw_assignments = data.get("assignments", [])
        for a in raw_assignments:
            aid = str(a["id"])
            assignment_record: dict[str, Any] = {
                "id": aid,
                "courseId": str(a.get("courseId", "")),
                "title": str(a.get("title", "")),
                "description": str(a.get("description", "")),
                "maxScore": float(a.get("maxScore", 10.0)),
                "createdAt": datetime.now(UTC).isoformat(),
            }
            self.assignments[aid] = assignment_record

        raw_submissions = data.get("submissions", [])
        for s in raw_submissions:
            sub_id = str(s["id"])
            aid = str(s.get("assignmentId", ""))
            sid = str(s.get("studentId", ""))
            sub_record: dict[str, Any] = {
                "id": sub_id,
                "assignmentId": aid,
                "studentId": sid,
                "content": str(s.get("content", "")),
                "score": float(s["score"]) if s.get("score") is not None else None,
                "feedback": str(s.get("feedback", "")),
                "submittedAt": str(s.get("submittedAt", datetime.now(UTC).isoformat())),
            }
            self.submissions[(aid, sid)] = sub_record
            self.all_submissions.append(sub_record)

        raw_classes = data.get("classes", [])
        for cl in raw_classes:
            cid = str(cl["id"])
            self.classes[cid] = {
                "id": cid,
                "courseId": str(cl.get("courseId", "")),
                "name": str(cl.get("name", "")),
                "capacity": int(cl.get("capacity", 30)),
                "room": str(cl.get("room", "")),
                "schedule": str(cl.get("schedule", "")),
            }

        raw_quizzes = data.get("quizzes", [])
        for q in raw_quizzes:
            qid = str(q["id"])
            course_id = str(q.get("courseId", ""))
            duration_minutes = int(q.get("durationMinutes", 30))
            questions = q.get("questions") or _quiz_questions_for_course(course_id)
            self.quizzes[qid] = {
                "id": qid,
                "courseId": course_id,
                "title": str(q.get("title", "")),
                "timeLimitSeconds": int(q.get("timeLimitSeconds", duration_minutes * 60)),
                "questions": questions,
                "passScore": float(q.get("passScore", 6.0)),
            }

    def get_class(self, class_id: str) -> dict[str, Any] | None:
        """Find a course class by ID."""
        return self.classes.get(class_id)

    def get_classes(self, course_id: str | None = None) -> list[dict[str, Any]]:
        """List course classes optionally filtered by course ID."""
        if course_id:
            return [
                c
                for c in self.classes.values()
                if c.get("course_id") == course_id or c.get("courseId") == course_id
            ]
        return list(self.classes.values())

    def get_reservations_for_class(self, class_id: str) -> list[dict[str, Any]]:
        """Get all reservations for a given class."""
        return [r for r in self.seat_reservations.values() if r.get("class_id") == class_id]

    def get_user_reservation_for_class(self, class_id: str, user_id: str) -> dict[str, Any] | None:
        """Find active/held reservation for a given user in a class."""
        for r in self.seat_reservations.values():
            if r.get("class_id") == class_id and r.get("user_id") == user_id:
                return r
        return None

    def get_reservation(self, reservation_id: str) -> dict[str, Any] | None:
        """Find a reservation by ID."""
        return self.seat_reservations.get(reservation_id)

    def save_reservation(self, record: dict[str, Any]) -> None:
        """Persist or update a seat reservation."""
        rid = record.get("id")
        if rid:
            self.seat_reservations[rid] = record

    def get_quizzes(self, course_id: str | None = None) -> list[dict[str, Any]]:
        """List quizzes optionally filtered by course ID."""
        if course_id:
            return [
                q
                for q in self.quizzes.values()
                if q.get("course_id") == course_id or q.get("courseId") == course_id
            ]
        return list(self.quizzes.values())

    def get_quiz(self, quiz_id: str) -> dict[str, Any] | None:
        """Find a quiz by ID."""
        return self.quizzes.get(quiz_id)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Find user by ID from DB (if active) or in-memory cache."""
        if self.db_session is not None:
            try:
                db_user = self.db_session.execute(
                    select(User).where(User.id == str(user_id))
                ).scalar_one_or_none()
                if db_user is not None:
                    return {
                        "id": db_user.id,
                        "email": db_user.email,
                        "role": db_user.role,
                        "password_hash": db_user.hashed_password,
                        "full_name": db_user.full_name,
                        "is_active": db_user.is_active,
                        "is_verified": db_user.is_verified,
                        "locked_at": db_user.locked_at,
                        "locked_reason": db_user.locked_reason,
                        "deleted_at": db_user.deleted_at,
                    }
            except Exception:
                pass

        user = self.users.get(str(user_id))
        if not user and str(user_id).isdigit():
            user = self.users.get(f"u{user_id}")
        elif not user and str(user_id).startswith("u") and str(user_id)[1:].isdigit():
            user = self.users.get(str(user_id)[1:])
        return dict(user) if user else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Find user by email (case-insensitive) from DB or in-memory cache."""
        normalized = email.strip().lower()
        if self.db_session is not None:
            try:
                db_user = self.db_session.execute(
                    select(User).where(User.email == normalized)
                ).scalar_one_or_none()
                if db_user is not None:
                    return {
                        "id": db_user.id,
                        "email": db_user.email,
                        "role": db_user.role,
                        "password_hash": db_user.hashed_password,
                        "full_name": db_user.full_name,
                        "is_active": db_user.is_active,
                        "is_verified": db_user.is_verified,
                        "locked_at": db_user.locked_at,
                        "locked_reason": db_user.locked_reason,
                        "deleted_at": db_user.deleted_at,
                    }
            except Exception:
                pass

        user = self.users_by_email.get(normalized)
        return dict(user) if user else None

    def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: str,
        role: str = "guest",
        is_active: bool = True,
        is_verified: bool = False,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new user."""
        uid = user_id or str(uuid.uuid4())
        normalized_email = email.strip().lower()

        if self.db_session is not None:
            try:
                user = User(
                    id=uid,
                    email=normalized_email,
                    hashed_password=password_hash,
                    full_name=full_name,
                    role=role,
                    is_active=is_active,
                    is_verified=is_verified,
                )
                self.db_session.add(user)
                self.db_session.commit()
                uid = user.id
            except Exception:
                self.db_session.rollback()
                raise

        user_record: dict[str, Any] = {
            "id": uid,
            "email": normalized_email,
            "role": role,
            "password_hash": password_hash,
            "full_name": full_name,
            "fullName": full_name,
            "phone": "",
            "bio": "",
            "avatarUrl": "",
            "notifications": {
                "emailNewCourses": True,
                "emailAssignments": True,
                "emailGradeUpdates": True,
            },
            "is_active": is_active,
            "is_verified": is_verified,
            "locked_at": None,
            "locked_reason": None,
            "deleted_at": None,
        }
        self.users[uid] = user_record
        self.users_by_email[normalized_email] = user_record
        return dict(user_record)

    def update_user_role(self, user_id: str, new_role: str) -> bool:
        """Update user role in DB and memory."""
        updated = False
        if self.db_session is not None:
            try:
                db_user = self.db_session.execute(
                    select(User).where(User.id == str(user_id))
                ).scalar_one_or_none()
                if db_user is not None:
                    db_user.role = new_role
                    self.db_session.commit()
                    updated = True
            except Exception:
                self.db_session.rollback()

        if str(user_id) in self.users:
            self.users[str(user_id)]["role"] = new_role
            email = self.users[str(user_id)]["email"]
            if email in self.users_by_email:
                self.users_by_email[email]["role"] = new_role
            updated = True

        return updated

    def list_users(
        self,
        *,
        query: str = "",
        role: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        """List sanitized users with deterministic filtering."""
        if self.db_session is not None:
            rows = self.db_session.execute(select(User)).scalars().all()
            users = [
                {
                    "id": row.id,
                    "email": row.email,
                    "fullName": row.full_name,
                    "role": row.role,
                    "isActive": row.is_active,
                    "lockedReason": row.locked_reason,
                    "deletedAt": row.deleted_at.isoformat() if row.deleted_at else None,
                }
                for row in rows
            ]
        else:
            users = [
                {
                    "id": user["id"],
                    "email": user["email"],
                    "fullName": user.get("fullName") or user.get("full_name", ""),
                    "role": user.get("role", "guest"),
                    "isActive": bool(user.get("is_active", True)),
                    "lockedReason": user.get("locked_reason"),
                    "deletedAt": (
                        user["deleted_at"].isoformat()
                        if isinstance(user.get("deleted_at"), datetime)
                        else user.get("deleted_at")
                    ),
                }
                for user in self.users.values()
            ]

        normalized_query = query.strip().lower()
        normalized_role = role.strip().lower()
        normalized_status = status.strip().lower()
        result: list[dict[str, Any]] = []
        for user in users:
            if normalized_query and normalized_query not in (
                f"{user['email']} {user['fullName']}".lower()
            ):
                continue
            if normalized_role and str(user["role"]).lower() != normalized_role:
                continue
            current_status = (
                "deleted" if user["deletedAt"] else "active" if user["isActive"] else "locked"
            )
            if normalized_status and current_status != normalized_status:
                continue
            user["status"] = current_status
            result.append(user)
        return sorted(result, key=lambda item: (str(item["email"]), str(item["id"])))

    def set_user_active(self, user_id: str, *, active: bool, reason: str = "") -> dict[str, Any]:
        """Lock or unlock a non-deleted account in DB and memory."""
        now = datetime.now(UTC)
        user = self.users.get(str(user_id))
        if self.db_session is not None:
            row = self.db_session.execute(
                select(User).where(User.id == str(user_id))
            ).scalar_one_or_none()
            if row is None or row.deleted_at is not None:
                raise KeyError(user_id)
            row.is_active = active
            row.locked_at = None if active else now
            row.locked_reason = None if active else reason
            self.db_session.commit()
        if user is not None:
            if user.get("deleted_at") is not None:
                raise KeyError(user_id)
            user["is_active"] = active
            user["locked_at"] = None if active else now
            user["locked_reason"] = None if active else reason
        updated = self.get_user_by_id(str(user_id))
        if updated is None:
            raise KeyError(user_id)
        return updated

    def soft_delete_user(self, user_id: str) -> None:
        """Deactivate and mark a user deleted without removing related data."""
        now = datetime.now(UTC)
        found = False
        if self.db_session is not None:
            row = self.db_session.execute(
                select(User).where(User.id == str(user_id))
            ).scalar_one_or_none()
            if row is not None:
                row.is_active = False
                row.deleted_at = row.deleted_at or now
                row.locked_reason = row.locked_reason or "soft-deleted"
                self.db_session.commit()
                found = True
        user = self.users.get(str(user_id))
        if user is not None:
            user["is_active"] = False
            user["deleted_at"] = user.get("deleted_at") or now
            user["locked_reason"] = user.get("locked_reason") or "soft-deleted"
            found = True
        if not found:
            raise KeyError(user_id)

    def create_password_reset_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        """Save a new password reset token."""
        token_id = str(uuid.uuid4())

        if self.db_session is not None:
            try:
                token_record = PasswordResetToken(
                    id=token_id,
                    user_id=str(user_id),
                    token_hash=token_hash,
                    expires_at=expires_at,
                    is_used=False,
                )
                self.db_session.add(token_record)
                self.db_session.commit()
            except Exception:
                self.db_session.rollback()
                raise

        rec = {
            "id": token_id,
            "user_id": str(user_id),
            "token_hash": token_hash,
            "expires_at": expires_at,
            "is_used": False,
        }
        self.reset_tokens[token_hash] = rec
        return dict(rec)

    def get_password_reset_token(self, token_hash: str) -> dict[str, Any] | None:
        """Find a reset token by token_hash."""
        if self.db_session is not None:
            try:
                db_token = self.db_session.execute(
                    select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
                ).scalar_one_or_none()
                if db_token is not None:
                    return {
                        "id": db_token.id,
                        "user_id": db_token.user_id,
                        "token_hash": db_token.token_hash,
                        "expires_at": db_token.expires_at,
                        "is_used": db_token.is_used,
                    }
            except Exception:
                pass

        rec = self.reset_tokens.get(token_hash)
        return dict(rec) if rec else None

    def mark_password_reset_token_used(self, token_id_or_hash: str) -> None:
        """Mark a reset token as used."""
        if self.db_session is not None:
            try:
                db_token = self.db_session.execute(
                    select(PasswordResetToken).where(
                        (PasswordResetToken.id == token_id_or_hash)
                        | (PasswordResetToken.token_hash == token_id_or_hash)
                    )
                ).scalar_one_or_none()
                if db_token is not None:
                    db_token.is_used = True
                    self.db_session.commit()
            except Exception:
                self.db_session.rollback()

        for rec in self.reset_tokens.values():
            if rec["id"] == token_id_or_hash or rec["token_hash"] == token_id_or_hash:
                rec["is_used"] = True

    def get_actor(self, user_id: str) -> dict[str, str] | None:
        """Return actor dict containing strictly id, email, and role."""
        user = self.get_user_by_id(user_id)
        if user is None:
            return None
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
        }

    def create_refresh_session(
        self,
        *,
        jti: str,
        user_id: str,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """Persist one active refresh-token session."""
        record = {
            "jti": jti,
            "user_id": user_id,
            "family_id": family_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "revoked_at": None,
            "replaced_by_jti": None,
        }
        with self.auth_session_lock:
            if self.db_session is not None:
                self.db_session.add(
                    RefreshSession(
                        jti=jti,
                        user_id=user_id,
                        family_id=family_id,
                        token_hash=token_hash,
                        expires_at=expires_at,
                    )
                )
                self.db_session.commit()
            self.refresh_sessions[jti] = record

    def get_refresh_session(self, jti: str) -> dict[str, Any] | None:
        """Return a refresh session from DB or memory."""
        if self.db_session is not None:
            row = self.db_session.execute(
                select(RefreshSession).where(RefreshSession.jti == jti)
            ).scalar_one_or_none()
            if row is not None:
                return {
                    "jti": row.jti,
                    "user_id": row.user_id,
                    "family_id": row.family_id,
                    "token_hash": row.token_hash,
                    "expires_at": row.expires_at,
                    "revoked_at": row.revoked_at,
                    "replaced_by_jti": row.replaced_by_jti,
                }
        record = self.refresh_sessions.get(jti)
        return dict(record) if record else None

    def rotate_refresh_session(
        self,
        old_jti: str,
        *,
        new_jti: str,
        user_id: str,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> bool:
        """Atomically revoke one refresh token and replace it once."""
        now = datetime.now(UTC)
        with self.auth_session_lock:
            old = self.get_refresh_session(old_jti)
            if old is None or old.get("revoked_at") is not None:
                return False
            if self.db_session is not None:
                db_old = self.db_session.execute(
                    select(RefreshSession).where(RefreshSession.jti == old_jti)
                ).scalar_one()
                db_old.revoked_at = now
                db_old.replaced_by_jti = new_jti
                self.db_session.add(
                    RefreshSession(
                        jti=new_jti,
                        user_id=user_id,
                        family_id=family_id,
                        token_hash=token_hash,
                        expires_at=expires_at,
                    )
                )
                self.db_session.commit()
            if old_jti in self.refresh_sessions:
                self.refresh_sessions[old_jti]["revoked_at"] = now
                self.refresh_sessions[old_jti]["replaced_by_jti"] = new_jti
            self.refresh_sessions[new_jti] = {
                "jti": new_jti,
                "user_id": user_id,
                "family_id": family_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "revoked_at": None,
                "replaced_by_jti": None,
            }
            return True

    def revoke_refresh_session(self, jti: str) -> None:
        """Revoke a refresh token if it exists; repeated logout is safe."""
        now = datetime.now(UTC)
        with self.auth_session_lock:
            if self.db_session is not None:
                row = self.db_session.execute(
                    select(RefreshSession).where(RefreshSession.jti == jti)
                ).scalar_one_or_none()
                if row is not None and row.revoked_at is None:
                    row.revoked_at = now
                    self.db_session.commit()
            if jti in self.refresh_sessions:
                self.refresh_sessions[jti]["revoked_at"] = now

    def revoke_access_token(self, *, jti: str, user_id: str, expires_at: datetime) -> None:
        """Persist an access-token deny-list entry through its expiry."""
        with self.auth_session_lock:
            if self.db_session is not None:
                existing = self.db_session.execute(
                    select(RevokedAccessToken).where(RevokedAccessToken.jti == jti)
                ).scalar_one_or_none()
                if existing is None:
                    self.db_session.add(
                        RevokedAccessToken(jti=jti, user_id=user_id, expires_at=expires_at)
                    )
                    self.db_session.commit()
            self.revoked_access_tokens[jti] = expires_at

    def is_access_token_revoked(self, jti: str) -> bool:
        """Check the access-token deny list and discard expired memory entries."""
        now = datetime.now(UTC)
        if self.db_session is not None:
            row = self.db_session.execute(
                select(RevokedAccessToken).where(RevokedAccessToken.jti == jti)
            ).scalar_one_or_none()
            if row is not None:
                expires_at = row.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                return expires_at > now
        memory_expiry = self.revoked_access_tokens.get(jti)
        if memory_expiry is None:
            return False
        if memory_expiry.tzinfo is None:
            memory_expiry = memory_expiry.replace(tzinfo=UTC)
        if memory_expiry <= now:
            self.revoked_access_tokens.pop(jti, None)
            return False
        return True

    def create_oauth_state(
        self,
        *,
        state_hash: str,
        provider: str,
        code_verifier: str,
        expires_at: datetime,
    ) -> None:
        """Store a short-lived, single-use OAuth state in application memory."""
        self.oauth_states[state_hash] = {
            "provider": provider,
            "code_verifier": code_verifier,
            "expires_at": expires_at,
        }

    def consume_oauth_state(self, state_hash: str, provider: str) -> dict[str, Any] | None:
        """Atomically consume OAuth state to prevent callback replay."""
        with self.auth_session_lock:
            record = self.oauth_states.pop(state_hash, None)
        if record is None or record.get("provider") != provider:
            return None
        expires_at = record.get("expires_at")
        if not isinstance(expires_at, datetime):
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return dict(record) if expires_at > datetime.now(UTC) else None

    def get_oauth_identity(self, provider: str, subject: str) -> str | None:
        """Resolve an OAuth identity to a local user ID."""
        if self.db_session is not None:
            row = self.db_session.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == provider,
                    OAuthIdentity.subject == subject,
                )
            ).scalar_one_or_none()
            if row is not None:
                return row.user_id
        return self.oauth_identities.get((provider, subject))

    def link_oauth_identity(self, provider: str, subject: str, user_id: str) -> None:
        """Persist a provider subject after verified-email account linking."""
        existing = self.get_oauth_identity(provider, subject)
        if existing is not None and existing != user_id:
            raise ConflictError("OAuth identity is already linked")
        if self.db_session is not None and existing is None:
            self.db_session.add(
                OAuthIdentity(
                    id=str(uuid.uuid4()),
                    provider=provider,
                    subject=subject,
                    user_id=user_id,
                )
            )
            self.db_session.commit()
        self.oauth_identities[(provider, subject)] = user_id

    def get_course_by_id(self, course_id: str) -> dict[str, Any] | None:
        """Find course by ID. Returns copy or None."""
        if self.db_session is not None:
            try:
                c = self.db_session.execute(
                    select(Course).where(Course.id == str(course_id))
                ).scalar_one_or_none()
                if c is not None:
                    return {"id": c.id, "title": c.title, "instructorId": c.instructor_id or ""}
            except Exception:
                pass
        course = self.courses.get(course_id)
        return dict(course) if course else None

    def get_enrollments(self, course_id: str) -> list[dict[str, Any]]:
        """Return all enrollment records for course_id."""
        if self.db_session is not None:
            try:
                enrs = (
                    self.db_session.execute(
                        select(Enrollment).where(Enrollment.course_id == str(course_id))
                    )
                    .scalars()
                    .all()
                )
                if enrs:
                    return [{"studentId": e.student_id, "score": e.score} for e in enrs]
            except Exception:
                pass
        return [
            {"studentId": rec["studentId"], "score": rec["score"]}
            for (c_id, _s_id), rec in self.enrollments.items()
            if c_id == course_id
        ]

    def get_enrollment(self, course_id: str, student_id: str) -> dict[str, Any] | None:
        """Find enrollment record for (course_id, student_id)."""
        if self.db_session is not None:
            try:
                e = self.db_session.execute(
                    select(Enrollment).where(
                        (Enrollment.course_id == str(course_id))
                        & (Enrollment.student_id == str(student_id))
                    )
                ).scalar_one_or_none()
                if e is not None:
                    return {"courseId": e.course_id, "studentId": e.student_id, "score": e.score}
            except Exception:
                pass
        rec = self.enrollments.get((course_id, student_id))
        return dict(rec) if rec else None

    def update_score(
        self, course_id: str, student_id: str, new_score: float
    ) -> tuple[dict[str, Any], float]:
        """Update grade for (course_id, student_id). Returns (updated_record, old_score)."""
        old_score: float | None = None
        if self.db_session is not None:
            try:
                e = self.db_session.execute(
                    select(Enrollment).where(
                        (Enrollment.course_id == str(course_id))
                        & (Enrollment.student_id == str(student_id))
                    )
                ).scalar_one_or_none()
                if e is not None:
                    old_score = float(e.score)
                    e.score = float(new_score)
                    self.db_session.commit()
            except Exception:
                self.db_session.rollback()

        key = (course_id, student_id)
        rec = self.enrollments.get(key)
        if rec is None and old_score is None:
            raise KeyError(f"Enrollment not found for course {course_id} and student {student_id}")

        if rec is not None:
            if old_score is None:
                old_score = float(rec["score"])
            rec["score"] = float(new_score)
            return dict(rec), old_score

        updated_record = {
            "courseId": course_id,
            "studentId": student_id,
            "score": float(new_score),
        }
        return updated_record, float(old_score or 0.0)

    def create_course(
        self,
        course_id: str,
        title: str,
        instructor_id: str,
        description: str = "",
        duration_hours: int = 30,
        thumbnail: str = "",
    ) -> dict[str, Any]:
        """Create and persist a course."""
        cid = str(course_id)
        if self.db_session is not None:
            try:
                c = Course(id=cid, title=title, instructor_id=instructor_id)
                self.db_session.add(c)
                self.db_session.commit()
            except Exception:
                self.db_session.rollback()

        course_rec = {
            "id": cid,
            "title": title,
            "instructorId": instructor_id,
            "description": description,
            "durationHours": duration_hours,
            "thumbnail": thumbnail
            or "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600",
            "isFeatured": False,
            "lessons": [{"id": f"{cid}-l1", "title": "Bài 1: Giới thiệu & Tổng quan"}],
        }
        self.courses[cid] = course_rec
        return dict(course_rec)

    def enroll_student(self, course_id: str, student_id: str) -> dict[str, Any]:
        """Enroll student in a course with initial score 0.0."""
        cid = str(course_id)
        sid = str(student_id)
        if (cid, sid) in self.enrollments:
            raise ValueError(f"Student {sid} is already enrolled in course {cid}")

        if self.db_session is not None:
            try:
                enr = Enrollment(course_id=cid, student_id=sid, score=0.0)
                self.db_session.add(enr)
                self.db_session.commit()
            except Exception:
                self.db_session.rollback()

        rec = {
            "courseId": cid,
            "studentId": sid,
            "score": 0.0,
            "enrolledAt": datetime.now(UTC).strftime("%Y-%m-%d"),
            "completedLessons": [],
        }
        self.enrollments[(cid, sid)] = rec
        return dict(rec)

    def add_lesson(self, course_id: str, title: str) -> dict[str, Any]:
        """Add a lesson to a course."""
        cid = str(course_id)
        course = self.courses.get(cid)
        if not course:
            raise KeyError(f"Course {cid} not found")

        lessons = course.setdefault("lessons", [])
        lesson_id = f"{cid}-l{len(lessons) + 1}"
        lesson = {"id": lesson_id, "title": title}
        lessons.append(lesson)
        return dict(lesson)

    def complete_lesson(self, course_id: str, student_id: str, lesson_id: str) -> dict[str, Any]:
        """Mark a lesson as completed for an enrolled student."""
        cid = str(course_id)
        sid = str(student_id)
        key = (cid, sid)
        enr = self.enrollments.get(key)
        if not enr:
            raise KeyError(f"Enrollment not found for student {sid} in course {cid}")

        completed = enr.setdefault("completedLessons", [])
        if lesson_id not in completed:
            completed.append(lesson_id)

        course = self.courses.get(cid, {})
        total_lessons = len(course.get("lessons", []))
        completed_count = len(completed)
        progress = round(completed_count / total_lessons * 100) if total_lessons > 0 else 100

        return {
            "courseId": cid,
            "studentId": sid,
            "completedLessons": list(completed),
            "progress": progress,
        }

    def create_assignment(
        self,
        course_id: str,
        title: str,
        description: str = "",
        max_score: float = 10.0,
        assignment_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist an assignment."""
        aid = assignment_id or str(uuid.uuid4())
        rec = {
            "id": aid,
            "courseId": str(course_id),
            "title": title,
            "description": description,
            "maxScore": float(max_score),
            "createdAt": datetime.now(UTC).isoformat(),
        }
        self.assignments[aid] = rec
        return dict(rec)

    def get_assignments(self, course_id: str) -> list[dict[str, Any]]:
        """Return all assignments for a course."""
        return [dict(a) for a in self.assignments.values() if a.get("courseId") == str(course_id)]

    def get_assignment_by_id(self, assignment_id: str) -> dict[str, Any] | None:
        """Find assignment by ID."""
        rec = self.assignments.get(str(assignment_id))
        return dict(rec) if rec else None

    def submit_assignment(
        self,
        assignment_id: str,
        student_id: str,
        content: str,
    ) -> dict[str, Any]:
        """Submit an assignment solution."""
        aid = str(assignment_id)
        sid = str(student_id)
        sub_id = str(uuid.uuid4())
        rec = {
            "id": sub_id,
            "assignmentId": aid,
            "studentId": sid,
            "content": content,
            "score": None,
            "feedback": "",
            "submittedAt": datetime.now(UTC).isoformat(),
        }
        self.submissions[(aid, sid)] = rec
        self.all_submissions.append(rec)
        return dict(rec)

    def _resolve_default_assignment_id(self, course_id: str) -> str:
        """Find first assignment for course or generate a default one."""
        existing = self.get_assignments(course_id)
        if existing:
            return str(existing[0]["id"])
        if self.db_session is not None:
            try:
                db_a = (
                    self.db_session.execute(
                        select(Assignment).where(Assignment.course_id == str(course_id))
                    )
                    .scalars()
                    .first()
                )
                if db_a:
                    return str(db_a.id)
            except Exception:
                pass
        created = self.create_assignment(
            course_id=course_id,
            title=f"Bài tập môn {course_id.upper()}",
            description="Bài nộp định kỳ qua hệ thống miniLMS",
            max_score=10.0,
        )
        return str(created["id"])

    def submit_assignment_vulnerable(
        self,
        course_id: str,
        student_id: str,
        content: str,
        assignment_id: str | None = None,
    ) -> dict[str, Any]:
        """Vulnerable assignment submission simulating delay (time.sleep(1)).

        Race conditions or double-clicks will create multiple duplicate submission records.
        """
        aid = (
            str(assignment_id)
            if assignment_id
            else self._resolve_default_assignment_id(str(course_id))
        )

        # Giả lập delay 1s theo đặc tả 02_idempotency_key_pattern.md
        time.sleep(1.0)

        sub_id = str(uuid.uuid4())
        rec = {
            "id": sub_id,
            "assignmentId": aid,
            "courseId": str(course_id),
            "studentId": str(student_id),
            "content": str(content),
            "score": None,
            "feedback": "",
            "submittedAt": datetime.now(UTC).isoformat(),
        }
        self.all_submissions.append(rec)
        self.submissions[(aid, str(student_id))] = rec

        if self.db_session is not None:
            try:
                db_sub = Submission(
                    id=sub_id,
                    assignment_id=aid,
                    student_id=str(student_id),
                    content=str(content),
                )
                self.db_session.add(db_sub)
                self.db_session.commit()
            except Exception:
                self.db_session.rollback()

        return dict(rec)

    def submit_assignment_secure(
        self,
        course_id: str,
        student_id: str,
        content: str,
        idempotency_key: str,
        assignment_id: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Patched assignment submission protected by Idempotency Key pattern.

        Logic:
        1. Check key in idempotency_cache (thread-safe).
        2. If key is PROCESSING -> raise ConflictError (409 Conflict).
        3. If key is COMPLETED -> return cached response (200 OK) without duplicate.
        4. If key is new -> mark PROCESSING, execute, mark COMPLETED -> return 201.
        """
        key = str(idempotency_key).strip()
        if not key:
            raise ValidationError("Idempotency-Key header is required")

        with self.idempotency_lock:
            # Check in-memory cache
            cached = self.idempotency_cache.get(key)
            if cached is not None:
                status = cached.get("status")
                if status == "PROCESSING":
                    raise ConflictError("Request is currently being processed")
                if status == "COMPLETED":
                    return cached.get("response", {}), 200

            # Check PostgreSQL idempotency_records table if active
            if self.db_session is not None:
                try:
                    db_rec = self.db_session.execute(
                        select(IdempotencyRecord).where(IdempotencyRecord.key == key)
                    ).scalar_one_or_none()
                    if db_rec is not None:
                        if db_rec.status == "PROCESSING":
                            raise ConflictError("Request is currently being processed")
                        if db_rec.status == "COMPLETED":
                            resp_data = (
                                json.loads(db_rec.response_body) if db_rec.response_body else {}
                            )
                            self.idempotency_cache[key] = {
                                "status": "COMPLETED",
                                "response": resp_data,
                                "statusCode": 200,
                            }
                            return resp_data, 200
                except ConflictError:
                    raise
                except Exception:
                    pass

            # Mark key as PROCESSING
            self.idempotency_cache[key] = {
                "status": "PROCESSING",
                "userId": str(student_id),
                "courseId": str(course_id),
                "createdAt": datetime.now(UTC).isoformat(),
            }
            if self.db_session is not None:
                try:
                    db_rec = IdempotencyRecord(
                        key=key,
                        user_id=str(student_id),
                        endpoint="/assignments/submit-secure",
                        status="PROCESSING",
                    )
                    self.db_session.add(db_rec)
                    self.db_session.commit()
                except Exception:
                    self.db_session.rollback()

        # Execute business logic
        try:
            aid = (
                str(assignment_id)
                if assignment_id
                else self._resolve_default_assignment_id(str(course_id))
            )
            sub_id = str(uuid.uuid4())
            rec = {
                "id": sub_id,
                "assignmentId": aid,
                "courseId": str(course_id),
                "studentId": str(student_id),
                "content": str(content),
                "score": None,
                "feedback": "",
                "submittedAt": datetime.now(UTC).isoformat(),
            }
            self.all_submissions.append(rec)
            self.submissions[(aid, str(student_id))] = rec

            if self.db_session is not None:
                try:
                    db_sub = Submission(
                        id=sub_id,
                        assignment_id=aid,
                        student_id=str(student_id),
                        content=str(content),
                    )
                    self.db_session.add(db_sub)
                    self.db_session.commit()
                except Exception:
                    self.db_session.rollback()

            resp_payload = {
                "message": "Nộp bài thành công",
                "submission": rec,
                "idempotencyKey": key,
            }

            with self.idempotency_lock:
                self.idempotency_cache[key] = {
                    "status": "COMPLETED",
                    "userId": str(student_id),
                    "response": resp_payload,
                    "statusCode": 201,
                    "completedAt": datetime.now(UTC).isoformat(),
                }
                if self.db_session is not None:
                    try:
                        db_rec = self.db_session.execute(
                            select(IdempotencyRecord).where(IdempotencyRecord.key == key)
                        ).scalar_one_or_none()
                        if db_rec:
                            db_rec.status = "COMPLETED"
                            db_rec.response_code = 201
                            db_rec.response_body = json.dumps(resp_payload)
                            db_rec.completed_at = datetime.now(UTC)
                            self.db_session.commit()
                    except Exception:
                        self.db_session.rollback()

            return resp_payload, 201

        except Exception as exc:
            with self.idempotency_lock:
                self.idempotency_cache.pop(key, None)
                if self.db_session is not None:
                    try:
                        db_rec = self.db_session.execute(
                            select(IdempotencyRecord).where(IdempotencyRecord.key == key)
                        ).scalar_one_or_none()
                        if db_rec:
                            self.db_session.delete(db_rec)
                            self.db_session.commit()
                    except Exception:
                        self.db_session.rollback()
            raise exc

    def get_all_submissions(
        self,
        student_id: str | None = None,
        course_id: str | None = None,
        assignment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all submissions recorded, allowing inspection of duplicates."""
        results = []
        for s in self.all_submissions:
            if student_id and s.get("studentId") != str(student_id):
                continue
            if course_id and s.get("courseId") != str(course_id):
                continue
            if assignment_id and s.get("assignmentId") != str(assignment_id):
                continue
            results.append(dict(s))
        return results

    def get_submission_by_id(self, submission_id: str) -> dict[str, Any] | None:
        """Find submission by id across all recorded submissions."""
        sid = str(submission_id)
        for s in self.all_submissions:
            if s.get("id") == sid:
                return dict(s)
        for s in self.submissions.values():
            if s.get("id") == sid:
                return dict(s)
        return None

    def get_submissions(self, assignment_id: str) -> list[dict[str, Any]]:
        """Return all submissions for an assignment."""
        aid = str(assignment_id)
        results = []
        for (a_id, s_id), sub in self.submissions.items():
            if a_id == aid:
                student = self.get_user_by_id(s_id)
                sub_copy = dict(sub)
                sub_copy["studentEmail"] = student.get("email", "") if student else ""
                sub_copy["studentName"] = student.get("fullName", "") if student else ""
                results.append(sub_copy)
        return results

    def grade_submission(
        self,
        assignment_id: str,
        student_id: str,
        score: float,
        feedback: str = "",
    ) -> tuple[dict[str, Any], float | None]:
        """Update grade for a student's assignment submission."""
        aid = str(assignment_id)
        sid = str(student_id)
        sub = self.submissions.get((aid, sid))
        if not sub:
            raise KeyError(f"Submission not found for assignment {aid} and student {sid}")
        old_score = sub.get("score")
        sub["score"] = float(score)
        sub["feedback"] = str(feedback)
        return dict(sub), (float(old_score) if old_score is not None else None)

    def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve sanitized profile for user_id (no password hash)."""
        user = self.users.get(user_id)
        if not user:
            return None
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "fullName": user["fullName"],
            "phone": user["phone"],
            "bio": user["bio"],
            "avatarUrl": user["avatarUrl"],
            "notifications": dict(user["notifications"]),
        }

    def update_user_profile(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Safely update editable user profile fields.

        Enforces Defense in Depth: prevents modification of id, role, or password hash.
        """
        user = self.users.get(user_id)
        if not user:
            raise KeyError(f"User '{user_id}' not found")

        old_email = str(user["email"])
        new_email = str(payload.get("email", old_email)).strip().lower()
        existing = self.users_by_email.get(new_email)
        if existing is not None and str(existing.get("id")) != str(user_id):
            raise ConflictError("Email is already in use")

        if "fullName" in payload:
            user["fullName"] = str(payload["fullName"]).strip()
        if "phone" in payload:
            user["phone"] = str(payload["phone"]).strip()
        if "bio" in payload:
            user["bio"] = str(payload["bio"]).strip()
        if "avatarUrl" in payload:
            user["avatarUrl"] = str(payload["avatarUrl"]).strip()
        if "email" in payload:
            self.users_by_email.pop(old_email, None)
            user["email"] = new_email
            self.users_by_email[new_email] = user

        if self.db_session is not None:
            try:
                db_user = self.db_session.execute(
                    select(User).where(User.id == str(user_id))
                ).scalar_one_or_none()
                if db_user is not None:
                    db_user.email = new_email
                    db_user.full_name = str(user.get("fullName", ""))
                    db_user.phone_number = str(user.get("phone", "")) or None
                    db_user.bio = str(user.get("bio", ""))
                    db_user.avatar_url = str(user.get("avatarUrl", "")) or None
                    self.db_session.commit()
            except Exception:
                self.db_session.rollback()
                raise

        return self.get_user_profile(user_id) or {}

    def update_user_password(
        self, user_id: str, old_password_or_hash: str, new_password: str | None = None
    ) -> None:
        """Safely update user password.

        Supports both:
        - update_user_password(user_id, new_password_hash) [Reset password token flow]
        - update_user_password(user_id, old_password, new_password) [Account change password flow]
        """
        from lms_project_1.errors import InvalidCredentials, NotFound

        user = self.get_user_by_id(user_id)
        if not user:
            raise NotFound(f"User '{user_id}' not found")

        if new_password is not None:
            # Change password flow: verify old_password against existing hash
            current_hash = user["password_hash"]
            if not bcrypt.checkpw(
                old_password_or_hash.encode("utf-8"), current_hash.encode("utf-8")
            ):
                raise InvalidCredentials("Mật khẩu hiện tại không chính xác")
            salt = bcrypt.gensalt(rounds=10)
            target_hash = bcrypt.hashpw(new_password.encode("utf-8"), salt).decode("utf-8")
        else:
            # Reset password flow: old_password_or_hash is either raw new password or bcrypt hash
            if old_password_or_hash.startswith("$2"):
                target_hash = old_password_or_hash
            else:
                salt = bcrypt.gensalt(rounds=10)
                target_hash = bcrypt.hashpw(old_password_or_hash.encode("utf-8"), salt).decode(
                    "utf-8"
                )

        # Update in-memory storage
        raw_u = self.users.get(str(user_id)) or self.users.get(str(user["id"]))
        if raw_u:
            raw_u["password_hash"] = target_hash
        email = str(user.get("email", "")).strip().lower()
        if email in self.users_by_email:
            self.users_by_email[email]["password_hash"] = target_hash

        # Update database if DB session is active
        if self.db_session is not None:
            try:
                db_u = self.db_session.execute(
                    select(User).where(User.id == str(user_id))
                ).scalar_one_or_none()
                if db_u is not None:
                    db_u.hashed_password = target_hash
                    self.db_session.commit()
            except Exception:
                self.db_session.rollback()

    def update_user_notifications(self, user_id: str, settings: dict[str, Any]) -> dict[str, bool]:
        """Update user notification preferences."""
        from lms_project_1.errors import NotFound

        user = self.users.get(user_id)
        if not user:
            raise NotFound(f"User '{user_id}' not found")

        notifs = user["notifications"]
        for key in ("emailNewCourses", "emailAssignments", "emailGradeUpdates"):
            if key in settings:
                notifs[key] = bool(settings[key])

        return dict(notifs)

    def get_home_dashboard(self, user_id: str) -> dict[str, Any]:
        """Retrieve complete home dashboard data in a single pass (Zero N+1 Query)."""
        from lms_project_1.errors import NotFound

        user = self.users.get(user_id)
        if not user:
            raise NotFound(f"User '{user_id}' not found")

        # 1. Single pass over user enrollments
        enrolled_courses: list[dict[str, Any]] = []
        enrolled_course_ids: set[str] = set()
        total_completed = 0
        total_hours = 0

        for (c_id, s_id), rec in self.enrollments.items():
            if s_id != user_id:
                continue

            enrolled_course_ids.add(c_id)
            course = self.courses.get(c_id, {})
            instructor_id = course.get("instructorId", "")
            instructor = self.users.get(instructor_id, {})
            instructor_name = instructor.get("fullName") or instructor.get("email", "Giảng viên")

            lessons = course.get("lessons", [])
            completed_lessons = set(rec.get("completedLessons", []))
            total_lessons_cnt = len(lessons)
            completed_cnt = len(completed_lessons)

            if total_lessons_cnt > 0:
                progress_pct = round(completed_cnt / total_lessons_cnt * 100)
            else:
                progress_pct = 100 if rec["score"] >= 5.0 else 0

            is_completed = (progress_pct >= 100) or (rec["score"] >= 8.5)
            if is_completed:
                total_completed += 1
                total_hours += course.get("durationHours", 30)
            else:
                total_hours += int(course.get("durationHours", 30) * (progress_pct / 100))

            # Next lesson calculation
            next_lesson_id = ""
            next_lesson_title = "Hoàn thành toàn bộ khóa học"
            for lesson in lessons:
                if lesson["id"] not in completed_lessons:
                    next_lesson_id = lesson["id"]
                    next_lesson_title = lesson["title"]
                    break

            enrolled_courses.append(
                {
                    "id": c_id,
                    "title": course.get("title", ""),
                    "thumbnail": course.get("thumbnail", ""),
                    "instructor": instructor_name,
                    "progress": progress_pct,
                    "isCompleted": is_completed,
                    "score": rec["score"],
                    "nextLessonId": next_lesson_id,
                    "nextLessonTitle": next_lesson_title,
                }
            )

        # 2. Featured / Recommended courses (user has not enrolled)
        featured_courses: list[dict[str, Any]] = []
        for c_id, course in self.courses.items():
            if c_id in enrolled_course_ids:
                continue
            inst = self.users.get(course.get("instructorId", ""), {})
            inst_name = inst.get("fullName") or inst.get("email", "Giảng viên miniLMS")
            featured_courses.append(
                {
                    "id": c_id,
                    "title": course.get("title", ""),
                    "description": course.get("description", ""),
                    "thumbnail": course.get("thumbnail", ""),
                    "instructor": inst_name,
                    "duration": f"{course.get('durationHours', 30)} giờ",
                    "isFeatured": course.get("isFeatured", False),
                }
            )

        return {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
                "fullName": user["fullName"],
                "avatarUrl": user["avatarUrl"],
            },
            "stats": {
                "completedCourses": total_completed,
                "inProgressCourses": len(enrolled_courses) - total_completed,
                "totalHours": total_hours,
                "certificates": total_completed,
            },
            "enrolledCourses": enrolled_courses,
            "featuredCourses": featured_courses,
        }

    def get_account_data(self, user_id: str) -> dict[str, Any]:
        """Retrieve profile, learning history, and notification settings for account page."""
        from lms_project_1.errors import NotFound

        user = self.users.get(user_id)
        if not user:
            raise NotFound(f"User '{user_id}' not found")

        # Build learning history
        history: list[dict[str, Any]] = []
        for (c_id, s_id), rec in self.enrollments.items():
            if s_id != user_id:
                continue
            course = self.courses.get(c_id, {})
            score = rec["score"]
            is_completed = score >= 8.5
            history.append(
                {
                    "courseId": c_id,
                    "courseTitle": course.get("title", "Khóa học"),
                    "enrolledAt": rec.get("enrolledAt", "2026-02-15"),
                    "status": "Đã hoàn thành" if is_completed else "Đang học",
                    "score": score,
                }
            )

        return {
            "profile": {
                "id": user["id"],
                "email": user["email"],
                "role": user["role"],
                "fullName": user["fullName"],
                "phone": user["phone"],
                "bio": user["bio"],
                "avatarUrl": user["avatarUrl"],
            },
            "history": history,
            "notifications": dict(user["notifications"]),
        }


def load_store(seed_path: str | Path | None = None) -> Store:
    """Create and return a freshly loaded Store instance."""
    return Store(seed_path=seed_path)
