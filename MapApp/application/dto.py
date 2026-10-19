"""Sanitized public values that may cross the HTTP presentation boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TypeAlias

from MapApp.domain.errors import DomainValidationError
from MapApp.domain.validation import (
    latitude,
    longitude,
    optional_accuracy,
    optional_int,
    optional_text,
    require_non_negative_int,
    require_text,
)


@dataclass(frozen=True, slots=True)
class LocationPoint:
    latitude: float
    longitude: float
    observed_at: int
    status: str
    own_report: bool
    altitude: int | None = None
    accuracy: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "latitude", latitude(self.latitude))
        object.__setattr__(self, "longitude", longitude(self.longitude))
        object.__setattr__(self, "observed_at", require_non_negative_int(self.observed_at, "observed_at"))
        object.__setattr__(self, "status", require_text(self.status, "status"))
        if not isinstance(self.own_report, bool):
            raise DomainValidationError("own_report")
        object.__setattr__(self, "altitude", optional_int(self.altitude, "altitude"))
        object.__setattr__(self, "accuracy", optional_accuracy(self.accuracy))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SemanticLocation:
    name: str
    observed_at: int
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_text(self.name, "name"))
        object.__setattr__(self, "observed_at", require_non_negative_int(self.observed_at, "observed_at"))
        object.__setattr__(self, "status", require_text(self.status, "status"))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


PublicLocation: TypeAlias = LocationPoint | SemanticLocation


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    public_id: str
    name: str
    active: bool
    type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    latest_location: PublicLocation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_id", require_text(self.public_id, "public_id"))
        object.__setattr__(self, "name", require_text(self.name, "name"))
        if not isinstance(self.active, bool):
            raise DomainValidationError("active")
        for field in ("type", "manufacturer", "model"):
            object.__setattr__(self, field, optional_text(getattr(self, field), field))
        if self.latest_location is not None and not isinstance(
            self.latest_location, (LocationPoint, SemanticLocation)
        ):
            raise DomainValidationError("latest_location")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SyncStatus:
    job_id: str
    operation: str
    status: str
    progress: float
    safe_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", require_text(self.job_id, "job_id"))
        object.__setattr__(self, "operation", require_text(self.operation, "operation"))
        object.__setattr__(self, "status", require_text(self.status, "status"))
        if isinstance(self.progress, bool) or not isinstance(self.progress, (int, float)):
            raise DomainValidationError("progress")
        progress = float(self.progress)
        if not 0.0 <= progress <= 1.0:
            raise DomainValidationError("progress")
        object.__setattr__(self, "progress", progress)
        object.__setattr__(self, "safe_error", optional_text(self.safe_error, "safe_error"))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
