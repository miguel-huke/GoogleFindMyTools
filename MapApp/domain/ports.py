"""Dependency-inversion ports implemented by infrastructure adapters."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from .models import Beacon, DiscoveredBeacon, InsertSummary, LocationReport, RawLocationReport, SyncRun


@runtime_checkable
class GoogleGateway(Protocol):
    def list_beacons(self) -> list[DiscoveredBeacon]: ...

    def locate(self, canonic_id: str, timeout_seconds: float) -> list[RawLocationReport]: ...


@runtime_checkable
class BeaconRepository(Protocol):
    def upsert_discovered(self, beacon: DiscoveredBeacon, now: int) -> Beacon: ...

    def get_by_public_id(self, public_id: str) -> Beacon | None: ...

    def list_active(self) -> list[Beacon]: ...


@runtime_checkable
class LocationRepository(Protocol):
    def add_many(self, reports: list[LocationReport]) -> InsertSummary: ...

    def latest_by_beacon(self) -> list[LocationReport]: ...

    def history(self, beacon_id: int, limit: int) -> list[LocationReport]: ...


@runtime_checkable
class SyncRunRepository(Protocol):
    def add(self, run: SyncRun) -> None: ...

    def update(self, run: SyncRun) -> None: ...

    def get(self, run_id: str) -> SyncRun | None: ...


@runtime_checkable
class UnitOfWork(Protocol):
    beacons: BeaconRepository
    locations: LocationRepository
    sync_runs: SyncRunRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now_utc_seconds(self) -> int: ...
