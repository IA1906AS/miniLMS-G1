"""Tests for the versioned SQL migration runner (FND-03)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from lms_project_1.migrations import (
    MigrationChecksumError,
    load_migrations,
    migration_status,
    upgrade,
)
from lms_project_1.models import Base


def test_baseline_migration_creates_current_orm_schema(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")

    applied = upgrade(engine)

    assert [migration.version for migration in applied] == list(range(1, 15))
    actual_tables = set(inspect(engine).get_table_names())
    expected_tables = set(Base.metadata.tables)
    assert expected_tables <= actual_tables
    assert "schema_migrations" in actual_tables

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT version, feature_id FROM schema_migrations ORDER BY version")
        ).all()
    assert rows == [
        (1, "FND-03"),
        (2, "AUTH-02"),
        (3, "AUTH-03"),
        (4, "USR-02"),
        (5, "USR-03"),
        (6, "CRS-03"),
        (7, "CRS-05"),
        (8, "CRS-06"),
        (9, "CRS-04"),
        (10, "CRS-07"),
        (11, "LRN-01"),
        (12, "LRN-03"),
        (13, "LRN-04"),
        (14, "LRN-05"),
    ]

    assert upgrade(engine) == []
    assert [item.state for item in migration_status(engine)] == ["applied"] * 14
    engine.dispose()


def test_upgrade_rejects_modified_applied_migration(tmp_path: Path) -> None:
    sources = [migration.path for migration in load_migrations()]
    migration_root = tmp_path / "migrations"
    migration_root.mkdir()
    for source in sources:
        (migration_root / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    target = migration_root / sources[0].name
    engine = create_engine(f"sqlite:///{tmp_path / 'checksum.db'}")

    upgrade(engine, migration_root=migration_root)
    target.write_text(
        target.read_text(encoding="utf-8") + "\n-- migration was modified\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationChecksumError, match="checksum"):
        upgrade(engine, migration_root=migration_root)
    engine.dispose()


def test_status_does_not_apply_pending_migration(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'status.db'}")

    status = migration_status(engine)

    assert [item.state for item in status] == ["pending"] * 14
    assert "schema_migrations" not in inspect(engine).get_table_names()
    engine.dispose()
