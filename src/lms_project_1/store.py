"""In-memory data store for miniLMS reloaded from seed.json per application factory call."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bcrypt


class Store:
    """In-memory store loading and holding isolated state from seed.json.

    All passwords are hashed with bcrypt (cost >= 10) on boot and plain passwords
    are never retained in memory.
    """

    def __init__(
        self,
        seed_path: str | Path | None = None,
        seed_data: dict[str, Any] | None = None,
    ) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.users_by_email: dict[str, dict[str, Any]] = {}
        self.courses: dict[str, dict[str, Any]] = {}
        # Key: (courseId, studentId) -> {"courseId": ..., "studentId": ..., "score": float}
        self.enrollments: dict[tuple[str, str], dict[str, Any]] = {}

        if seed_data is not None:
            self._load_data(seed_data)
        else:
            path = self._resolve_seed_path(seed_path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._load_data(data)

    def _resolve_seed_path(self, seed_path: str | Path | None) -> Path:
        if seed_path is not None:
            return Path(seed_path)
        # Search current working directory, module directory, and parent directories
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
                "fullName": str(u.get("fullName") or default_name),
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
                "lessons": list(c.get("lessons", default_lessons)),
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

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Find user by ID. Returns copy or None."""
        user = self.users.get(user_id)
        return dict(user) if user else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Find user by email (case-insensitive). Returns copy or None."""
        user = self.users_by_email.get(email.strip().lower())
        return dict(user) if user else None

    def get_actor(self, user_id: str) -> dict[str, str] | None:
        """Return actor dict containing strictly id, email, and role."""
        user = self.users.get(user_id)
        if user is None:
            return None
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
        }

    def get_course_by_id(self, course_id: str) -> dict[str, Any] | None:
        """Find course by ID. Returns copy or None."""
        course = self.courses.get(course_id)
        return dict(course) if course else None

    def get_enrollments(self, course_id: str) -> list[dict[str, Any]]:
        """Return all enrollment records for course_id."""
        return [
            {"studentId": rec["studentId"], "score": rec["score"]}
            for (c_id, _s_id), rec in self.enrollments.items()
            if c_id == course_id
        ]

    def get_enrollment(self, course_id: str, student_id: str) -> dict[str, Any] | None:
        """Find enrollment record for (course_id, student_id)."""
        rec = self.enrollments.get((course_id, student_id))
        return dict(rec) if rec else None

    def update_score(
        self, course_id: str, student_id: str, new_score: float
    ) -> tuple[dict[str, Any], float]:
        """Update grade for (course_id, student_id). Returns (updated_record, old_score)."""
        key = (course_id, student_id)
        rec = self.enrollments.get(key)
        if rec is None:
            raise KeyError(f"Enrollment not found for course {course_id} and student {student_id}")
        old_score = float(rec["score"])
        rec["score"] = float(new_score)
        return dict(rec), old_score

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

        Enforces Defense in Depth: strictly prevents modification of id, email, role,
        or password_hash.
        """
        user = self.users.get(user_id)
        if not user:
            raise KeyError(f"User '{user_id}' not found")

        if "fullName" in payload:
            user["fullName"] = str(payload["fullName"]).strip()
        if "phone" in payload:
            user["phone"] = str(payload["phone"]).strip()
        if "bio" in payload:
            user["bio"] = str(payload["bio"]).strip()
        if "avatarUrl" in payload:
            user["avatarUrl"] = str(payload["avatarUrl"]).strip()

        return self.get_user_profile(user_id) or {}

    def update_user_password(self, user_id: str, old_password: str, new_password: str) -> None:
        """Safely change user password after verifying current password against bcrypt hash."""
        from lms_project_1.errors import InvalidCredentials, NotFound

        user = self.users.get(user_id)
        if not user:
            raise NotFound(f"User '{user_id}' not found")

        current_hash = user["password_hash"]
        if not bcrypt.checkpw(old_password.encode("utf-8"), current_hash.encode("utf-8")):
            raise InvalidCredentials("Mật khẩu hiện tại không chính xác")

        salt = bcrypt.gensalt(rounds=10)
        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), salt).decode("utf-8")
        user["password_hash"] = new_hash

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
