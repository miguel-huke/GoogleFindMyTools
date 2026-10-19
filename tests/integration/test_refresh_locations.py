import tempfile
import unittest
from pathlib import Path

from MapApp.application.refresh_locations import RefreshBeaconLocations
from MapApp.domain.errors import LocationTimeout, MalformedGoogleResponse, NotFoundError
from MapApp.domain.models import (
    DiscoveredBeacon,
    LocationKind,
    LocationStatus,
    RawLocationReport,
    SyncState,
)
from MapApp.infrastructure.persistence import SQLiteUnitOfWork


class FakeClock:
    def __init__(self, *timestamps):
        self._timestamps = iter(timestamps)

    def now_utc_seconds(self):
        return next(self._timestamps)


class FakeGateway:
    def __init__(self, reports=None, error=None):
        self.reports = [] if reports is None else reports
        self.error = error
        self.locate_calls = []

    def list_beacons(self):
        raise AssertionError("RefreshBeaconLocations must not list devices")

    def locate(self, canonic_id, timeout_seconds):
        self.locate_calls.append((canonic_id, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.reports


class RefreshLocationsIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "locations.db"
        self.job_ids = iter(("job-1", "job-2", "job-3"))
        with self.uow() as transaction:
            self.beacon = transaction.beacons.upsert_discovered(
                DiscoveredBeacon("backend-device-1", "Tag sintética"),
                now=50,
            )
            transaction.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def uow(self):
        return SQLiteUnitOfWork(self.database_path, id_factory=lambda: "public-device-1")

    def use_case(self, gateway, *timestamps):
        return RefreshBeaconLocations(
            gateway,
            self.uow,
            clock=FakeClock(*timestamps),
            job_id_factory=lambda: next(self.job_ids),
        )

    @staticmethod
    def point(observed_at, latitude):
        return RawLocationReport(
            kind=LocationKind.POINT,
            observed_at=observed_at,
            status=LocationStatus.CROWDSOURCED,
            is_own_report=False,
            latitude=latitude,
            longitude=-46.6,
            accuracy=5,
        )

    def test_refresh_persists_reports_and_returns_latest_point(self):
        gateway = FakeGateway([self.point(100, -23.5), self.point(120, -23.6)])
        result = self.use_case(gateway, 80, 130).execute(
            self.beacon.public_id,
            timeout_seconds=2.5,
        )
        self.assertEqual(gateway.locate_calls, [("backend-device-1", 2.5)])
        self.assertEqual(result.run.status, SyncState.SUCCEEDED)
        self.assertEqual(result.run.reports_received, 2)
        self.assertEqual((result.insert_summary.inserted, result.insert_summary.duplicated), (2, 0))
        self.assertEqual(result.latest_location.report.observed_at, 120)
        with self.uow() as transaction:
            history = transaction.locations.history(self.beacon.id, 10)
            stored_run = transaction.sync_runs.get("job-1")
        self.assertEqual([item.report.observed_at for item in history], [120, 100])
        self.assertEqual(stored_run, result.run)

    def test_repeated_refresh_deduplicates_without_losing_history(self):
        reports = [self.point(100, -23.5), self.point(120, -23.6)]
        first = self.use_case(FakeGateway(reports), 80, 130).execute(self.beacon.public_id)
        second = self.use_case(FakeGateway(reports), 140, 150).execute(self.beacon.public_id)
        self.assertEqual(first.insert_summary.inserted, 2)
        self.assertEqual((second.insert_summary.inserted, second.insert_summary.duplicated), (0, 2))
        self.assertEqual(second.latest_location.report.observed_at, 120)
        with self.uow() as transaction:
            history = transaction.locations.history(self.beacon.id, 10)
        self.assertEqual(len(history), 2)

    def test_semantic_report_is_history_but_latest_map_location_is_point(self):
        semantic = RawLocationReport(
            kind=LocationKind.SEMANTIC,
            observed_at=130,
            status=LocationStatus.SEMANTIC,
            is_own_report=True,
            semantic_name="Casa sintética",
        )
        result = self.use_case(
            FakeGateway([self.point(120, -23.6), semantic]),
            80,
            140,
        ).execute(self.beacon.public_id)
        self.assertEqual(result.latest_location.report.kind, LocationKind.POINT)
        self.assertEqual(result.latest_location.report.observed_at, 120)
        with self.uow() as transaction:
            history = transaction.locations.history(self.beacon.id, 10)
        self.assertEqual([item.report.kind for item in history], [LocationKind.SEMANTIC, LocationKind.POINT])

    def test_empty_response_keeps_previous_latest_location(self):
        self.use_case(FakeGateway([self.point(100, -23.5)]), 80, 110).execute(
            self.beacon.public_id
        )
        result = self.use_case(FakeGateway([]), 120, 130).execute(self.beacon.public_id)
        self.assertEqual(result.insert_summary.inserted, 0)
        self.assertEqual(result.latest_location.report.observed_at, 100)

    def test_unknown_public_id_is_recorded_and_does_not_call_gateway(self):
        gateway = FakeGateway([self.point(100, -23.5)])
        with self.assertRaises(NotFoundError):
            self.use_case(gateway, 80, 90).execute("unknown-public-id")
        self.assertEqual(gateway.locate_calls, [])
        with self.uow() as transaction:
            run = transaction.sync_runs.get("job-1")
        self.assertEqual(run.status, SyncState.FAILED)
        self.assertEqual(run.error_code, "not_found")

    def test_timeout_is_recorded_without_changing_history(self):
        gateway = FakeGateway(error=LocationTimeout())
        with self.assertRaises(LocationTimeout):
            self.use_case(gateway, 80, 90).execute(self.beacon.public_id, timeout_seconds=0.01)
        with self.uow() as transaction:
            run = transaction.sync_runs.get("job-1")
            history = transaction.locations.history(self.beacon.id, 10)
        self.assertEqual(run.status, SyncState.FAILED)
        self.assertEqual(run.error_code, "location_timeout")
        self.assertEqual(history, [])

    def test_malformed_gateway_result_is_rejected_before_persistence(self):
        gateway = FakeGateway(reports=[{"latitude": -23.5}])
        with self.assertRaises(MalformedGoogleResponse):
            self.use_case(gateway, 80, 90).execute(self.beacon.public_id)
        with self.uow() as transaction:
            self.assertEqual(transaction.locations.history(self.beacon.id, 10), [])


if __name__ == "__main__":
    unittest.main()
