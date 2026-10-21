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

            user_record: dict[str, Any] = {
                "id": str(u["id"]),
                "email": str(u["email"]).strip().lower(),
                "role": str(u["role"]),
                "password_hash": pwd_hash,
                "full_name": str(u.get("name", u.get("email", ""))),
                "is_active": True,
                "is_verified": True,
            }
            self.users[user_record["id"]] = user_record
            self.users_by_email[user_record["email"]] = user_record

        raw_courses = data.get("courses", [])
        for c in raw_courses:
            course_record: dict[str, Any] = {
                "id": str(c["id"]),
                "title": str(c.get("title", "")),
                "instructorId": str(c.get("instructorId", "")),
            }
            self.courses[course_record["id"]] = course_record

        raw_enrollments = data.get("enrollments", [])
        for e in raw_enrollments:
            course_id = str(e["courseId"])
            student_id = str(e["studentId"])
            score = float(e["score"])
            enrollment_record: dict[str, Any] = {
                "courseId": course_id,
                "studentId": student_id,
                "score": score,
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

    def update_user_password(self, user_id: str, new_password_hash: str) -> bool:
        """Update user hashed_password in DB and memory."""
        updated = False
        if self.db_session is not None:
            try:
                db_user = self.db_session.execute(
                    select(User).where(User.id == str(user_id))
                ).scalar_one_or_none()
                if db_user is not None:
                    db_user.hashed_password = new_password_hash
                    self.db_session.commit()
                    updated = True
            except Exception:
                self.db_session.rollback()

        if str(user_id) in self.users:
            self.users[str(user_id)]["password_hash"] = new_password_hash
            email = self.users[str(user_id)]["email"]
            if email in self.users_by_email:
                self.users_by_email[email]["password_hash"] = new_password_hash
            updated = True

        return updated

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


def load_store(seed_path: str | Path | None = None) -> Store:
    """Create and return a freshly loaded Store instance."""
    return Store(seed_path=seed_path)
