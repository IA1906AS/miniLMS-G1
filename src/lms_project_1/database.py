"""Database connection management and initialization using SQLAlchemy."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import bcrypt
from flask import Flask
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from lms_project_1.models import Base, Course, Enrollment, User

DEFAULT_POSTGRES_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/lms_db"


def normalize_db_url(url: str) -> str:
    """Ensure PostgreSQL URLs use the psycopg (psycopg3) driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def get_database_url(config: dict[str, Any] | None = None) -> str | None:
    """Retrieve database URL from config or environment."""
    url = (config.get("DATABASE_URL") if config else None) or os.environ.get("DATABASE_URL")
    if url:
        return normalize_db_url(url)
    return None


def init_db(
    app: Flask,
    database_url: str | None = None,
    create_tables: bool = True,
    seed_if_empty: bool = True,
) -> scoped_session[Session] | None:
    """Initialize database engine and scoped session for the Flask app."""
    url = database_url or get_database_url(app.config)
    if not url:
        return None

    try:
        engine_kwargs: dict[str, Any] = {"echo": False}
        if "sqlite" in url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_pre_ping"] = True

        engine: Engine = create_engine(url, **engine_kwargs)

        if create_tables:
            Base.metadata.create_all(bind=engine)

        session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_session: scoped_session[Session] = scoped_session(session_factory)

        app.db_engine = engine  # type: ignore[attr-defined]
        app.db_session = db_session  # type: ignore[attr-defined]
        app.config["DB_SESSION"] = db_session

        @app.teardown_appcontext
        def shutdown_session(exception: BaseException | None = None) -> None:
            db_session.remove()

        if seed_if_empty:
            seed_db(db_session)

        return db_session
    except Exception as exc:
        app.logger.warning(f"Could not connect to database at {url}: {exc}")
        return None


def seed_db(
    session: scoped_session[Session] | Session,
    seed_path: str | Path | None = None,
) -> None:
    """Populate database from seed.json if users table is empty."""
    # Check if users already exist
    existing_user = session.execute(select(User).limit(1)).scalar_one_or_none()
    if existing_user is not None:
        return

    path = _resolve_seed_path(seed_path)
    if not path.is_file():
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # 1. Seed users
    for u in data.get("users", []):
        plain_pwd = str(u.get("password", ""))
        salt = bcrypt.gensalt(rounds=10)
        pwd_hash = bcrypt.hashpw(plain_pwd.encode("utf-8"), salt).decode("utf-8")
        role_val = str(u.get("role", "guest")).lower()
        # Normalise teacher / instructor
        if role_val == "instructor":
            role_val = "teacher"

        user = User(
            id=str(u["id"]),
            email=str(u["email"]).strip().lower(),
            hashed_password=pwd_hash,
            full_name=str(u.get("name", u.get("email", ""))),
            role=role_val,
            is_active=True,
            is_verified=True,
        )
        session.add(user)

    # 2. Seed courses
    for c in data.get("courses", []):
        course = Course(
            id=str(c["id"]),
            title=str(c.get("title", "")),
            instructor_id=str(c.get("instructorId", "")),
        )
        session.add(course)

    # 3. Seed enrollments
    for e in data.get("enrollments", []):
        enrollment = Enrollment(
            course_id=str(e["courseId"]),
            student_id=str(e["studentId"]),
            score=float(e["score"]),
        )
        session.add(enrollment)

    session.commit()


def _resolve_seed_path(seed_path: str | Path | None) -> Path:
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
