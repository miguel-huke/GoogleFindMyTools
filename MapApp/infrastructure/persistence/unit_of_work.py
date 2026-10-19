"""SQLite transaction boundary implementing the UnitOfWork port."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from MapApp.domain.errors import PersistenceFailed

from .connection import open_database
from .migrations import apply_migrations
from .repositories import SQLiteBeaconRepository, SQLiteLocationRepository, SQLiteSyncRunRepository


class SQLiteUnitOfWork:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        migrations_dir: str | Path | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._database_path = database_path
        self._migrations_dir = migrations_dir
        self._id_factory = id_factory
        self._connection: sqlite3.Connection | None = None
        self._finished = False

    def __enter__(self) -> "SQLiteUnitOfWork":
        if self._connection is not None:
            raise PersistenceFailed("The transaction is already open.")
        connection = open_database(self._database_path)
        try:
            apply_migrations(connection, self._migrations_dir)
            connection.execute("BEGIN")
        except Exception:
            connection.close()
            raise
        self._connection = connection
        self._finished = False
        self.beacons = SQLiteBeaconRepository(connection, self._id_factory)
        self.locations = SQLiteLocationRepository(connection)
        self.sync_runs = SQLiteSyncRunRepository(connection)
        return self

    def commit(self) -> None:
        connection = self._require_connection()
        try:
            connection.commit()
            self._finished = True
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def rollback(self) -> None:
        connection = self._require_connection()
        try:
            connection.rollback()
            self._finished = True
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        connection = self._require_connection()
        try:
            if not self._finished:
                connection.rollback()
        finally:
            connection.close()
            self._connection = None
        return False

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise PersistenceFailed("No database transaction is open.")
        return self._connection
