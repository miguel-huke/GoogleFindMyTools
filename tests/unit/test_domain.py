import json
import math
import unittest

from MapApp.application.dto import DeviceSummary, LocationPoint, SemanticLocation, SyncStatus
from MapApp.domain.errors import DomainValidationError, LocationTimeout
from MapApp.domain.models import (
    Beacon,
    LocationKind,
    LocationReport,
    LocationStatus,
    RawLocationReport,
    SyncOperation,
    SyncRun,
    SyncState,
)


class LocationDomainTest(unittest.TestCase):
    def make_point(self, **changes):
        values = {
            "kind": LocationKind.POINT,
            "observed_at": 1_700_000_000,
            "status": LocationStatus.CROWDSOURCED,
            "is_own_report": False,
            "latitude": -23.5,
            "longitude": -46.6,
            "accuracy": 12.0,
        }
        values.update(changes)
        return RawLocationReport(**values)

    def test_point_accepts_coordinate_limits(self):
        point = self.make_point(latitude=-90, longitude=180, altitude=-12, accuracy=0)
        self.assertEqual(point.latitude, -90.0)
        self.assertEqual(point.longitude, 180.0)
        self.assertEqual(point.altitude, -12)

    def test_point_rejects_absent_invalid_or_non_finite_coordinates(self):
        for changes in (
            {"latitude": None},
            {"latitude": -90.01},
            {"longitude": 180.01},
            {"latitude": math.nan},
            {"longitude": math.inf},
            {"accuracy": -0.1},
        ):
            with self.subTest(changes=changes), self.assertRaises(DomainValidationError):
                self.make_point(**changes)

    def test_semantic_location_requires_name_and_discards_coordinates(self):
        report = RawLocationReport(
            kind=LocationKind.SEMANTIC,
            observed_at=10,
            status=LocationStatus.SEMANTIC,
            is_own_report=True,
            latitude=10,
            longitude=20,
            semantic_name="  Casa  ",
        )
        self.assertEqual(report.semantic_name, "Casa")
        self.assertIsNone(report.latitude)
        self.assertIsNone(report.longitude)
        with self.assertRaises(DomainValidationError):
            RawLocationReport(
                kind=LocationKind.SEMANTIC,
                observed_at=10,
                status=LocationStatus.SEMANTIC,
                is_own_report=True,
            )

    def test_dedup_key_is_stable_and_uses_public_identity(self):
        point = self.make_point()
        first = LocationReport.create(
            beacon_id=1,
            beacon_public_id="public-a",
            report=point,
            received_at=1_700_000_010,
        )
        repeated = LocationReport.create(
            beacon_id=99,
            beacon_public_id="public-a",
            report=point,
            received_at=1_800_000_000,
        )
        other = LocationReport.create(
            beacon_id=1,
            beacon_public_id="public-b",
            report=point,
            received_at=1_700_000_010,
        )
        self.assertEqual(first.dedup_key, repeated.dedup_key)
        self.assertNotEqual(first.dedup_key, other.dedup_key)
        self.assertEqual(len(first.dedup_key), 64)


class CoreModelTest(unittest.TestCase):
    def test_beacon_requires_ordered_timestamps_and_nonempty_ids(self):
        beacon = Beacon(None, "public-1", "backend-id", "Tag", 10, 20)
        self.assertEqual(beacon.display_name, "Tag")
        with self.assertRaises(DomainValidationError):
            Beacon(None, "", "backend-id", "Tag", 10, 20)
        with self.assertRaises(DomainValidationError):
            Beacon(None, "public-1", "backend-id", "Tag", 20, 10)

    def test_sync_run_validates_time_and_counters(self):
        run = SyncRun("job-1", SyncOperation.SYNC_DEVICES, SyncState.SUCCEEDED, 10, 11, 2)
        self.assertEqual(run.devices_discovered, 2)
        with self.assertRaises(DomainValidationError):
            SyncRun("job-2", SyncOperation.REFRESH_ALL, SyncState.FAILED, 20, 10)

    def test_typed_error_contains_only_safe_contract(self):
        error = LocationTimeout()
        self.assertEqual(error.code, "location_timeout")
        self.assertTrue(error.retryable)
        self.assertNotIn("token", str(error).lower())


class PublicDtoTest(unittest.TestCase):
    def test_device_dto_serializes_nested_location_without_private_fields(self):
        dto = DeviceSummary(
            public_id="public-1",
            name="Tag",
            active=True,
            type="tracker",
            latest_location=LocationPoint(-23.5, -46.6, 100, "LAST_KNOWN", False),
        )
        serialized = json.dumps(dto.to_dict())
        for forbidden in ("canonic_id", "token", "cookie", "encrypted", "android_id"):
            self.assertNotIn(forbidden, serialized.lower())
        self.assertIn("latest_location", serialized)

    def test_semantic_and_sync_dtos_validate_public_values(self):
        semantic = SemanticLocation("Casa", 100, "SEMANTIC")
        status = SyncStatus("job-1", "REFRESH_ALL", "RUNNING", 0.5)
        self.assertEqual(semantic.to_dict()["name"], "Casa")
        self.assertEqual(status.to_dict()["progress"], 0.5)
        with self.assertRaises(DomainValidationError):
            SyncStatus("job-2", "REFRESH_ALL", "RUNNING", 1.1)


if __name__ == "__main__":
    unittest.main()
