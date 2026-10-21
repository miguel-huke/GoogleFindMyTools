"""Composition root for the local SQLite-backed map application."""

from __future__ import annotations

import signal
import threading
import webbrowser
from collections import OrderedDict
from pathlib import Path
from urllib.request import Request, urlopen

from MapApp.application import (
    JobCoordinator,
    JobSnapshot,
    QueryMapState,
    RefreshAllBeacons,
    RefreshBeaconLocations,
    SyncDevices,
)
from MapApp.domain.errors import NotFoundError
from MapApp.domain.models import SyncOperation, SyncState
from MapApp.domain.ports import GoogleGateway
from MapApp.infrastructure.google import (
    DemoGoogleGateway,
    GoogleFindMyToolsGateway,
    LegacyFcmSubscription,
    LegacyLocationDecryptor,
    LegacyNovaTransport,
)
from MapApp.infrastructure.persistence import SQLiteUnitOfWork, default_database_path
from MapApp.presentation.http import ApiServices, HttpExposurePolicy, create_api_server


OSM_TILE_ORIGIN = "https://tile.openstreetmap.org/"
TERMINAL_STATES = frozenset(
    {
        SyncState.SUCCEEDED,
        SyncState.PARTIAL,
        SyncState.FAILED,
        SyncState.TIMED_OUT,
        SyncState.CANCELLED,
    }
)


def fetch_osm_tile(z: int, x: int, y: int) -> tuple[bytes, str]:
    request = Request(
        f"{OSM_TILE_ORIGIN}{z}/{x}/{y}.png",
        headers={"User-Agent": "GoogleFindMyToolsMap/1.0 (local application)"},
    )
    with urlopen(request, timeout=20) as response:
        return response.read(), response.headers.get_content_type()


class RasterTileProxy:
    """Bounded, allowlisted OSM raster proxy with an in-process cache."""

    def __init__(self, fetcher=fetch_osm_tile, max_entries: int = 512) -> None:
        self._fetcher = fetcher
        self._max_entries = max_entries
        self._cache: OrderedDict[tuple[int, int, int], tuple[bytes, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, z: int, x: int, y: int) -> tuple[bytes, str]:
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
        result = self._fetcher(z, x, y)
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
        return result


def create_google_gateway() -> GoogleGateway:
    """Build lazy legacy adapters without authenticating or touching the network."""

    return GoogleFindMyToolsGateway(
        nova=LegacyNovaTransport(),
        subscription_factory=LegacyFcmSubscription,
        decryptor=LegacyLocationDecryptor(),
    )


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    demo: bool = False,
    *,
    gateway: GoogleGateway | None = None,
    tile_fetcher=fetch_osm_tile,
    database_path: str | Path | None = None,
    exposure_policy: HttpExposurePolicy | None = None,
):
    """Wire domain, persistence, integrations, jobs and HTTP into one local server."""

    selected_gateway = gateway or (DemoGoogleGateway() if demo else create_google_gateway())
    selected_database = Path(database_path) if database_path is not None else default_database_path()

    def unit_of_work() -> SQLiteUnitOfWork:
        return SQLiteUnitOfWork(selected_database)

    # Apply migrations before the first request so startup fails predictably.
    with unit_of_work():
        pass

    sync_devices = SyncDevices(selected_gateway, unit_of_work)
    refresh_one = RefreshBeaconLocations(selected_gateway, unit_of_work)
    refresh_all = RefreshAllBeacons(selected_gateway, unit_of_work)
    coordinator = JobCoordinator(refresh_all)
    tile_proxy = RasterTileProxy(fetcher=tile_fetcher)

    def get_job(job_id: str) -> JobSnapshot:
        with unit_of_work() as transaction:
            run = transaction.sync_runs.get(job_id)
        if run is None:
            raise KeyError(job_id)
        if run.operation is SyncOperation.REFRESH_ALL:
            try:
                return coordinator.snapshot(job_id)
            except NotFoundError as exc:
                raise KeyError(job_id) from exc
        total = max(run.devices_discovered, 1)
        completed = total if run.status in TERMINAL_STATES else 0
        return JobSnapshot(run, completed, total, False)

    services = ApiServices(
        queries=QueryMapState(unit_of_work),
        submit_sync_devices=sync_devices.execute,
        submit_refresh_all=coordinator.submit_refresh_all,
        submit_refresh_one=lambda public_id: refresh_one.execute(public_id).run,
        get_job=get_job,
        cancel_job=coordinator.cancel,
        tile_provider=tile_proxy.get,
    )
    try:
        return create_api_server(
            services,
            host=host,
            port=port,
            on_close=coordinator.close,
            exposure_policy=exposure_policy,
        )
    except Exception:
        coordinator.close()
        raise


def run_map_app(
    host: str = "127.0.0.1",
    port: int = 8765,
    demo: bool = False,
    open_browser: bool = True,
    database_path: str | Path | None = None,
    exposure_policy: HttpExposurePolicy | None = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        demo=demo,
        database_path=database_path,
        exposure_policy=exposure_policy,
    )
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    mode = "demo" if demo else "real"
    print(f"GoogleFindMyTools Map ({mode}): {url}")
    print("Pressione Ctrl+C para encerrar.")
    if open_browser:
        browser_timer = threading.Timer(0.3, lambda: webbrowser.open(url))
        browser_timer.daemon = True
        browser_timer.start()
    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def stop_on_sigterm(_signum, _frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop_on_sigterm)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
