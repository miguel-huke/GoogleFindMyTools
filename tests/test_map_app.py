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
from unittest import mock

from MapApp.server import create_server
from MapApp.presentation.http import HttpExposurePolicy
from main import parse_args


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

    def test_kezpo_brand_assets_are_local_and_integrity_documented(self):
        expected = {
            "/assets/brand/kezpo-logo.webp": (
                "image/webp",
                "eba289398cef30e71f3f3f732cdccbeae13f5d2661e7313323ca5eab14e2fad5",
            ),
            "/assets/brand/kezpo-favicon.png": (
                "image/png",
                "03fd1dfd4e13fb3173d23c47d84bff464207f4ff900040eca6fd4918076fd2ca",
            ),
        }
        import hashlib

        for path, (content_type, digest) in expected.items():
            with self.subTest(path=path):
                with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
                    payload = response.read()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), content_type)
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

        with urllib.request.urlopen(
            self.base_url + "/assets/brand/manifest.json", timeout=3
        ) as response:
            manifest = json.load(response)
        self.assertEqual(manifest["brand"], "Kezpo Solutions")
        self.assertEqual(len(manifest["assets"]), 2)

    def test_kezpo_fonts_are_local_licensed_and_integrity_documented(self):
        import hashlib

        expected = {
            "/assets/fonts/Inter-Variable.ttf": (
                "font/ttf",
                "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
            ),
            "/assets/fonts/Outfit-Variable.ttf": (
                "font/ttf",
                "fc7287273e66929776e2ba54f144fe699080bec29f61bf649d70d871468aeade",
            ),
        }
        for path, (content_type, digest) in expected.items():
            with self.subTest(path=path):
                with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
                    payload = response.read()
                    self.assertEqual(response.headers.get_content_type(), content_type)
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

        for license_name in ("OFL-Inter.txt", "OFL-Outfit.txt"):
            with urllib.request.urlopen(
                self.base_url + f"/assets/fonts/{license_name}", timeout=3
            ) as response:
                license_text = response.read().decode("utf-8")
            self.assertIn("SIL OPEN FONT LICENSE", license_text)

        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        self.assertIn('/assets/fonts/Inter-Variable.ttf', stylesheet)
        self.assertIn('/assets/fonts/Outfit-Variable.ttf', stylesheet)
        self.assertNotIn("fonts.googleapis.com", stylesheet)
        self.assertNotIn("fonts.gstatic.com", stylesheet)

        with urllib.request.urlopen(
            self.base_url + "/assets/fonts/manifest.json", timeout=3
        ) as response:
            manifest = json.load(response)
        self.assertEqual(manifest["license"], "SIL Open Font License 1.1")
        self.assertEqual(len(manifest["fonts"]), 2)

    def test_kezpo_color_tokens_replace_the_legacy_palette_with_aa_contrast(self):
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        tokens = {
            "--kezpo-navy": "#0f172e",
            "--kezpo-blue-deep": "#0a2576",
            "--kezpo-blue": "#1745cf",
            "--kezpo-blue-light": "#25b2f4",
            "--kezpo-gold": "#f4a825",
            "--kezpo-gold-dark": "#b87614",
            "--kezpo-gold-light": "#f2bf5a",
            "--kezpo-surface": "#ffffff",
            "--kezpo-surface-soft": "#f4f5f7",
            "--kezpo-border": "#dde0e5",
            "--kezpo-danger": "#ef4444",
        }
        for name, value in tokens.items():
            self.assertIn(f"{name}: {value}", stylesheet)

        legacy_colors = ("#07100f", "#55f2ad", "#4bd9ed", "#f3c96b", "#f28ac5", "#a994ff")
        for color in legacy_colors:
            self.assertNotIn(color, stylesheet.lower())
            self.assertNotIn(color, script.lower())

        def luminance(hex_color):
            channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(foreground, background):
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        aa_pairs = (
            (tokens["--kezpo-surface"], tokens["--kezpo-blue"]),
            (tokens["--kezpo-blue-light"], tokens["--kezpo-navy"]),
            (tokens["--kezpo-gold-light"], tokens["--kezpo-navy"]),
            (tokens["--kezpo-border"], tokens["--kezpo-navy"]),
        )
        for foreground, background in aa_pairs:
            self.assertGreaterEqual(contrast(foreground, background), 4.5)

    def test_kezpo_desktop_shell_uses_light_panels_and_explicit_environment(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            document = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")

        self.assertIn('class="brand-context"', document)
        self.assertIn('class="environment-badge"', document)
        self.assertIn("OPERAÇÕES DE LOCALIZAÇÃO", document)
        self.assertIn("LOCAL · PRIVADO", document)
        self.assertIn("color-scheme: light", stylesheet)
        self.assertIn("--panel: var(--kezpo-surface)", stylesheet)
        self.assertIn("--surface-raised: var(--kezpo-surface-soft)", stylesheet)
        self.assertIn("--map-overlay: rgba(15, 23, 46, 0.94)", stylesheet)
        self.assertIn("min-height: 44px", stylesheet)
        self.assertIn("background: var(--kezpo-navy)", stylesheet)
        self.assertIn("color: var(--kezpo-surface)", stylesheet)

        def luminance(hex_color):
            channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(foreground, background):
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        for foreground, background in (
            ("#0f172e", "#ffffff"),
            ("#0a2576", "#ffffff"),
            ("#1745cf", "#ffffff"),
            ("#0f172e", "#f4a825"),
            ("#ffffff", "#0f172e"),
        ):
            self.assertGreaterEqual(contrast(foreground, background), 4.5)

    def test_kezpo_responsive_contract_covers_all_blueprint_ranges(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            document = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        self.assertIn('id="panel-toggle"', document)
        self.assertIn('aria-controls="device-panel"', document)
        for query in (
            "(max-width: 639px)",
            "(min-width: 640px) and (max-width: 767px)",
            "(min-width: 768px) and (max-width: 1023px)",
            "(min-width: 1280px) and (max-width: 1399px)",
            "(min-width: 1400px)",
            "(prefers-reduced-motion: reduce)",
        ):
            self.assertIn(f"@media {query}", stylesheet)
        self.assertIn("100dvh", stylesheet)
        self.assertIn("panel-collapsed", stylesheet)
        self.assertIn("isolation: isolate", stylesheet)
        self.assertIn("#map { position: absolute; z-index: 0", stylesheet)
        self.assertIn("z-index: 1100", stylesheet)
        self.assertIn("window.matchMedia('(min-width: 1024px)')", script)
        self.assertIn("map.invalidateSize()", script)

    def test_kezpo_accessibility_contract_supports_keyboard_and_text_equivalence(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            document = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        for fragment in (
            'class="skip-link" href="#map"',
            'id="map" role="region"',
            'aria-describedby="map-description"',
            'tabindex="0"',
            'role="progressbar"',
            'aria-atomic="true"',
            'aria-label="Controles e dados de localização"',
        ):
            self.assertIn(fragment, document)
        self.assertIn(":focus-visible", stylesheet)
        self.assertIn("#map:focus-visible", stylesheet)
        self.assertIn(".sr-only", stylesheet)
        self.assertIn("document.createElement('button')", script)
        self.assertIn("Atualizar localização de", script)
        self.assertIn("Carregar histórico de", script)
        self.assertIn("Centralizar ${report.device_name} no mapa", script)
        self.assertIn("aria-valuenow", script)

    def test_kezpo_usability_states_are_actionable_and_semantic(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            document = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        self.assertIn("Carregando devices…", document)
        self.assertIn("Carregando reports…", document)
        for text in (
            "Nenhum device no cache",
            "Nenhuma localização no mapa",
            "Sincronizar devices",
            "Atualizar localizações",
        ):
            self.assertIn(text, script)
        for tone in ("success", "warning", "error", "info"):
            self.assertIn(tone, script)
            self.assertIn(f".status.{tone}" if tone != "info" else ".status", stylesheet)
        self.assertIn("aria-busy", script)
        self.assertIn(".empty-state", stylesheet)

    def test_kezpo_map_ux_has_empty_feedback_summary_legend_and_refit(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            document = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        for fragment in (
            'id="fit-reports"',
            'id="map-empty"',
            'id="map-summary"',
            'aria-labelledby="map-key-title"',
            "Nenhum report visível",
        ):
            self.assertIn(fragment, document)
        self.assertNotIn('class="map-key" aria-hidden="true"', document)
        self.assertIn("function fitVisibleReports()", script)
        self.assertIn("function updateMapFeedback(reportCount)", script)
        self.assertIn("mapNode.focus({ preventScroll: true })", script)
        self.assertIn(".map-empty", stylesheet)
        self.assertIn(".map-empty[hidden] { display: none; }", stylesheet)
        self.assertIn("--tablet-panel-width", stylesheet)
        self.assertIn("body.panel-collapsed .map-empty", stylesheet)
        self.assertIn("bottom: 80px", stylesheet)
        self.assertIn(".map-summary", stylesheet)
        self.assertIn(".map-tools", stylesheet)

    def test_kezpo_motion_contract_respects_reduced_motion_in_css_and_leaflet(self):
        with urllib.request.urlopen(self.base_url + "/styles.css", timeout=3) as response:
            stylesheet = response.read().decode("utf-8")
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=3) as response:
            script = response.read().decode("utf-8")

        for token in ("--motion-fast", "--motion-base", "--ease-standard"):
            self.assertIn(token, stylesheet)
        self.assertIn("button:active:not(:disabled)", stylesheet)
        self.assertIn(".report:active", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
        self.assertIn("--motion-fast: 0ms", stylesheet)
        skip_link_rule = stylesheet.split(".skip-link {", 1)[1].split("}", 1)[0]
        self.assertNotIn("transition:", skip_link_rule)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)')", script)
        self.assertIn("animate: !reducedMotion.matches", script)
        self.assertIn("map.setView(point, 15, { animate: false })", script)
        self.assertIn("map.flyTo(point, 15)", script)

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

    def test_container_environment_builds_explicit_exposure_policy(self):
        environment = {
            "GFMT_MODE": "demo",
            "GFMT_BIND_HOST": "0.0.0.0",
            "GFMT_PORT": "8765",
            "GFMT_DATABASE_PATH": "/data/find_hub.db",
            "GFMT_ALLOW_NON_LOOPBACK": "true",
            "GFMT_TRUSTED_HOSTS": "localhost:8765,app.example.com",
            "GFMT_TRUSTED_ORIGINS": "http://localhost:8765,https://app.example.com",
        }
        with mock.patch.dict(os.environ, environment):
            args = parse_args([])

        policy = HttpExposurePolicy(
            allow_non_loopback_bind=args.allow_non_loopback,
            trusted_hosts=tuple(args.trusted_host),
            trusted_origins=tuple(args.trusted_origin),
        )
        self.assertTrue(args.demo)
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8765)
        self.assertEqual(args.database, "/data/find_hub.db")
        self.assertTrue(policy.allow_non_loopback_bind)
        self.assertEqual(policy.trusted_hosts, ("localhost:8765", "app.example.com"))
        self.assertEqual(
            policy.trusted_origins,
            ("http://localhost:8765", "https://app.example.com"),
        )

    def test_main_py_starts_with_explicit_container_environment(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        authority = f"container.test:{port}"
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "GFMT_MODE": "demo",
                "GFMT_BIND_HOST": "0.0.0.0",
                "GFMT_PORT": str(port),
                "GFMT_DATABASE_PATH": str(Path(self.temp_dir.name) / "container-cli.db"),
                "GFMT_ALLOW_NON_LOOPBACK": "true",
                "GFMT_TRUSTED_HOSTS": authority,
                "GFMT_TRUSTED_ORIGINS": f"http://{authority}",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-u", "-B", "main.py", "--no-browser"],
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
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/v1/health",
                        headers={"Host": authority},
                    )
                    with urllib.request.urlopen(request, timeout=0.5) as response:
                        payload = json.load(response)
                    break
                except Exception:
                    if process.poll() is not None:
                        stdout, stderr = process.communicate(timeout=2)
                        self.fail(f"container-configured main.py exited early: {stdout} {stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("container-configured main.py did not start")
                    time.sleep(0.05)
            self.assertEqual(payload, {"status": "ok", "api_version": "v1", "database": "ok"})
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
