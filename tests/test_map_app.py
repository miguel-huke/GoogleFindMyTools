import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from MapApp.server import create_server


class MapAppBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.database_path = Path(cls.temp_dir.name) / "map-app.db"

        def fake_tile(_z, _x, _y):
            return b"synthetic-png", "image/png"

        cls.fake_tile = fake_tile
        cls.server = create_server(
            port=0,
            demo=True,
            tile_fetcher=fake_tile,
            database_path=cls.database_path,
        )
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
    def request(cls, path, method="GET"):
        headers = {"Accept": "application/json"}
        if method == "POST":
            headers.update(
                {
                    "Origin": cls.base_url,
                    "X-FindHub-CSRF": cls.csrf_token,
                }
            )
        request = urllib.request.Request(cls.base_url + path, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.load(response), response.headers

    @classmethod
    def synchronize_demo(cls):
        status, submitted, _ = cls.request("/api/v1/sync/devices", "POST")
        if status != 202:
            raise AssertionError(status)
        status, job, _ = cls.request(f"/api/v1/jobs/{submitted['job_id']}")
        if status != 200 or job["status"] != "SUCCEEDED":
            raise AssertionError(job)

    def test_main_bootstrap_serves_frontend_api_and_security_headers(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("Find Hub Map", body)
            self.assertIn("leaflet@1.9.4", body)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        status, health, _ = self.request("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["database"], "ok")

    def test_main_py_cli_starts_the_v1_server(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-B",
                "main.py",
                "--demo",
                "--no-browser",
                "--port",
                str(port),
                "--database",
                str(Path(self.temp_dir.name) / "cli.db"),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 8
            while True:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/v1/health", timeout=0.5
                    ) as response:
                        payload = json.load(response)
                    break
                except Exception:
                    if process.poll() is not None:
                        stdout, stderr = process.communicate(timeout=2)
                        self.fail(f"main.py exited early: {stdout} {stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("main.py did not start the API v1 server")
                    time.sleep(0.05)
            self.assertEqual(payload["api_version"], "v1")
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)

    def test_demo_flow_persists_devices_jobs_and_locations_in_sqlite(self):
        self.synchronize_demo()
        status, devices, _ = self.request("/api/v1/devices")
        self.assertEqual(status, 200)
        self.assertEqual(len(devices["devices"]), 2)
        self.assertNotIn("demo-keys", json.dumps(devices))

        status, submitted, _ = self.request("/api/v1/sync/locations", "POST")
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 5
        while True:
            _, job, _ = self.request(f"/api/v1/jobs/{submitted['job_id']}")
            if job["status"] in {"SUCCEEDED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"}:
                break
            if time.monotonic() >= deadline:
                self.fail("demo refresh job did not finish")
            time.sleep(0.02)
        self.assertEqual(job["status"], "SUCCEEDED")
        self.assertEqual(job["counts"]["reports_inserted"], 5)
        _, map_payload, _ = self.request("/api/v1/map/latest")
        self.assertEqual(len(map_payload["features"]), 2)

    def test_sqlite_cache_survives_a_new_server_instance(self):
        self.synchronize_demo()
        second = create_server(
            port=0,
            demo=True,
            tile_fetcher=self.fake_tile,
            database_path=self.database_path,
        )
        thread = threading.Thread(target=second.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{second.server_address[1]}"
            with urllib.request.urlopen(base_url + "/api/v1/devices", timeout=3) as response:
                payload = json.load(response)
            self.assertEqual(len(payload["devices"]), 2)
        finally:
            second.shutdown()
            second.server_close()
            thread.join(timeout=2)

    def test_raster_tiles_are_still_served_from_localhost(self):
        with urllib.request.urlopen(
            self.base_url + "/osm-tiles/10/379/580.png", timeout=3
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"synthetic-png")
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertIn("max-age=604800", response.headers["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
