"""Small, dependency-free runner for versioned EduShield SQL migrations.

The runner deliberately supports only status and forward upgrades. Rollback remains
an operator-reviewed procedure because a generic automatic downgrade can destroy
production data.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, inspect, text

from lms_project_1.database import get_database_url, normalize_db_url
from lms_project_1.models import Base

DEFAULT_MIGRATION_ROOT = Path(__file__).resolve().parents[2] / "database" / "migrations"
MIGRATION_PATTERN = re.compile(
    r"^(?P<version>\d{4})_(?P<feature>[a-z]+_\d+)_(?P<name>[a-z0-9_]+)\.up\.sql$"
)


class MigrationError(RuntimeError):
    """Base exception for invalid or failed migrations."""


class MigrationChecksumError(MigrationError):
    """Raised when an applied migration file has been modified."""


class MigrationSchemaError(MigrationError):
    """Raised when SQL migrations and SQLAlchemy models are out of sync."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable forward SQL migration."""

    version: int
    feature_id: str
    name: str
    path: Path
    checksum: str


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """Observed state of a migration without mutating the database."""

    migration: Migration
    state: str


def load_migrations(migration_root: Path | None = None) -> list[Migration]:
    """Load and validate ordered ``*.up.sql`` migrations from disk."""
    root = migration_root or DEFAULT_MIGRATION_ROOT
    if not root.is_dir():
        raise MigrationError(f"Migration directory does not exist: {root}")

    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(root.glob("*.up.sql")):
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in seen_versions:
            raise MigrationError(f"Duplicate migration version: {version:04d}")
        seen_versions.add(version)
        raw_sql = path.read_bytes()
        migrations.append(
            Migration(
                version=version,
                feature_id=match.group("feature").replace("_", "-").upper(),
                name=match.group("name"),
                path=path,
                checksum=hashlib.sha256(raw_sql).hexdigest(),
            )
        )

    actual_versions = [migration.version for migration in migrations]
    expected_versions = list(range(1, len(migrations) + 1))
    if actual_versions != expected_versions:
        raise MigrationError(
            f"Migration versions must be contiguous from 0001; found {actual_versions or 'none'}"
        )
    return migrations


def migration_status(
    engine: Engine,
    migration_root: Path | None = None,
) -> list[MigrationStatus]:
    """Return migration states without creating tables or applying SQL."""
    migrations = load_migrations(migration_root)
    if not inspect(engine).has_table("schema_migrations"):
        return [MigrationStatus(migration, "pending") for migration in migrations]

    with engine.connect() as connection:
        applied = _load_applied(connection)
    return [
        MigrationStatus(
            migration,
            (
                "pending"
                if migration.version not in applied
                else "applied"
                if applied[migration.version] == migration.checksum
                else "modified"
            ),
        )
        for migration in migrations
    ]


def upgrade(engine: Engine, migration_root: Path | None = None) -> list[Migration]:
    """Apply every pending migration once in a database transaction."""
    migrations = load_migrations(migration_root)
    applied_now: list[Migration] = []

    with engine.begin() as connection:
        _create_migration_table(connection)
        applied = _load_applied(connection)
        known_versions = {migration.version for migration in migrations}
        unknown_versions = sorted(set(applied) - known_versions)
        if unknown_versions:
            raise MigrationError(
                "Database contains migration versions missing from this checkout: "
                f"{unknown_versions}"
            )

        for migration in migrations:
            recorded_checksum = applied.get(migration.version)
            if recorded_checksum is not None:
                if recorded_checksum != migration.checksum:
                    raise MigrationChecksumError(
                        f"Migration {migration.version:04d} checksum differs from the applied SQL"
                    )
                continue

            sql = migration.path.read_text(encoding="utf-8")
            for statement in _split_sql_statements(sql):
                connection.exec_driver_sql(statement)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations "
                    "(version, feature_id, name, checksum) "
                    "VALUES (:version, :feature_id, :name, :checksum)"
                ),
                {
                    "version": migration.version,
                    "feature_id": migration.feature_id,
                    "name": migration.name,
                    "checksum": migration.checksum,
                },
            )
            applied_now.append(migration)

        _verify_model_schema(connection)

    return applied_now


def _create_migration_table(connection: Connection) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            feature_id VARCHAR(20) NOT NULL,
            name VARCHAR(255) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _load_applied(connection: Connection) -> dict[int, str]:
    rows = connection.execute(
        text("SELECT version, checksum FROM schema_migrations ORDER BY version")
    ).all()
    return {int(row.version): str(row.checksum) for row in rows}


def _verify_model_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(Base.metadata.tables) - actual_tables)
    if missing_tables:
        raise MigrationSchemaError(f"Migration is missing ORM tables: {missing_tables}")

    missing_columns: list[str] = []
    for table in Base.metadata.sorted_tables:
        actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in actual_columns:
                missing_columns.append(f"{table.name}.{column.name}")
    if missing_columns:
        raise MigrationSchemaError(f"Migration is missing ORM columns: {missing_columns}")


def _split_sql_statements(sql: str) -> list[str]:
    """Split ordinary DDL while respecting quotes and SQL comments.

    Migration files intentionally avoid stored procedures and PostgreSQL dollar-quoted
    blocks; those need an explicit runner extension before use.
    """
    statements: list[str] = []
    current: list[str] = []
    index = 0
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False

    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                current.append(char)
            index += 1
            continue
        if in_block_comment:
            if char == "*" and following == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if not in_single_quote and not in_double_quote:
            if char == "-" and following == "-":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and following == "*":
                in_block_comment = True
                index += 2
                continue
        if char == "'" and not in_double_quote:
            current.append(char)
            if in_single_quote and following == "'":
                current.append(following)
                index += 2
                continue
            in_single_quote = not in_single_quote
            index += 1
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            index += 1
            continue
        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue
        current.append(char)
        index += 1

    if in_single_quote or in_double_quote or in_block_comment:
        raise MigrationError("Migration SQL contains an unterminated quote or comment")
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: ``python -m lms_project_1.migrations``."""
    parser = argparse.ArgumentParser(description="EduShield versioned SQL migrations")
    parser.add_argument("command", choices=("status", "upgrade"))
    parser.add_argument("--database-url", help="Overrides DATABASE_URL")
    args = parser.parse_args(argv)
    database_url = args.database_url or get_database_url()
    if not database_url:
        parser.error("DATABASE_URL or --database-url is required")

    engine = create_engine(normalize_db_url(database_url), pool_pre_ping=True)
    try:
        if args.command == "status":
            for item in migration_status(engine):
                print(f"{item.migration.version:04d} {item.migration.feature_id} {item.state}")
            return 0

        applied = upgrade(engine)
        if not applied:
            print("Database is already up to date")
        for migration in applied:
            print(f"Applied {migration.version:04d} {migration.feature_id} {migration.name}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
