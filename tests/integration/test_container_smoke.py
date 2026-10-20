import tempfile
import threading
import unittest
from pathlib import Path

from MapApp.server import create_server
from scripts.container_smoke import SmokeFailure, run_smoke


class ContainerSmokeIntegrationTest(unittest.TestCase):
    def test_full_demo_smoke_and_cache_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "container-smoke.db"

            first = create_server(
                port=0,
                demo=True,
                tile_fetcher=lambda _z, _x, _y: (b"synthetic", "image/png"),
                database_path=database,
            )
            first_thread = threading.Thread(target=first.serve_forever, daemon=True)
            first_thread.start()
            try:
                first_url = f"http://127.0.0.1:{first.server_address[1]}"
                result = run_smoke(first_url, timeout=5)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["devices"], 2)
                self.assertEqual(result["map_features"], 2)
            finally:
                first.shutdown()
                first.server_close()
                first_thread.join(timeout=2)

            second = create_server(
                port=0,
                demo=True,
                tile_fetcher=lambda _z, _x, _y: (b"synthetic", "image/png"),
                database_path=database,
            )
            second_thread = threading.Thread(target=second.serve_forever, daemon=True)
            second_thread.start()
            try:
                second_url = f"http://127.0.0.1:{second.server_address[1]}"
                persisted = run_smoke(second_url, verify_cache=True, timeout=5)
                self.assertEqual(persisted["status"], "ok")
                self.assertEqual(persisted["devices"], 2)
                self.assertEqual(persisted["map_features"], 2)
            finally:
                second.shutdown()
                second.server_close()
                second_thread.join(timeout=2)

    def test_smoke_refuses_non_local_targets(self):
        with self.assertRaisesRegex(SmokeFailure, "localhost"):
            run_smoke("https://example.com")


if __name__ == "__main__":
    unittest.main()
