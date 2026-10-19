import base64
import contextlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from MapApp.application.jobs import JobSnapshot
from MapApp.application.query_map import QueryMapState
from MapApp.domain.models import (
    DiscoveredBeacon,
    LocationKind,
    LocationReport,
    LocationStatus,
    RawLocationReport,
    SyncOperation,
    SyncRun,
    SyncState,
)
from MapApp.infrastructure.persistence import SQLiteUnitOfWork
from MapApp.presentation.http import ApiServices, create_api_server


class ApiV1IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.database_path = Path(cls.temp_dir.name) / "api.db"
        cls._seed_database()
        cls.submissions = []
        cls.runs = {}

        def submit(operation, public_id=None):
            job_id = f"job-{len(cls.submissions) + 1}"
            run = SyncRun(job_id, operation, SyncState.PENDING, beacon_public_id=public_id)
            cls.submissions.append((operation.value, public_id))
            cls.runs[job_id] = JobSnapshot(run, 0, 0, False)
            return run

        cls.services = ApiServices(
            queries=QueryMapState(cls.uow),
            submit_sync_devices=lambda: submit(SyncOperation.SYNC_DEVICES),
            submit_refresh_all=lambda: submit(SyncOperation.REFRESH_ALL),
            submit_refresh_one=lambda public_id: submit(SyncOperation.REFRESH_ONE, public_id),
            get_job=lambda job_id: cls.runs[job_id],
            cancel_job=cls._cancel_job,
            tile_provider=lambda _z, _x, _y: (
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                ),
                "image/png",
            ),
        )
        cls.server = create_api_server(cls.services, port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        with urllib.request.urlopen(cls.base_url + "/api/v1/session", timeout=3) as response:
            cls.csrf_token = json.load(response)["csrf_token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    @classmethod
    def uow(cls):
        return SQLiteUnitOfWork(cls.database_path, id_factory=lambda: "public-device-1")

    @classmethod
    def _seed_database(cls):
        with cls.uow() as transaction:
            beacon = transaction.beacons.upsert_discovered(
                DiscoveredBeacon("backend-secret-id", "Tag pública", "DEVICE_TYPE_KEYS", "Acme", "One"),
                now=10,
            )
            point = RawLocationReport(
                kind=LocationKind.POINT,
                observed_at=100,
                status=LocationStatus.CROWDSOURCED,
                is_own_report=False,
                latitude=-23.5,
                longitude=-46.6,
                accuracy=7,
            )
            semantic = RawLocationReport(
                kind=LocationKind.SEMANTIC,
                observed_at=110,
                status=LocationStatus.SEMANTIC,
                is_own_report=True,
                semantic_name="Casa sintética",
            )
            transaction.locations.add_many(
                [
                    LocationReport.create(
                        beacon_id=beacon.id,
                        beacon_public_id=beacon.public_id,
                        report=report,
                        received_at=120,
                    )
                    for report in (point, semantic)
                ]
            )
            transaction.commit()

    @classmethod
    def _cancel_job(cls, job_id):
        snapshot = cls.runs[job_id]
        run = snapshot.run
        cancelled = SyncRun(run.id, run.operation, SyncState.CANCELLED, finished_at=200, beacon_public_id=run.beacon_public_id)
        cls.runs[job_id] = JobSnapshot(cancelled, 0, 0, True)
        return True

    def request(self, path, method="GET", headers=None):
        request_headers = dict(headers or {})
        if method == "POST":
            request_headers.setdefault("Origin", self.base_url)
            request_headers.setdefault("X-FindHub-CSRF", self.csrf_token)
        request = urllib.request.Request(self.base_url + path, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.load(error), error.headers

    def raw_request(self, path, method="GET", headers=None):
        request = urllib.request.Request(self.base_url + path, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_frontend_and_local_tiles_are_served_by_api_server(self):
        status, page, headers = self.raw_request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"sync-devices", page)
        self.assertEqual(headers.get_content_type(), "text/html")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        status, script, headers = self.raw_request("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"/api/v1", script)
        self.assertIn("javascript", headers["Content-Type"])
        status, tile, headers = self.raw_request("/osm-tiles/1/0/0.png")
        self.assertEqual(status, 200)
        self.assertTrue(tile.startswith(b"\x89PNG"))
        self.assertEqual(headers.get_content_type(), "image/png")

    def test_health_session_and_json_headers(self):
        status, payload, headers = self.request("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "api_version": "v1", "database": "ok"})
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        status, session, _ = self.request("/api/v1/session")
        self.assertEqual(status, 200)
        token = session.pop("csrf_token")
        self.assertEqual(session, {"connected": False, "available": False})
        self.assertGreaterEqual(len(token), 32)

    def test_rejects_untrusted_host_origin_and_csrf_without_starting_job(self):
        initial_submissions = len(self.submissions)
        status, body, _ = self.raw_request("/api/v1/health", headers={"Host": "attacker.example"})
        self.assertEqual(status, 421)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_host")

        status, body, _ = self.raw_request("/api/v1/sync/devices", method="POST")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_origin")

        status, body, _ = self.raw_request(
            "/api/v1/sync/devices",
            method="POST",
            headers={"Origin": "http://attacker.example", "X-FindHub-CSRF": self.csrf_token},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_origin")

        status, body, _ = self.raw_request(
            "/api/v1/sync/devices",
            method="POST",
            headers={"Origin": self.base_url, "X-FindHub-CSRF": "wrong-token"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_csrf")
        self.assertEqual(len(self.submissions), initial_submissions)

    def test_server_refuses_non_loopback_bind(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_api_server(self.services, host="0.0.0.0", port=0)

    def test_server_suppresses_connection_handler_tracebacks(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.server.handle_error(None, None)
        self.assertEqual(stderr.getvalue(), "")

    def test_devices_detail_and_history_are_sanitized(self):
        status, payload, _ = self.request("/api/v1/devices")
        self.assertEqual(status, 200)
        self.assertEqual(payload["devices"][0]["public_id"], "public-device-1")
        serialized = json.dumps(payload).lower()
        self.assertNotIn("backend-secret-id", serialized)
        self.assertNotIn("canonic", serialized)
        status, detail, _ = self.request("/api/v1/devices/public-device-1")
        self.assertEqual(status, 200)
        self.assertEqual(detail["device"]["latest_location"]["kind"], "point")
        status, history, _ = self.request("/api/v1/devices/public-device-1/locations?limit=2")
        self.assertEqual(status, 200)
        self.assertEqual([item["kind"] for item in history["locations"]], ["semantic", "point"])

    def test_map_latest_is_valid_geojson_with_longitude_first(self):
        status, payload, _ = self.request("/api/v1/map/latest")
        self.assertEqual(status, 200)
        self.assertEqual(payload["type"], "FeatureCollection")
        feature = payload["features"][0]
        self.assertEqual(feature["geometry"]["coordinates"], [-46.6, -23.5])
        self.assertEqual(feature["properties"]["device_public_id"], "public-device-1")

    def test_job_submission_status_and_cancel_routes(self):
        status, all_job, _ = self.request("/api/v1/sync/locations", "POST")
        self.assertEqual(status, 202)
        self.assertEqual(all_job["operation"], "REFRESH_ALL")
        status, one_job, _ = self.request("/api/v1/devices/public-device-1/refresh", "POST")
        self.assertEqual(status, 202)
        self.assertEqual(self.submissions[-1], ("REFRESH_ONE", "public-device-1"))
        status, snapshot, _ = self.request(f"/api/v1/jobs/{one_job['job_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["status"], "PENDING")
        status, cancelled, _ = self.request(f"/api/v1/jobs/{one_job['job_id']}/cancel", "POST")
        self.assertEqual(status, 202)
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_sync_devices_and_unconfigured_connect_contracts(self):
        status, job, _ = self.request("/api/v1/sync/devices", "POST")
        self.assertEqual(status, 202)
        self.assertEqual(job["operation"], "SYNC_DEVICES")
        status, payload, _ = self.request("/api/v1/session/connect", "POST")
        self.assertEqual(status, 501)
        self.assertEqual(payload["error"]["code"], "not_implemented")

    def test_invalid_and_missing_resources_return_safe_errors(self):
        for path in (
            "/api/v1/devices/missing",
            "/api/v1/devices/public-device-1/locations?limit=invalid",
            "/api/v1/jobs/missing",
            "/api/v1/unknown",
        ):
            status, payload, _ = self.request(path)
            self.assertIn(status, (400, 404))
            self.assertIn("correlation_id", payload["error"])
            serialized = json.dumps(payload).lower()
            self.assertNotIn("traceback", serialized)
            self.assertNotIn("backend-secret-id", serialized)


if __name__ == "__main__":
    unittest.main()
