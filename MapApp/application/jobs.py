"""Single-worker coordinator for Google jobs and in-memory cancellation tokens."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from MapApp.domain.models import SyncRun, SyncState

from .refresh_all import CancellationToken, RefreshAllBeacons, RefreshAllBeaconsResult


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    run: SyncRun
    completed: int
    total: int
    cancellation_requested: bool

    @property
    def progress(self) -> float:
        if self.total > 0:
            return self.completed / self.total
        if self.run.status in {
            SyncState.SUCCEEDED,
            SyncState.PARTIAL,
            SyncState.FAILED,
            SyncState.TIMED_OUT,
            SyncState.CANCELLED,
        }:
            return 1.0
        return 0.0


@dataclass(slots=True)
class _JobEntry:
    token: CancellationToken
    future: Future[RefreshAllBeaconsResult] | None = None
    completed: int = 0
    total: int = 0


class JobCoordinator:
    def __init__(self, refresh_all: RefreshAllBeacons) -> None:
        self._refresh_all = refresh_all
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="find-hub-google")
        self._entries: dict[str, _JobEntry] = {}
        self._lock = threading.Lock()
        self._closed = False

    def submit_refresh_all(self, *, timeout_per_beacon: float = 60.0) -> SyncRun:
        with self._lock:
            if self._closed:
                raise RuntimeError("The job coordinator is closed.")
        pending = self._refresh_all.prepare()
        entry = _JobEntry(CancellationToken())
        with self._lock:
            self._entries[pending.id] = entry
            entry.future = self._executor.submit(
                self._run,
                pending.id,
                timeout_per_beacon,
                entry,
            )
        return pending

    def _run(
        self,
        job_id: str,
        timeout_per_beacon: float,
        entry: _JobEntry,
    ) -> RefreshAllBeaconsResult:
        return self._refresh_all.execute_pending(
            job_id,
            timeout_per_beacon=timeout_per_beacon,
            cancellation=entry.token,
            on_progress=lambda completed, total: self._set_progress(
                job_id, completed, total
            ),
        )

    def _set_progress(self, job_id: str, completed: int, total: int) -> None:
        with self._lock:
            entry = self._entries.get(job_id)
            if entry is not None:
                entry.completed = completed
                entry.total = total

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            entry = self._entries.get(job_id)
            if entry is None or entry.future is None or entry.future.done():
                return False
            entry.token.cancel()
            cancelled_before_start = entry.future.cancel()
        if cancelled_before_start:
            self._refresh_all.cancel_pending(job_id)
        return True

    def snapshot(self, job_id: str) -> JobSnapshot:
        run = self._refresh_all.get_run(job_id)
        with self._lock:
            entry = self._entries.get(job_id)
            if entry is None:
                return JobSnapshot(run, 0, run.devices_discovered, False)
            return JobSnapshot(
                run,
                entry.completed,
                entry.total,
                entry.token.is_cancelled(),
            )

    def wait(self, job_id: str, timeout: float | None = None) -> RefreshAllBeaconsResult:
        with self._lock:
            entry = self._entries.get(job_id)
            if entry is None or entry.future is None:
                raise KeyError(job_id)
            future = entry.future
        return future.result(timeout=timeout)

    def close(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def __enter__(self) -> "JobCoordinator":
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        return False
