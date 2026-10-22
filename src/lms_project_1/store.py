"""Data store for miniLMS supporting both in-memory cache and PostgreSQL database."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session, scoped_session

from lms_project_1.models import Course, Enrollment, PasswordResetToken, User


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
        # Key: (courseId, studentId) -> {"courseId": ..., "studentId": ..., "score": float}
        self.enrollments: dict[tuple[str, str], dict[str, Any]] = {}
        # In-memory reset tokens: token_hash -> record dict
        self.reset_tokens: dict[str, dict[str, Any]] = {}

        if seed_data is not None:
            self._load_data(seed_data)
        else:
            path = self._resolve_seed_path(seed_path)
            if path.is_file():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._load_data(data)

    def set_session(self, session: scoped_session[Session] | Session | None) -> None:
        """Bind an active database session."""
        self.db_session = session

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
            "is_active": is_active,
            "is_verified": is_verified,
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
