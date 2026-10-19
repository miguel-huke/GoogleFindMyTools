import tempfile
import unittest
from pathlib import Path

from MapApp.application.sync_devices import SyncDevices
from MapApp.domain.errors import GoogleUnavailable, MalformedGoogleResponse, PersistenceFailed
from MapApp.domain.models import DiscoveredBeacon, SyncState
from MapApp.infrastructure.persistence import SQLiteUnitOfWork


class FakeClock:
    def __init__(self, *timestamps):
        self._timestamps = iter(timestamps)

    def now_utc_seconds(self):
        return next(self._timestamps)


class FakeGateway:
    def __init__(self, beacons=None, error=None):
        self.beacons = beacons or []
        self.error = error
        self.calls = 0

    def list_beacons(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.beacons

    def locate(self, _canonic_id, _timeout_seconds):
        raise AssertionError("SyncDevices must not request locations")


class SyncDevicesIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "sync.db"
        self.public_ids = iter(("public-1", "public-2", "public-3", "public-4"))
        self.job_ids = iter(("job-1", "job-2", "job-3"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def uow(self):
        return SQLiteUnitOfWork(
            self.database_path,
            id_factory=lambda: next(self.public_ids),
        )

    def use_case(self, gateway, *timestamps):
        return SyncDevices(
            gateway,
            self.uow,
            clock=FakeClock(*timestamps),
            job_id_factory=lambda: next(self.job_ids),
        )

    def test_sync_persists_inventory_and_successful_run(self):
        gateway = FakeGateway(
            [
                DiscoveredBeacon("backend-1", "Chaves", "DEVICE_TYPE_KEYS"),
                DiscoveredBeacon("backend-2", "Mochila", "DEVICE_TYPE_BAG"),
            ]
        )
        result = self.use_case(gateway, 100, 110).execute()
        self.assertEqual(result.status, SyncState.SUCCEEDED)
        self.assertEqual(result.devices_discovered, 2)
        self.assertEqual(gateway.calls, 1)
        with self.uow() as transaction:
            beacons = transaction.beacons.list_active()
            stored_run = transaction.sync_runs.get("job-1")
        self.assertEqual({item.canonic_id for item in beacons}, {"backend-1", "backend-2"})
        self.assertEqual({item.public_id for item in beacons}, {"public-1", "public-2"})
        self.assertEqual(stored_run, result)

    def test_repeated_sync_is_idempotent_and_updates_metadata(self):
        first_gateway = FakeGateway([DiscoveredBeacon("backend-1", "Nome antigo")])
        first = self.use_case(first_gateway, 100, 110).execute()
        with self.uow() as transaction:
            original = transaction.beacons.list_active()[0]

        second_gateway = FakeGateway(
            [DiscoveredBeacon("backend-1", "Nome novo", manufacturer="Acme")]
        )
        second = self.use_case(second_gateway, 200, 210).execute()
        with self.uow() as transaction:
            beacons = transaction.beacons.list_active()
            first_run = transaction.sync_runs.get(first.id)
            second_run = transaction.sync_runs.get(second.id)
        self.assertEqual(len(beacons), 1)
        self.assertEqual(beacons[0].public_id, original.public_id)
        self.assertEqual(beacons[0].first_seen_at, 110)
        self.assertEqual(beacons[0].last_discovered_at, 210)
        self.assertEqual(beacons[0].display_name, "Nome novo")
        self.assertEqual(beacons[0].manufacturer, "Acme")
        self.assertEqual(first_run.status, SyncState.SUCCEEDED)
        self.assertEqual(second_run.status, SyncState.SUCCEEDED)

    def test_absent_beacon_is_not_automatically_deactivated(self):
        self.use_case(
            FakeGateway(
                [DiscoveredBeacon("backend-1", "Primeiro"), DiscoveredBeacon("backend-2", "Segundo")]
            ),
            100,
            110,
        ).execute()
        self.use_case(FakeGateway([DiscoveredBeacon("backend-1", "Primeiro")]), 200, 210).execute()
        with self.uow() as transaction:
            active = transaction.beacons.list_active()
        self.assertEqual({item.canonic_id for item in active}, {"backend-1", "backend-2"})

    def test_gateway_failure_is_recorded_without_sensitive_detail(self):
        gateway = FakeGateway(error=GoogleUnavailable())
        with self.assertRaises(GoogleUnavailable):
            self.use_case(gateway, 100, 120).execute()
        with self.uow() as transaction:
            run = transaction.sync_runs.get("job-1")
            beacons = transaction.beacons.list_active()
        self.assertEqual(run.status, SyncState.FAILED)
        self.assertEqual(run.error_code, "google_unavailable")
        self.assertNotIn("token", run.error_message.lower())
        self.assertEqual(beacons, [])

    def test_duplicate_gateway_identity_is_rejected_before_upsert(self):
        gateway = FakeGateway(
            [DiscoveredBeacon("duplicate", "One"), DiscoveredBeacon("duplicate", "Two")]
        )
        with self.assertRaises(MalformedGoogleResponse):
            self.use_case(gateway, 100, 120).execute()
        with self.uow() as transaction:
            self.assertEqual(transaction.beacons.list_active(), [])
            run = transaction.sync_runs.get("job-1")
        self.assertEqual(run.status, SyncState.FAILED)
        self.assertEqual(run.error_code, "malformed_google_response")

    def test_upsert_failure_rolls_back_all_beacons_and_marks_run_failed(self):
        def colliding_uow():
            return SQLiteUnitOfWork(self.database_path, id_factory=lambda: "same-public-id")

        gateway = FakeGateway(
            [DiscoveredBeacon("backend-1", "One"), DiscoveredBeacon("backend-2", "Two")]
        )
        use_case = SyncDevices(
            gateway,
            colliding_uow,
            clock=FakeClock(100, 110, 120),
            job_id_factory=lambda: "job-collision",
        )
        with self.assertRaises(PersistenceFailed):
            use_case.execute()
        with colliding_uow() as transaction:
            self.assertEqual(transaction.beacons.list_active(), [])
            run = transaction.sync_runs.get("job-collision")
        self.assertEqual(run.status, SyncState.FAILED)
        self.assertEqual(run.error_code, "persistence_failed")


if __name__ == "__main__":
    unittest.main()
