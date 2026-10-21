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

            user_record: dict[str, Any] = {
                "id": str(u["id"]),
                "email": str(u["email"]).strip().lower(),
                "role": str(u["role"]),
                "password_hash": pwd_hash,
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


def load_store(seed_path: str | Path | None = None) -> Store:
    """Create and return a freshly loaded Store instance."""
    return Store(seed_path=seed_path)
