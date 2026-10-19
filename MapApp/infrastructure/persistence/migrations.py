"""Small, deterministic SQL migration runner."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from MapApp.domain.errors import PersistenceFailed


MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]+)_[a-z0-9_]+\.sql$")


def default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "migrations"


def _migration_files(directory: Path) -> list[tuple[int, Path]]:
    migrations: list[tuple[int, Path]] = []
    for path in directory.glob("*.sql"):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise PersistenceFailed("The database migrations are invalid.")
        version = int(match.group("version"))
        if version == 0:
            raise PersistenceFailed("The database migrations are invalid.")
        migrations.append((version, path))
    migrations.sort(key=lambda item: item[0])
    versions = [version for version, _ in migrations]
    if not migrations or len(versions) != len(set(versions)):
        raise PersistenceFailed("The database migrations are invalid.")
    return migrations


def apply_migrations(
    connection: sqlite3.Connection,
    directory: str | Path | None = None,
    *,
    applied_at: int | None = None,
) -> tuple[int, ...]:
    migration_dir = Path(directory) if directory is not None else default_migrations_dir()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at INTEGER NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        pending = [(version, path) for version, path in _migration_files(migration_dir) if version not in applied]
        timestamp = int(time.time()) if applied_at is None else applied_at
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise PersistenceFailed("The migration timestamp is invalid.")
        completed: list[int] = []
        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                f"INSERT INTO schema_migrations(version, applied_at) VALUES ({version}, {timestamp});\n"
                "COMMIT;"
            )
            try:
                connection.executescript(script)
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            completed.append(version)
        return tuple(completed)
    except (OSError, sqlite3.Error) as exc:
        raise PersistenceFailed("The local database could not be initialized.") from exc
