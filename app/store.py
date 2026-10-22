from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bcrypt


class InMemoryStore:
    def __init__(self) -> None:
        self.users_by_id: dict[str, dict[str, Any]] = {}
        self.users_by_email: dict[str, dict[str, Any]] = {}
        self.id_aliases: dict[str, str] = {}
        self.courses_by_id: dict[str, dict[str, Any]] = {}
        self.enrollments: list[dict[str, Any]] = []
        self.login_attempts: dict[str, dict[str, Any]] = {}
        self.reset_requests: dict[str, str] = {}

    def load_seed(self, seed_path: str | Path = "seed.json") -> None:
        self.users_by_id.clear()
        self.users_by_email.clear()
        self.id_aliases.clear()
        self.courses_by_id.clear()
        self.enrollments.clear()
        self.login_attempts.clear()
        self.reset_requests.clear()

        p = Path(seed_path)
        if not p.is_file():
            candidates = [
                Path.cwd() / "seed.json",
                Path(__file__).resolve().parent / "seed.json",
                Path(__file__).resolve().parent.parent / "seed.json",
            ]
            for c in candidates:
                if c.is_file():
                    p = c
                    break

        raw = json.loads(p.read_text(encoding="utf-8"))
        hash_cache: dict[str, str] = {}

        for u in raw.get("users", []):
            plain_pw = u.get("password", "")
            if plain_pw not in hash_cache:
                hash_cache[plain_pw] = bcrypt.hashpw(
                    plain_pw.encode("utf-8"), bcrypt.gensalt(rounds=10)
                ).decode("utf-8")

            uid = str(u["id"]).strip()
            email = str(u["email"]).strip().lower()
            role = str(u["role"]).strip().upper()
            if role == "TEACHER":
                role = "INSTRUCTOR"

            user_record = {
                "id": uid,
                "email": email,
                "password_hash": hash_cache[plain_pw],
                "role": role,
                "fullName": u.get("fullName", u.get("full_name", email.split("@")[0])),
            }
            self.users_by_id[uid] = user_record
            self.users_by_email[email] = user_record

            if uid.isdigit():
                self.id_aliases[f"u{uid}"] = uid
                self.id_aliases[uid] = uid
            elif uid.startswith("u") and uid[1:].isdigit():
                self.id_aliases[uid[1:]] = uid
                self.id_aliases[uid] = uid

        for c in raw.get("courses", []):
            cid = str(c["id"]).strip()
            inst_id = self.resolve_user_id(str(c["instructorId"]).strip())
            self.courses_by_id[cid] = {
                "id": cid,
                "title": str(c["title"]),
                "instructorId": inst_id,
                "description": str(c.get("description", "")),
                "thumbnail": str(c.get("thumbnail", "")),
                "durationHours": int(c.get("durationHours", 30)),
                "isFeatured": bool(c.get("isFeatured", False)),
            }

        for e in raw.get("enrollments", []):
            cid = str(e["courseId"]).strip()
            sid = self.resolve_user_id(str(e["studentId"]).strip())
            score = float(e["score"])
            self.enrollments.append(
                {
                    "courseId": cid,
                    "studentId": sid,
                    "score": score,
                }
            )

    def resolve_user_id(self, user_id: str) -> str:
        if user_id in self.users_by_id:
            return user_id
        return self.id_aliases.get(user_id, user_id)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        resolved = self.resolve_user_id(user_id)
        u = self.users_by_id.get(resolved)
        return dict(u) if u else None

    def get_public_actor(self, user_id: str) -> dict[str, str] | None:
        u = self.get_user_by_id(user_id)
        if not u:
            return None
        return {
            "id": u["id"],
            "email": u["email"],
            "role": u["role"],
        }

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        u = self.users_by_email.get(email.strip().lower())
        return dict(u) if u else None


store = InMemoryStore()
