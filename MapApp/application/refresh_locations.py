"""Use case for refreshing and persisting one beacon's location reports."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from MapApp.domain.errors import (
    ApplicationError,
    MalformedGoogleResponse,
    NotFoundError,
    PersistenceFailed,
)
from MapApp.domain.models import (
    Beacon,
    InsertSummary,
    LocationReport,
    RawLocationReport,
    SyncOperation,
    SyncRun,
    SyncState,
)
from MapApp.domain.ports import Clock, GoogleGateway, UnitOfWork
from MapApp.domain.validation import require_text

from .system_clock import SystemClock


UnitOfWorkFactory = Callable[[], UnitOfWork]
JobIdFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class RefreshBeaconLocationsResult:
    run: SyncRun
    insert_summary: InsertSummary
    latest_location: LocationReport | None


class RefreshBeaconLocations:
    def __init__(
        self,
        gateway: GoogleGateway,
        unit_of_work_factory: UnitOfWorkFactory,
        *,
        clock: Clock | None = None,
        job_id_factory: JobIdFactory | None = None,
    ) -> None:
        self._gateway = gateway
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or SystemClock()
        self._job_id_factory = job_id_factory or (lambda: str(uuid.uuid4()))

    def execute(
        self,
        beacon_public_id: str,
        *,
        timeout_seconds: float = 60.0,
    ) -> RefreshBeaconLocationsResult:
        public_id = require_text(beacon_public_id, "beacon_public_id")
        job_id = require_text(self._job_id_factory(), "job_id")
        started_at = self._clock.now_utc_seconds()
        running = SyncRun(
            id=job_id,
            operation=SyncOperation.REFRESH_ONE,
            status=SyncState.RUNNING,
            started_at=started_at,
            beacon_public_id=public_id,
        )
        self._add_run(running)

        try:
            beacon = self._get_beacon(public_id)
            raw_reports = self._validated_reports(
                self._gateway.locate(beacon.canonic_id, timeout_seconds)
            )
            received_at = self._clock.now_utc_seconds()
            if beacon.id is None:
                raise PersistenceFailed()
            reports = [
                LocationReport.create(
                    beacon_id=beacon.id,
                    beacon_public_id=beacon.public_id,
                    report=report,
                    received_at=received_at,
                )
                for report in raw_reports
            ]
            with self._unit_of_work_factory() as transaction:
                summary = transaction.locations.add_many(reports)
                latest = next(
                    (
                        item
                        for item in transaction.locations.latest_by_beacon()
                        if item.beacon_id == beacon.id
                    ),
                    None,
                )
                completed = SyncRun(
                    id=job_id,
                    operation=SyncOperation.REFRESH_ONE,
                    status=SyncState.SUCCEEDED,
                    started_at=started_at,
                    finished_at=received_at,
                    reports_received=len(raw_reports),
                    reports_inserted=summary.inserted,
                    reports_duplicated=summary.duplicated,
                    beacon_public_id=public_id,
                )
                transaction.sync_runs.update(completed)
                transaction.commit()
            return RefreshBeaconLocationsResult(completed, summary, latest)
        except ApplicationError as error:
            self._record_failure(running, error)
            raise
        except Exception as exc:
            error = ApplicationError()
            self._record_failure(running, error)
            raise error from exc

    def _get_beacon(self, public_id: str) -> Beacon:
        with self._unit_of_work_factory() as transaction:
            beacon = transaction.beacons.get_by_public_id(public_id)
        if beacon is None:
            raise NotFoundError()
        return beacon

    def _add_run(self, run: SyncRun) -> None:
        with self._unit_of_work_factory() as transaction:
            transaction.sync_runs.add(run)
            transaction.commit()

    def _record_failure(self, running: SyncRun, error: ApplicationError) -> None:
        try:
            failed = SyncRun(
                id=running.id,
                operation=running.operation,
                status=SyncState.FAILED,
                started_at=running.started_at,
                finished_at=self._clock.now_utc_seconds(),
                beacon_public_id=running.beacon_public_id,
                error_code=error.code,
                error_message=error.safe_message,
            )
            with self._unit_of_work_factory() as transaction:
                transaction.sync_runs.update(failed)
                transaction.commit()
        except Exception:
            # Preserve the original typed failure if audit persistence also fails.
            return

    @staticmethod
    def _validated_reports(value: object) -> list[RawLocationReport]:
        if not isinstance(value, list) or not all(
            isinstance(item, RawLocationReport) for item in value
        ):
            raise MalformedGoogleResponse()
        return value
