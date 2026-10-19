"""Use case for synchronizing the Google beacon inventory into local storage."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from MapApp.domain.errors import ApplicationError, MalformedGoogleResponse
from MapApp.domain.models import Beacon, DiscoveredBeacon, SyncOperation, SyncRun, SyncState
from MapApp.domain.ports import Clock, GoogleGateway, UnitOfWork
from MapApp.domain.validation import require_text

from .system_clock import SystemClock


UnitOfWorkFactory = Callable[[], UnitOfWork]
JobIdFactory = Callable[[], str]


class SyncDevices:
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

    def execute(self) -> SyncRun:
        job_id = require_text(self._job_id_factory(), "job_id")
        started_at = self._clock.now_utc_seconds()
        running = SyncRun(
            id=job_id,
            operation=SyncOperation.SYNC_DEVICES,
            status=SyncState.RUNNING,
            started_at=started_at,
        )
        self._add_run(running)

        try:
            discovered = self._validated_inventory(self._gateway.list_beacons())
            discovered_at = self._clock.now_utc_seconds()
            with self._unit_of_work_factory() as transaction:
                persisted: list[Beacon] = [
                    transaction.beacons.upsert_discovered(beacon, discovered_at)
                    for beacon in discovered
                ]
                completed = SyncRun(
                    id=job_id,
                    operation=SyncOperation.SYNC_DEVICES,
                    status=SyncState.SUCCEEDED,
                    started_at=started_at,
                    finished_at=discovered_at,
                    devices_discovered=len(persisted),
                )
                transaction.sync_runs.update(completed)
                transaction.commit()
            return completed
        except ApplicationError as error:
            self._record_failure(running, error)
            raise
        except Exception as exc:
            error = ApplicationError()
            self._record_failure(running, error)
            raise error from exc

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
    def _validated_inventory(value: object) -> list[DiscoveredBeacon]:
        if not isinstance(value, list) or not all(
            isinstance(item, DiscoveredBeacon) for item in value
        ):
            raise MalformedGoogleResponse()
        canonic_ids = [item.canonic_id for item in value]
        if len(canonic_ids) != len(set(canonic_ids)):
            raise MalformedGoogleResponse()
        return value
