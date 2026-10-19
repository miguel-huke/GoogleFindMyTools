"""Read-only queries that project SQLite entities into sanitized public DTOs."""

from __future__ import annotations

from collections.abc import Callable

from MapApp.domain.errors import DomainValidationError, NotFoundError
from MapApp.domain.models import Beacon, LocationKind, LocationReport
from MapApp.domain.ports import UnitOfWork

from .dto import DeviceSummary, LocationPoint, PublicLocation, SemanticLocation


UnitOfWorkFactory = Callable[[], UnitOfWork]


class QueryMapState:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def list_devices(self) -> list[DeviceSummary]:
        with self._unit_of_work_factory() as transaction:
            beacons = transaction.beacons.list_active()
            latest = {
                location.beacon_id: location
                for location in transaction.locations.latest_by_beacon()
            }
        return [self._device_summary(beacon, latest.get(beacon.id)) for beacon in beacons]

    def get_device(self, public_id: str) -> DeviceSummary:
        with self._unit_of_work_factory() as transaction:
            beacon = transaction.beacons.get_by_public_id(public_id)
            latest = transaction.locations.latest_by_beacon() if beacon is not None else []
        if beacon is None:
            raise NotFoundError()
        latest_by_id = next(
            (location for location in latest if location.beacon_id == beacon.id),
            None,
        )
        return self._device_summary(beacon, latest_by_id)

    def history(self, public_id: str, *, limit: int = 100) -> list[PublicLocation]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise DomainValidationError("limit")
        with self._unit_of_work_factory() as transaction:
            beacon = transaction.beacons.get_by_public_id(public_id)
            if beacon is None or beacon.id is None:
                raise NotFoundError()
            history = transaction.locations.history(beacon.id, limit)
        return [self._public_location(location) for location in history]

    @staticmethod
    def _device_summary(beacon: Beacon, latest: LocationReport | None) -> DeviceSummary:
        return DeviceSummary(
            public_id=beacon.public_id,
            name=beacon.display_name,
            active=beacon.is_active,
            type=beacon.device_type,
            manufacturer=beacon.manufacturer,
            model=beacon.model,
            latest_location=(
                QueryMapState._public_location(latest) if latest is not None else None
            ),
        )

    @staticmethod
    def _public_location(location: LocationReport) -> PublicLocation:
        report = location.report
        if report.kind is LocationKind.SEMANTIC:
            return SemanticLocation(
                name=report.semantic_name,
                observed_at=report.observed_at,
                status=report.status.value,
            )
        return LocationPoint(
            latitude=report.latitude,
            longitude=report.longitude,
            altitude=report.altitude,
            accuracy=report.accuracy,
            observed_at=report.observed_at,
            status=report.status.value,
            own_report=report.is_own_report,
        )
