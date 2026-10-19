"""Sequential refresh of every active beacon with durable aggregate status."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from MapApp.domain.errors import ApplicationError, LocationTimeout, MalformedGoogleResponse, NotFoundError, PersistenceFailed
from MapApp.domain.models import LocationReport, RawLocationReport, SyncOperation, SyncRun, SyncState
from MapApp.domain.ports import Clock, GoogleGateway, UnitOfWork
from MapApp.domain.validation import require_text

from .system_clock import SystemClock


UnitOfWorkFactory = Callable[[], UnitOfWork]
JobIdFactory = Callable[[], str]
ProgressCallback = Callable[[int, int], None]


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True, slots=True)
class DeviceRefreshFailure:
    beacon_public_id: str
    error_code: str


@dataclass(frozen=True, slots=True)
class RefreshAllBeaconsResult:
    run: SyncRun
    completed: int
    total: int
    failures: tuple[DeviceRefreshFailure, ...]


class RefreshAllBeacons:
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

    def prepare(self) -> SyncRun:
        pending = SyncRun(
            id=require_text(self._job_id_factory(), "job_id"),
            operation=SyncOperation.REFRESH_ALL,
            status=SyncState.PENDING,
        )
        with self._unit_of_work_factory() as transaction:
            transaction.sync_runs.add(pending)
            transaction.commit()
        return pending

    def execute(
        self,
        *,
        timeout_per_beacon: float = 60.0,
        cancellation: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> RefreshAllBeaconsResult:
        pending = self.prepare()
        return self.execute_pending(
            pending.id,
            timeout_per_beacon=timeout_per_beacon,
            cancellation=cancellation,
            on_progress=on_progress,
        )

    def execute_pending(
        self,
        job_id: str,
        *,
        timeout_per_beacon: float = 60.0,
        cancellation: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> RefreshAllBeaconsResult:
        safe_job_id = require_text(job_id, "job_id")
        token = cancellation or CancellationToken()
        started_at = self._clock.now_utc_seconds()
        try:
            pending = self.get_run(safe_job_id)
            if pending.status is SyncState.CANCELLED:
                return RefreshAllBeaconsResult(pending, 0, 0, ())
            if pending.status is not SyncState.PENDING:
                raise PersistenceFailed("The job is not pending.")
            with self._unit_of_work_factory() as transaction:
                beacons = transaction.beacons.list_active()
            total = len(beacons)
            running = SyncRun(
                id=safe_job_id,
                operation=SyncOperation.REFRESH_ALL,
                status=SyncState.RUNNING,
                started_at=started_at,
                devices_discovered=total,
            )
            self._update_run(running)
            self._publish(on_progress, 0, total)

            completed = 0
            received = 0
            inserted = 0
            duplicated = 0
            failures: list[DeviceRefreshFailure] = []

            for beacon in beacons:
                if token.is_cancelled():
                    break
                try:
                    raw_reports = self._validated_reports(
                        self._gateway.locate(beacon.canonic_id, timeout_per_beacon)
                    )
                    if beacon.id is None:
                        raise PersistenceFailed()
                    received_at = self._clock.now_utc_seconds()
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
                        received += len(raw_reports)
                        inserted += summary.inserted
                        duplicated += summary.duplicated
                        completed += 1
                        transaction.sync_runs.update(
                            self._running_snapshot(
                                safe_job_id,
                                started_at,
                                total,
                                received,
                                inserted,
                                duplicated,
                            )
                        )
                        transaction.commit()
                except ApplicationError as error:
                    failures.append(DeviceRefreshFailure(beacon.public_id, error.code))
                    completed += 1
                    self._update_run(
                        self._running_snapshot(
                            safe_job_id,
                            started_at,
                            total,
                            received,
                            inserted,
                            duplicated,
                        )
                    )
                except Exception:
                    failures.append(DeviceRefreshFailure(beacon.public_id, "application_error"))
                    completed += 1
                    self._update_run(
                        self._running_snapshot(
                            safe_job_id,
                            started_at,
                            total,
                            received,
                            inserted,
                            duplicated,
                        )
                    )
                self._publish(on_progress, completed, total)

            final = self._final_run(
                safe_job_id,
                started_at,
                total,
                completed,
                received,
                inserted,
                duplicated,
                failures,
                cancelled=token.is_cancelled() and completed < total,
            )
            self._update_run(final)
            return RefreshAllBeaconsResult(final, completed, total, tuple(failures))
        except ApplicationError as error:
            self._fail_unfinished(safe_job_id, started_at, error)
            raise
        except Exception as exc:
            error = ApplicationError()
            self._fail_unfinished(safe_job_id, started_at, error)
            raise error from exc

    def cancel_pending(self, job_id: str) -> SyncRun:
        run = self.get_run(job_id)
        if run.status is not SyncState.PENDING:
            return run
        cancelled = SyncRun(
            id=run.id,
            operation=run.operation,
            status=SyncState.CANCELLED,
            finished_at=self._clock.now_utc_seconds(),
        )
        self._update_run(cancelled)
        return cancelled

    def get_run(self, job_id: str) -> SyncRun:
        with self._unit_of_work_factory() as transaction:
            run = transaction.sync_runs.get(require_text(job_id, "job_id"))
        if run is None:
            raise NotFoundError()
        return run

    def _update_run(self, run: SyncRun) -> None:
        with self._unit_of_work_factory() as transaction:
            transaction.sync_runs.update(run)
            transaction.commit()

    def _fail_unfinished(self, job_id: str, started_at: int, error: ApplicationError) -> None:
        try:
            current = self.get_run(job_id)
            if current.status not in (SyncState.PENDING, SyncState.RUNNING):
                return
            failed = SyncRun(
                id=current.id,
                operation=SyncOperation.REFRESH_ALL,
                status=SyncState.FAILED,
                started_at=started_at,
                finished_at=self._clock.now_utc_seconds(),
                devices_discovered=current.devices_discovered,
                reports_received=current.reports_received,
                reports_inserted=current.reports_inserted,
                reports_duplicated=current.reports_duplicated,
                error_code=error.code,
                error_message=error.safe_message,
            )
            self._update_run(failed)
        except Exception:
            return

    @staticmethod
    def _running_snapshot(
        job_id: str,
        started_at: int,
        total: int,
        received: int,
        inserted: int,
        duplicated: int,
    ) -> SyncRun:
        return SyncRun(
            id=job_id,
            operation=SyncOperation.REFRESH_ALL,
            status=SyncState.RUNNING,
            started_at=started_at,
            devices_discovered=total,
            reports_received=received,
            reports_inserted=inserted,
            reports_duplicated=duplicated,
        )

    def _final_run(
        self,
        job_id: str,
        started_at: int,
        total: int,
        completed: int,
        received: int,
        inserted: int,
        duplicated: int,
        failures: list[DeviceRefreshFailure],
        *,
        cancelled: bool,
    ) -> SyncRun:
        error_code = None
        error_message = None
        if cancelled:
            status = SyncState.CANCELLED
        elif not failures:
            status = SyncState.SUCCEEDED
        elif len(failures) < total:
            status = SyncState.PARTIAL
            error_code = "partial_failure"
            error_message = "Some devices could not be refreshed."
        elif failures and all(item.error_code == LocationTimeout.default_code for item in failures):
            status = SyncState.TIMED_OUT
            error_code = LocationTimeout.default_code
            error_message = LocationTimeout.default_message
        else:
            status = SyncState.FAILED
            error_code = "refresh_failed"
            error_message = "No device could be refreshed."
        return SyncRun(
            id=job_id,
            operation=SyncOperation.REFRESH_ALL,
            status=status,
            started_at=started_at,
            finished_at=self._clock.now_utc_seconds(),
            devices_discovered=total,
            reports_received=received,
            reports_inserted=inserted,
            reports_duplicated=duplicated,
            error_code=error_code,
            error_message=error_message,
        )

    @staticmethod
    def _validated_reports(value: object) -> list[RawLocationReport]:
        if not isinstance(value, list) or not all(
            isinstance(item, RawLocationReport) for item in value
        ):
            raise MalformedGoogleResponse()
        return value

    @staticmethod
    def _publish(callback: ProgressCallback | None, completed: int, total: int) -> None:
        if callback is None:
            return
        try:
            callback(completed, total)
        except Exception:
            return
