"""Framework-independent entities and value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import DomainValidationError
from .validation import (
    build_location_dedup_key,
    latitude,
    longitude,
    optional_accuracy,
    optional_int,
    optional_non_negative_int,
    optional_text,
    require_non_negative_int,
    require_text,
)


class LocationKind(StrEnum):
    POINT = "POINT"
    SEMANTIC = "SEMANTIC"


class LocationStatus(StrEnum):
    SEMANTIC = "SEMANTIC"
    LAST_KNOWN = "LAST_KNOWN"
    CROWDSOURCED = "CROWDSOURCED"
    AGGREGATED = "AGGREGATED"


class SyncOperation(StrEnum):
    CONNECT = "CONNECT"
    SYNC_DEVICES = "SYNC_DEVICES"
    REFRESH_ONE = "REFRESH_ONE"
    REFRESH_ALL = "REFRESH_ALL"


class SyncState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class DiscoveredBeacon:
    canonic_id: str
    display_name: str
    device_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    image_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonic_id", require_text(self.canonic_id, "canonic_id"))
        object.__setattr__(self, "display_name", require_text(self.display_name, "display_name"))
        for field in ("device_type", "manufacturer", "model", "image_url"):
            object.__setattr__(self, field, optional_text(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class Beacon:
    id: int | None
    public_id: str
    canonic_id: str
    display_name: str
    first_seen_at: int
    last_discovered_at: int
    is_active: bool = True
    device_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    image_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", optional_non_negative_int(self.id, "id"))
        object.__setattr__(self, "public_id", require_text(self.public_id, "public_id"))
        object.__setattr__(self, "canonic_id", require_text(self.canonic_id, "canonic_id"))
        object.__setattr__(self, "display_name", require_text(self.display_name, "display_name"))
        object.__setattr__(self, "first_seen_at", require_non_negative_int(self.first_seen_at, "first_seen_at"))
        object.__setattr__(
            self,
            "last_discovered_at",
            require_non_negative_int(self.last_discovered_at, "last_discovered_at"),
        )
        if self.last_discovered_at < self.first_seen_at:
            raise DomainValidationError("last_discovered_at")
        if not isinstance(self.is_active, bool):
            raise DomainValidationError("is_active")
        for field in ("device_type", "manufacturer", "model", "image_url"):
            object.__setattr__(self, field, optional_text(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class RawLocationReport:
    """Validated gateway output before it is associated with a local beacon row."""

    kind: LocationKind
    observed_at: int
    status: LocationStatus
    is_own_report: bool
    latitude: float | None = None
    longitude: float | None = None
    altitude: int | None = None
    accuracy: float | None = None
    semantic_name: str | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "kind", LocationKind(self.kind))
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("kind") from exc
        try:
            object.__setattr__(self, "status", LocationStatus(self.status))
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("status") from exc
        object.__setattr__(self, "observed_at", require_non_negative_int(self.observed_at, "observed_at"))
        if not isinstance(self.is_own_report, bool):
            raise DomainValidationError("is_own_report")
        object.__setattr__(self, "altitude", optional_int(self.altitude, "altitude"))
        object.__setattr__(self, "accuracy", optional_accuracy(self.accuracy))

        if self.kind is LocationKind.POINT:
            if self.latitude is None or self.longitude is None:
                raise DomainValidationError("coordinates")
            object.__setattr__(self, "latitude", latitude(self.latitude))
            object.__setattr__(self, "longitude", longitude(self.longitude))
            object.__setattr__(self, "semantic_name", None)
        else:
            object.__setattr__(self, "latitude", None)
            object.__setattr__(self, "longitude", None)
            object.__setattr__(self, "semantic_name", require_text(self.semantic_name, "semantic_name"))


@dataclass(frozen=True, slots=True)
class LocationReport:
    id: int | None
    beacon_id: int
    report: RawLocationReport
    dedup_key: str
    received_at: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", optional_non_negative_int(self.id, "id"))
        object.__setattr__(self, "beacon_id", require_non_negative_int(self.beacon_id, "beacon_id"))
        if not isinstance(self.report, RawLocationReport):
            raise DomainValidationError("report")
        object.__setattr__(self, "dedup_key", require_text(self.dedup_key, "dedup_key"))
        object.__setattr__(self, "received_at", require_non_negative_int(self.received_at, "received_at"))

    @classmethod
    def create(
        cls,
        *,
        beacon_id: int,
        beacon_public_id: str,
        report: RawLocationReport,
        received_at: int,
    ) -> "LocationReport":
        dedup_key = build_location_dedup_key(
            beacon_public_id=beacon_public_id,
            kind=report.kind.value,
            observed_at=report.observed_at,
            latitude_value=report.latitude,
            longitude_value=report.longitude,
            status=report.status.value,
            is_own_report=report.is_own_report,
        )
        return cls(None, beacon_id, report, dedup_key, received_at)


@dataclass(frozen=True, slots=True)
class InsertSummary:
    inserted: int
    duplicated: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "inserted", require_non_negative_int(self.inserted, "inserted"))
        object.__setattr__(self, "duplicated", require_non_negative_int(self.duplicated, "duplicated"))


@dataclass(frozen=True, slots=True)
class SyncRun:
    id: str
    operation: SyncOperation
    status: SyncState
    started_at: int | None = None
    finished_at: int | None = None
    devices_discovered: int = 0
    reports_received: int = 0
    reports_inserted: int = 0
    reports_duplicated: int = 0
    beacon_public_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "id"))
        try:
            object.__setattr__(self, "operation", SyncOperation(self.operation))
            object.__setattr__(self, "status", SyncState(self.status))
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("sync_enum") from exc
        object.__setattr__(self, "started_at", optional_non_negative_int(self.started_at, "started_at"))
        object.__setattr__(self, "finished_at", optional_non_negative_int(self.finished_at, "finished_at"))
        if self.started_at is not None and self.finished_at is not None and self.finished_at < self.started_at:
            raise DomainValidationError("finished_at")
        for field in ("devices_discovered", "reports_received", "reports_inserted", "reports_duplicated"):
            object.__setattr__(self, field, require_non_negative_int(getattr(self, field), field))
        for field in ("beacon_public_id", "error_code", "error_message"):
            object.__setattr__(self, field, optional_text(getattr(self, field), field))
