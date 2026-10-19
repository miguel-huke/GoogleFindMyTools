import json
import mimetypes
import secrets
import threading
import webbrowser
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from MapApp.providers import DemoReportsProvider, GoogleFindMyToolsProvider


STATIC_ROOT = Path(__file__).with_name("static")
OSM_TILE_ORIGIN = "https://tile.openstreetmap.org/"


def fetch_osm_tile(z, x, y):
    request = Request(
        f"{OSM_TILE_ORIGIN}{z}/{x}/{y}.png",
        headers={"User-Agent": "GoogleFindMyToolsMap/1.0 (local application)"},
    )
    with urlopen(request, timeout=20) as response:
        return response.read(), response.headers.get_content_type()


class RasterTileProxy:
    """Bounded, allowlisted OSM raster proxy with an in-process cache."""

    def __init__(self, fetcher=fetch_osm_tile, max_entries=512):
        self._fetcher = fetcher
        self._max_entries = max_entries
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, z, x, y):
        z, x, y = int(z), int(x), int(y)
        limit = 1 << z
        if not (0 <= z <= 19 and 0 <= x < limit and 0 <= y < limit):
            raise ValueError("Invalid tile coordinates")
        key = z, x, y
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        payload, content_type = self._fetcher(z, x, y)
        result = payload, content_type
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
        return result


class DeviceRegistry:
    def __init__(self):
        self._devices = {}
        self._lock = threading.Lock()

    def replace(self, devices):
        public_devices = []
        private_devices = {}
        for name, canonic_id in devices:
            ref = secrets.token_urlsafe(12)
            private_devices[ref] = (canonic_id, name)
            public_devices.append({"ref": ref, "name": name})
        with self._lock:
            self._devices = private_devices
        return public_devices

    def resolve(self, ref):
        with self._lock:
            return self._devices.get(ref)


def create_handler(provider, tile_proxy):
    registry = DeviceRegistry()

    class MapRequestHandler(BaseHTTPRequestHandler):
        server_version = "GoogleFindMyToolsMap/1.0"

        def log_message(self, format_string, *args):
            # Avoid logging URLs that contain temporary device references.
            if self.path.startswith("/api/"):
                return
            super().log_message(format_string, *args)

        def end_headers(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            if self.path.startswith("/osm-tiles/"):
                self.send_header("Cache-Control", "public, max-age=604800")
            else:
                self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'self' https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://unpkg.com; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' https://unpkg.com; "
                "font-src 'self' data: https:;",
            )
            super().end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                return self._json({"status": "ok"})
            if parsed.path == "/api/devices":
                return self._list_devices()
            if parsed.path.startswith("/osm-tiles/"):
                return self._osm_tile(parsed.path)
            if parsed.path.startswith("/api/devices/") and parsed.path.endswith(
                "/reports"
            ):
                ref = unquote(parsed.path[len("/api/devices/") : -len("/reports")])
                return self._device_reports(ref)
            return self._static(parsed.path)

        def _osm_tile(self, request_path):
            try:
                parts = request_path.removeprefix("/osm-tiles/").split("/")
                if len(parts) != 3 or not parts[2].endswith(".png"):
                    raise ValueError("Invalid tile path")
                z, x, y = parts[0], parts[1], parts[2][:-4]
                payload, content_type = tile_proxy.get(z, x, y)
            except (ValueError, TypeError):
                return self.send_error(HTTPStatus.BAD_REQUEST)
            except Exception:
                return self.send_error(HTTPStatus.BAD_GATEWAY)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _list_devices(self):
            try:
                devices = registry.replace(provider.list_devices())
                self._json({"devices": devices})
            except Exception as error:
                self._api_error(error)

        def _device_reports(self, ref):
            device = registry.resolve(ref)
            if device is None:
                return self._json(
                    {"error": "Referência de device inválida ou expirada."},
                    HTTPStatus.NOT_FOUND,
                )
            canonic_id, name = device
            try:
                reports = provider.locate(canonic_id, name)
                self._json({"device": {"ref": ref, "name": name}, "reports": reports})
            except TimeoutError as error:
                self._json({"error": str(error)}, HTTPStatus.GATEWAY_TIMEOUT)
            except Exception as error:
                self._api_error(error)

        def _api_error(self, error):
            # Keep implementation details and credentials out of browser responses.
            self._json(
                {
                    "error": "A operação não foi concluída.",
                    "type": type(error).__name__,
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        def _static(self, request_path):
            relative = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
            candidate = (STATIC_ROOT / relative).resolve()
            try:
                candidate.relative_to(STATIC_ROOT.resolve())
            except ValueError:
                return self.send_error(HTTPStatus.NOT_FOUND)
            if not candidate.is_file():
                return self.send_error(HTTPStatus.NOT_FOUND)
            payload = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, data, status=HTTPStatus.OK):
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return MapRequestHandler


def create_server(
    host="127.0.0.1",
    port=8765,
    demo=False,
    provider=None,
    tile_fetcher=fetch_osm_tile,
):
    selected_provider = provider or (
        DemoReportsProvider() if demo else GoogleFindMyToolsProvider()
    )
    tile_proxy = RasterTileProxy(fetcher=tile_fetcher)
    return ThreadingHTTPServer(
        (host, port), create_handler(selected_provider, tile_proxy)
    )


def run_map_app(host="127.0.0.1", port=8765, demo=False, open_browser=True):
    server = create_server(host=host, port=port, demo=demo)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    mode = "demo" if demo else "real"
    print(f"GoogleFindMyTools Map ({mode}): {url}")
    print("Pressione Ctrl+C para encerrar.")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
