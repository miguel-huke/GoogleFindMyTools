import json
import threading
import unittest
import urllib.request

from MapApp.providers import DemoReportsProvider
from MapApp.server import create_server


class MapAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def fake_tile(z, x, y):
            return b"synthetic-png", "image/png"

        cls.server = create_server(
            port=0,
            provider=DemoReportsProvider(),
            tile_fetcher=fake_tile,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path):
        with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
            return response.status, json.load(response)

    def test_frontend_is_served(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("Find Hub Map", body)
            self.assertIn("leaflet@1.9.4", body)

    def test_devices_use_temporary_references(self):
        status, payload = self.get_json("/api/devices")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["devices"]), 2)
        serialized = json.dumps(payload)
        self.assertNotIn("demo-keys", serialized)
        self.assertNotIn("canonic", serialized.lower())

    def test_reports_are_structured_for_map(self):
        _, devices = self.get_json("/api/devices")
        ref = devices["devices"][0]["ref"]
        status, payload = self.get_json(f"/api/devices/{ref}/reports")
        self.assertEqual(status, 200)
        self.assertGreater(len(payload["reports"]), 0)
        point = payload["reports"][0]
        self.assertEqual(point["kind"], "point")
        self.assertTrue(-90 <= point["latitude"] <= 90)
        self.assertTrue(-180 <= point["longitude"] <= 180)
        self.assertIn("timestamp", point)
        self.assertNotIn("encrypted", json.dumps(payload).lower())

    def test_raster_tiles_are_served_from_localhost(self):
        with urllib.request.urlopen(
            self.base_url + "/osm-tiles/10/379/580.png", timeout=3
        ) as response:
            body = response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(body, b"synthetic-png")
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertIn("max-age=604800", response.headers["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
