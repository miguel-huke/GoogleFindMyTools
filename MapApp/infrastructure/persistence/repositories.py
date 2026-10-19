"""SQLite repository implementations with domain-only return values."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable

from MapApp.domain.errors import NotFoundError, PersistenceFailed
from MapApp.domain.models import (
    Beacon,
    DiscoveredBeacon,
    InsertSummary,
    LocationKind,
    LocationReport,
    LocationStatus,
    RawLocationReport,
    SyncOperation,
    SyncRun,
    SyncState,
)
from MapApp.domain.validation import require_non_negative_int


def _beacon_from_row(row: sqlite3.Row) -> Beacon:
    return Beacon(
        id=row["id"],
        public_id=row["public_id"],
        canonic_id=row["canonic_id"],
        display_name=row["display_name"],
        first_seen_at=row["first_seen_at"],
        last_discovered_at=row["last_discovered_at"],
        is_active=bool(row["is_active"]),
        device_type=row["device_type"],
        manufacturer=row["manufacturer"],
        model=row["model"],
        image_url=row["image_url"],
    )


def _location_from_row(row: sqlite3.Row) -> LocationReport:
    report = RawLocationReport(
        kind=LocationKind(row["kind"]),
        observed_at=row["observed_at"],
        status=LocationStatus(row["status"]),
        is_own_report=bool(row["is_own_report"]),
        latitude=row["latitude"],
        longitude=row["longitude"],
        altitude=row["altitude"],
        accuracy=row["accuracy"],
        semantic_name=row["semantic_name"],
    )
    return LocationReport(row["id"], row["beacon_id"], report, row["dedup_key"], row["received_at"])


def _sync_run_from_row(row: sqlite3.Row) -> SyncRun:
    return SyncRun(
        id=row["id"],
        operation=SyncOperation(row["operation"]),
        status=SyncState(row["status"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        devices_discovered=row["devices_discovered"],
        reports_received=row["reports_received"],
        reports_inserted=row["reports_inserted"],
        reports_duplicated=row["reports_duplicated"],
        beacon_public_id=row["beacon_public_id"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


class SQLiteBeaconRepository:
    def __init__(self, connection: sqlite3.Connection, id_factory: Callable[[], str] | None = None) -> None:
        self._connection = connection
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    def upsert_discovered(self, beacon: DiscoveredBeacon, now: int) -> Beacon:
        timestamp = require_non_negative_int(now, "now")
        try:
            existing = self._connection.execute(
                "SELECT * FROM beacons WHERE canonic_id = ?",
                (beacon.canonic_id,),
            ).fetchone()
            if existing is None:
                public_id = self._id_factory()
                cursor = self._connection.execute(
                    """
                    INSERT INTO beacons (
                        public_id, canonic_id, display_name, device_type, manufacturer,
                        model, image_url, is_active, first_seen_at, last_discovered_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        public_id,
                        beacon.canonic_id,
                        beacon.display_name,
                        beacon.device_type,
                        beacon.manufacturer,
                        beacon.model,
                        beacon.image_url,
                        timestamp,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
                row = self._connection.execute(
                    "SELECT * FROM beacons WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            else:
                self._connection.execute(
                    """
                    UPDATE beacons
                    SET display_name = ?, device_type = ?, manufacturer = ?, model = ?,
                        image_url = ?, is_active = 1, last_discovered_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        beacon.display_name,
                        beacon.device_type,
                        beacon.manufacturer,
                        beacon.model,
                        beacon.image_url,
                        timestamp,
                        timestamp,
                        existing["id"],
                    ),
                )
                row = self._connection.execute(
                    "SELECT * FROM beacons WHERE id = ?", (existing["id"],)
                ).fetchone()
            return _beacon_from_row(row)
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def get_by_public_id(self, public_id: str) -> Beacon | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM beacons WHERE public_id = ?", (public_id,)
            ).fetchone()
            return None if row is None else _beacon_from_row(row)
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def list_active(self) -> list[Beacon]:
        try:
            rows = self._connection.execute(
                "SELECT * FROM beacons WHERE is_active = 1 ORDER BY display_name, public_id"
            ).fetchall()
            return [_beacon_from_row(row) for row in rows]
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc


class SQLiteLocationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add_many(self, reports: list[LocationReport]) -> InsertSummary:
        inserted = 0
        try:
            for location in reports:
                report = location.report
                cursor = self._connection.execute(
                    """
                    INSERT INTO location_reports (
                        beacon_id, kind, latitude, longitude, altitude, accuracy,
                        semantic_name, observed_at, status, is_own_report,
                        dedup_key, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dedup_key) DO NOTHING
                    """,
                    (
                        location.beacon_id,
                        report.kind.value,
                        report.latitude,
                        report.longitude,
                        report.altitude,
                        report.accuracy,
                        report.semantic_name,
                        report.observed_at,
                        report.status.value,
                        int(report.is_own_report),
                        location.dedup_key,
                        location.received_at,
                    ),
                )
                inserted += cursor.rowcount
            return InsertSummary(inserted=inserted, duplicated=len(reports) - inserted)
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def latest_by_beacon(self) -> list[LocationReport]:
        try:
            rows = self._connection.execute(
                "SELECT * FROM beacon_latest_locations ORDER BY beacon_id"
            ).fetchall()
            return [_location_from_row(row) for row in rows]
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def history(self, beacon_id: int, limit: int) -> list[LocationReport]:
        require_non_negative_int(beacon_id, "beacon_id")
        require_non_negative_int(limit, "limit")
        try:
            rows = self._connection.execute(
                """
                SELECT * FROM location_reports
                WHERE beacon_id = ?
                ORDER BY observed_at DESC, id DESC
                LIMIT ?
                """,
                (beacon_id, limit),
            ).fetchall()
            return [_location_from_row(row) for row in rows]
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc


class SQLiteSyncRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @staticmethod
    def _values(run: SyncRun) -> tuple[object, ...]:
        return (
            run.operation.value,
            run.status.value,
            run.beacon_public_id,
            run.started_at,
            run.finished_at,
            run.devices_discovered,
            run.reports_received,
            run.reports_inserted,
            run.reports_duplicated,
            run.error_code,
            run.error_message,
        )

    def add(self, run: SyncRun) -> None:
        try:
            self._connection.execute(
                """
                INSERT INTO sync_runs (
                    id, operation, status, beacon_public_id, started_at, finished_at,
                    devices_discovered, reports_received, reports_inserted,
                    reports_duplicated, error_code, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run.id, *self._values(run)),
            )
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def update(self, run: SyncRun) -> None:
        try:
            cursor = self._connection.execute(
                """
                UPDATE sync_runs SET
                    operation = ?, status = ?, beacon_public_id = ?, started_at = ?,
                    finished_at = ?, devices_discovered = ?, reports_received = ?,
                    reports_inserted = ?, reports_duplicated = ?, error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (*self._values(run), run.id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError()
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc

    def get(self, run_id: str) -> SyncRun | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM sync_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return None if row is None else _sync_run_from_row(row)
        except sqlite3.Error as exc:
            raise PersistenceFailed() from exc
