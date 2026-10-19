import tempfile
import threading
import unittest
from pathlib import Path

from MapApp.application.jobs import JobCoordinator
from MapApp.application.refresh_all import CancellationToken, RefreshAllBeacons
from MapApp.domain.errors import GoogleUnavailable, LocationTimeout
from MapApp.domain.models import (
    DiscoveredBeacon,
    LocationKind,
    LocationStatus,
    RawLocationReport,
    SyncState,
)
from MapApp.infrastructure.persistence import SQLiteUnitOfWork


class IncrementingClock:
    def __init__(self, start=100):
        self._value = start
        self._lock = threading.Lock()

    def now_utc_seconds(self):
        with self._lock:
            self._value += 1
            return self._value


class BatchGateway:
    def __init__(self, responses, on_call=None):
        self.responses = responses
        self.on_call = on_call
        self.calls = []

    def list_beacons(self):
        raise AssertionError("RefreshAllBeacons reads the local inventory")

    def locate(self, canonic_id, timeout_seconds):
        self.calls.append((canonic_id, timeout_seconds))
        if self.on_call is not None:
            self.on_call(len(self.calls), canonic_id)
        response = self.responses[canonic_id]
        if isinstance(response, Exception):
            raise response
        return response


class RefreshAllJobsIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "jobs.db"
        self.clock = IncrementingClock()
        self.job_number = 0
        with self.uow() as transaction:
            for index in range(1, 4):
                transaction.beacons.upsert_discovered(
                    DiscoveredBeacon(f"backend-{index}", f"Tag {index}"),
                    now=50,
                )
            transaction.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def uow(self):
        next_public = getattr(self, "_next_public", 0)

        def id_factory():
            nonlocal next_public
            next_public += 1
            self._next_public = next_public
            return f"public-{next_public}"

        return SQLiteUnitOfWork(self.database_path, id_factory=id_factory)

    def point(self, index):
        return RawLocationReport(
            kind=LocationKind.POINT,
            observed_at=1_000 + index,
            status=LocationStatus.CROWDSOURCED,
            is_own_report=False,
            latitude=-20.0 - index,
            longitude=-40.0 - index,
        )

    def use_case(self, gateway):
        def job_id():
            self.job_number += 1
            return f"job-{self.job_number}"

        return RefreshAllBeacons(
            gateway,
            self.uow,
            clock=self.clock,
            job_id_factory=job_id,
        )

    def successful_responses(self):
        return {f"backend-{index}": [self.point(index)] for index in range(1, 4)}

    def test_all_success_persists_reports_and_progress(self):
        gateway = BatchGateway(self.successful_responses())
        progress = []
        result = self.use_case(gateway).execute(
            timeout_per_beacon=2.5,
            on_progress=lambda completed, total: progress.append((completed, total)),
        )
        self.assertEqual(result.run.status, SyncState.SUCCEEDED)
        self.assertEqual((result.completed, result.total), (3, 3))
        self.assertEqual(result.run.reports_inserted, 3)
        self.assertEqual(progress, [(0, 3), (1, 3), (2, 3), (3, 3)])
        self.assertEqual([timeout for _, timeout in gateway.calls], [2.5, 2.5, 2.5])

    def test_isolated_failure_continues_and_finishes_partial(self):
        responses = self.successful_responses()
        responses["backend-2"] = GoogleUnavailable()
        result = self.use_case(BatchGateway(responses)).execute()
        self.assertEqual(result.run.status, SyncState.PARTIAL)
        self.assertEqual(result.completed, 3)
        self.assertEqual(result.run.reports_inserted, 2)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].error_code, "google_unavailable")
        with self.uow() as transaction:
            latest = transaction.locations.latest_by_beacon()
        self.assertEqual(len(latest), 2)

    def test_all_timeouts_finish_as_timed_out(self):
        responses = {f"backend-{index}": LocationTimeout() for index in range(1, 4)}
        result = self.use_case(BatchGateway(responses)).execute(timeout_per_beacon=0.1)
        self.assertEqual(result.run.status, SyncState.TIMED_OUT)
        self.assertEqual(result.run.error_code, "location_timeout")
        self.assertEqual(len(result.failures), 3)

    def test_cancellation_stops_between_devices(self):
        token = CancellationToken()

        def cancel_after_first(call_number, _canonic_id):
            if call_number == 1:
                token.cancel()

        gateway = BatchGateway(self.successful_responses(), cancel_after_first)
        progress = []
        result = self.use_case(gateway).execute(
            cancellation=token,
            on_progress=lambda completed, total: progress.append((completed, total)),
        )
        self.assertEqual(result.run.status, SyncState.CANCELLED)
        self.assertEqual((result.completed, result.total), (1, 3))
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(progress[-1], (1, 3))

    def test_coordinator_runs_off_thread_and_reports_snapshot(self):
        entered = threading.Event()
        release = threading.Event()

        def block_first(call_number, _canonic_id):
            if call_number == 1:
                entered.set()
                self.assertTrue(release.wait(2))

        use_case = self.use_case(BatchGateway(self.successful_responses(), block_first))
        coordinator = JobCoordinator(use_case)
        self.addCleanup(coordinator.close)
        pending = coordinator.submit_refresh_all()
        self.assertTrue(entered.wait(2))
        snapshot = coordinator.snapshot(pending.id)
        self.assertIn(snapshot.run.status, (SyncState.PENDING, SyncState.RUNNING))
        release.set()
        result = coordinator.wait(pending.id, timeout=2)
        final_snapshot = coordinator.snapshot(pending.id)
        self.assertEqual(result.run.status, SyncState.SUCCEEDED)
        self.assertEqual(final_snapshot.progress, 1.0)

    def test_coordinator_cancel_stops_running_job_between_devices(self):
        entered = threading.Event()
        release = threading.Event()

        def block_first(call_number, _canonic_id):
            if call_number == 1:
                entered.set()
                self.assertTrue(release.wait(2))

        gateway = BatchGateway(self.successful_responses(), block_first)
        coordinator = JobCoordinator(self.use_case(gateway))
        self.addCleanup(coordinator.close)
        pending = coordinator.submit_refresh_all()
        self.assertTrue(entered.wait(2))
        self.assertTrue(coordinator.cancel(pending.id))
        release.set()
        result = coordinator.wait(pending.id, timeout=2)
        snapshot = coordinator.snapshot(pending.id)
        self.assertEqual(result.run.status, SyncState.CANCELLED)
        self.assertTrue(snapshot.cancellation_requested)
        self.assertEqual(len(gateway.calls), 1)

    def test_coordinator_uses_only_one_google_worker(self):
        entered = threading.Event()
        release = threading.Event()
        call_lock = threading.Lock()
        calls = []

        def block_first_global(_call_number, canonic_id):
            with call_lock:
                calls.append(canonic_id)
                position = len(calls)
            if position == 1:
                entered.set()
                self.assertTrue(release.wait(2))

        gateway = BatchGateway(self.successful_responses(), block_first_global)
        coordinator = JobCoordinator(self.use_case(gateway))
        self.addCleanup(coordinator.close)
        first = coordinator.submit_refresh_all()
        self.assertTrue(entered.wait(2))
        second = coordinator.submit_refresh_all()
        with call_lock:
            self.assertEqual(len(calls), 1)
        release.set()
        self.assertEqual(coordinator.wait(first.id, 3).run.status, SyncState.SUCCEEDED)
        self.assertEqual(coordinator.wait(second.id, 3).run.status, SyncState.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
