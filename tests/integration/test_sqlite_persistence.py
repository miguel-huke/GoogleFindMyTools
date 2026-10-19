import tempfile
import unittest
from pathlib import Path

from MapApp.domain.errors import PersistenceFailed
from MapApp.domain.models import (
    DiscoveredBeacon,
    LocationKind,
    LocationReport,
    LocationStatus,
    RawLocationReport,
    SyncOperation,
    SyncRun,
    SyncState,
)
from MapApp.infrastructure.persistence import SQLiteUnitOfWork, apply_migrations, open_database


class SQLitePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.db"
        self.public_ids = iter(("public-1", "public-2", "public-3"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def uow(self):
        return SQLiteUnitOfWork(self.database_path, id_factory=lambda: next(self.public_ids))

    def create_beacon(self):
        with self.uow() as transaction:
            beacon = transaction.beacons.upsert_discovered(
                DiscoveredBeacon("backend-device-1", "Tag sintética", "tracker"),
                now=100,
            )
            transaction.commit()
        return beacon

    @staticmethod
    def point(beacon, observed_at, latitude=-23.5):
        raw = RawLocationReport(
            kind=LocationKind.POINT,
            observed_at=observed_at,
            status=LocationStatus.CROWDSOURCED,
            is_own_report=False,
            latitude=latitude,
            longitude=-46.6,
            altitude=-5,
            accuracy=8,
        )
        return LocationReport.create(
            beacon_id=beacon.id,
            beacon_public_id=beacon.public_id,
            report=raw,
            received_at=observed_at + 1,
        )

    def test_migrations_are_ordered_idempotent_and_enable_pragmas(self):
        connection = open_database(self.database_path)
        try:
            self.assertEqual(apply_migrations(connection, applied_at=10), (1, 2))
            self.assertEqual(apply_migrations(connection, applied_at=20), ())
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            self.assertEqual([row["version"] for row in versions], [1, 2])
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            columns = {
                row["name"]
                for table in ("beacons", "location_reports", "sync_runs")
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            self.assertTrue(
                {"token", "cookie", "android_id", "pin", "key", "encrypted"}.isdisjoint(columns)
            )
        finally:
            connection.close()

    def test_beacon_upsert_preserves_public_id_and_first_seen(self):
        first = self.create_beacon()
        with self.uow() as transaction:
            updated = transaction.beacons.upsert_discovered(
                DiscoveredBeacon("backend-device-1", "Nome atualizado", "tracker", "Acme"),
                now=200,
            )
            transaction.commit()
        self.assertEqual(updated.id, first.id)
        self.assertEqual(updated.public_id, first.public_id)
        self.assertEqual(updated.first_seen_at, 100)
        self.assertEqual(updated.last_discovered_at, 200)
        self.assertEqual(updated.display_name, "Nome atualizado")
        self.assertEqual(updated.manufacturer, "Acme")

    def test_commit_survives_reopen_and_uncommitted_work_rolls_back(self):
        beacon = self.create_beacon()
        with self.uow() as transaction:
            self.assertEqual(transaction.beacons.get_by_public_id(beacon.public_id), beacon)
        with self.uow() as transaction:
            transaction.beacons.upsert_discovered(
                DiscoveredBeacon("rolled-back", "Não persistir"), now=300
            )
        with self.uow() as transaction:
            names = [item.display_name for item in transaction.beacons.list_active()]
        self.assertEqual(names, ["Tag sintética"])

    def test_location_insert_is_idempotent_and_history_is_ordered(self):
        beacon = self.create_beacon()
        older = self.point(beacon, 110, latitude=-23.5)
        newer = self.point(beacon, 120, latitude=-23.6)
        with self.uow() as transaction:
            first = transaction.locations.add_many([older, newer])
            repeated = transaction.locations.add_many([older])
            history = transaction.locations.history(beacon.id, limit=10)
            latest = transaction.locations.latest_by_beacon()
            transaction.commit()
        self.assertEqual((first.inserted, first.duplicated), (2, 0))
        self.assertEqual((repeated.inserted, repeated.duplicated), (0, 1))
        self.assertEqual([item.report.observed_at for item in history], [120, 110])
        self.assertEqual([item.report.observed_at for item in latest], [120])
        self.assertEqual(latest[0].report.altitude, -5)

    def test_semantic_report_is_stored_but_not_used_as_map_latest(self):
        beacon = self.create_beacon()
        semantic = RawLocationReport(
            kind=LocationKind.SEMANTIC,
            observed_at=130,
            status=LocationStatus.SEMANTIC,
            is_own_report=True,
            semantic_name="Casa sintética",
        )
        location = LocationReport.create(
            beacon_id=beacon.id,
            beacon_public_id=beacon.public_id,
            report=semantic,
            received_at=131,
        )
        with self.uow() as transaction:
            transaction.locations.add_many([location])
            transaction.commit()
        with self.uow() as transaction:
            self.assertEqual(transaction.locations.history(beacon.id, 10)[0].report.semantic_name, "Casa sintética")
            self.assertEqual(transaction.locations.latest_by_beacon(), [])

    def test_foreign_key_failure_is_typed_and_transaction_is_rolled_back(self):
        raw = RawLocationReport(
            kind=LocationKind.POINT,
            observed_at=100,
            status=LocationStatus.LAST_KNOWN,
            is_own_report=True,
            latitude=0,
            longitude=0,
        )
        orphan = LocationReport.create(
            beacon_id=999,
            beacon_public_id="public-missing",
            report=raw,
            received_at=101,
        )
        with self.assertRaises(PersistenceFailed):
            with self.uow() as transaction:
                transaction.locations.add_many([orphan])

    def test_sync_run_round_trip_and_update(self):
        pending = SyncRun("job-1", SyncOperation.REFRESH_ALL, SyncState.PENDING)
        completed = SyncRun(
            "job-1",
            SyncOperation.REFRESH_ALL,
            SyncState.SUCCEEDED,
            started_at=100,
            finished_at=120,
            reports_received=2,
            reports_inserted=2,
        )
        with self.uow() as transaction:
            transaction.sync_runs.add(pending)
            transaction.sync_runs.update(completed)
            transaction.commit()
        with self.uow() as transaction:
            restored = transaction.sync_runs.get("job-1")
        self.assertEqual(restored, completed)


if __name__ == "__main__":
    unittest.main()
