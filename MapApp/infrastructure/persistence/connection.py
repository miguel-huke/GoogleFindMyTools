"""SQLite connection policy for production and injected test databases."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_BUSY_TIMEOUT_MS = 5_000


def default_database_path() -> Path:
    """Return a per-user data path, never a path inside the repository."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "GoogleFindMyTools" / "find_hub.db"


def open_database(path: str | Path | None = None) -> sqlite3.Connection:
    database_path = Path(path) if path is not None else default_database_path()
    if str(database_path) != ":memory:":
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        str(database_path),
        timeout=DEFAULT_BUSY_TIMEOUT_MS / 1_000,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
