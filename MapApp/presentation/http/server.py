"""Dependency-injected HTTP API v1 for local SQLite state and jobs."""

from __future__ import annotations

import json
import mimetypes
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from MapApp.application.jobs import JobSnapshot
from MapApp.application.query_map import QueryMapState
from MapApp.domain.errors import (
    ApplicationError,
    AuthenticationExpired,
    AuthenticationRequired,
    DomainValidationError,
    GoogleUnavailable,
    LocationTimeout,
    MalformedGoogleResponse,
    NotFoundError,
    RateLimited,
)
from MapApp.domain.models import SyncRun

from .presenters import device_json, job_json, location_json, map_geojson


SubmitJob = Callable[[], SyncRun]
SubmitDeviceJob = Callable[[str], SyncRun]
GetJob = Callable[[str], JobSnapshot]
CancelJob = Callable[[str], bool]
SessionStatus = Callable[[], bool]
TileProvider = Callable[[int, int, int], tuple[bytes, str]]
CloseCallback = Callable[[], None]
STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CSRF_HEADER = "X-FindHub-CSRF"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)


@dataclass(frozen=True, slots=True)
class ApiServices:
    queries: QueryMapState
    submit_sync_devices: SubmitJob
    submit_refresh_all: SubmitJob
    submit_refresh_one: SubmitDeviceJob
    get_job: GetJob
    cancel_job: CancelJob
    session_status: SessionStatus | None = None
    submit_connect: SubmitJob | None = None
    tile_provider: TileProvider | None = None


def _http_status(error: ApplicationError) -> HTTPStatus:
    if isinstance(error, (AuthenticationRequired, AuthenticationExpired)):
        return HTTPStatus.UNAUTHORIZED
    if isinstance(error, DomainValidationError):
        return HTTPStatus.BAD_REQUEST
    if isinstance(error, NotFoundError):
        return HTTPStatus.NOT_FOUND
    if isinstance(error, RateLimited):
        return HTTPStatus.TOO_MANY_REQUESTS
    if isinstance(error, LocationTimeout):
        return HTTPStatus.GATEWAY_TIMEOUT
    if isinstance(error, (GoogleUnavailable, MalformedGoogleResponse)):
        return HTTPStatus.BAD_GATEWAY
    return HTTPStatus.INTERNAL_SERVER_ERROR


def create_api_handler(services: ApiServices):
    csrf_token = secrets.token_urlsafe(32)

    class ApiRequestHandler(BaseHTTPRequestHandler):
        server_version = "GoogleFindMyToolsApi/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            super().end_headers()

        def do_GET(self) -> None:
            if not self._trusted_host():
                return self._security_error("invalid_host", "Request host is not allowed.", HTTPStatus.MISDIRECTED_REQUEST)
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/v1/health":
                    services.queries.list_devices()
                    return self._json({"status": "ok", "api_version": "v1", "database": "ok"})
                if parsed.path == "/api/v1/session":
                    if services.session_status is None:
                        return self._json({"connected": False, "available": False, "csrf_token": csrf_token})
                    return self._json(
                        {"connected": bool(services.session_status()), "available": True, "csrf_token": csrf_token}
                    )
                if parsed.path == "/api/v1/devices":
                    return self._json({"devices": [device_json(item) for item in services.queries.list_devices()]})
                if parsed.path == "/api/v1/map/latest":
                    return self._json(map_geojson(services.queries.list_devices()))
                if parsed.path.startswith("/api/v1/jobs/"):
                    job_id = self._one_segment(parsed.path, "/api/v1/jobs/")
                    return self._json(job_json(self._get_job(job_id)))
                if parsed.path.startswith("/api/v1/devices/"):
                    return self._device_get(parsed.path, parsed.query)
                if parsed.path.startswith("/osm-tiles/"):
                    return self._tile(parsed.path)
                if not parsed.path.startswith("/api/"):
                    return self._static(parsed.path)
                return self._error(NotFoundError())
            except ConnectionError:
                return
            except ApplicationError as error:
                return self._error(error)
            except Exception:
                return self._error(ApplicationError())

        def do_POST(self) -> None:
            if not self._trusted_host():
                return self._security_error("invalid_host", "Request host is not allowed.", HTTPStatus.MISDIRECTED_REQUEST)
            if not self._trusted_origin():
                return self._security_error("invalid_origin", "Request origin is not allowed.", HTTPStatus.FORBIDDEN)
            if not secrets.compare_digest(self.headers.get(CSRF_HEADER, ""), csrf_token):
                return self._security_error("invalid_csrf", "CSRF token is missing or invalid.", HTTPStatus.FORBIDDEN)
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/v1/session/connect":
                    if services.submit_connect is None:
                        return self._json(
                            {
                                "error": {
                                    "code": "not_implemented",
                                    "message": "Interactive connection is not configured.",
                                    "correlation_id": secrets.token_hex(8),
                                }
                            },
                            HTTPStatus.NOT_IMPLEMENTED,
                        )
                    return self._accepted(services.submit_connect())
                if parsed.path == "/api/v1/sync/devices":
                    return self._accepted(services.submit_sync_devices())
                if parsed.path == "/api/v1/sync/locations":
                    return self._accepted(services.submit_refresh_all())
                if parsed.path.startswith("/api/v1/jobs/") and parsed.path.endswith("/cancel"):
                    job_id = self._middle_segment(parsed.path, "/api/v1/jobs/", "/cancel")
                    self._get_job(job_id)
                    services.cancel_job(job_id)
                    return self._json(job_json(self._get_job(job_id)), HTTPStatus.ACCEPTED)
                if parsed.path.startswith("/api/v1/devices/") and parsed.path.endswith("/refresh"):
                    public_id = self._middle_segment(parsed.path, "/api/v1/devices/", "/refresh")
                    return self._accepted(services.submit_refresh_one(public_id))
                return self._error(NotFoundError())
            except ConnectionError:
                return
            except ApplicationError as error:
                return self._error(error)
            except Exception:
                return self._error(ApplicationError())

        def _device_get(self, path: str, query: str) -> None:
            suffix = path.removeprefix("/api/v1/devices/")
            if suffix.endswith("/locations"):
                public_id = self._middle_segment(path, "/api/v1/devices/", "/locations")
                raw_limit = parse_qs(query).get("limit", ["100"])[0]
                try:
                    limit = int(raw_limit)
                except ValueError as exc:
                    raise DomainValidationError("limit") from exc
                locations = services.queries.history(public_id, limit=limit)
                return self._json({"locations": [location_json(item) for item in locations]})
            public_id = self._one_segment(path, "/api/v1/devices/")
            return self._json({"device": device_json(services.queries.get_device(public_id))})

        def _accepted(self, run: SyncRun) -> None:
            return self._json(
                {"job_id": run.id, "operation": run.operation.value, "status": run.status.value},
                HTTPStatus.ACCEPTED,
            )

        def _tile(self, path: str) -> None:
            if services.tile_provider is None:
                raise NotFoundError()
            parts = path.removeprefix("/osm-tiles/").removesuffix(".png").split("/")
            if len(parts) != 3:
                raise NotFoundError()
            try:
                zoom, tile_x, tile_y = (int(part) for part in parts)
            except ValueError as exc:
                raise NotFoundError() from exc
            payload, content_type = services.tile_provider(zoom, tile_x, tile_y)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            self.wfile.write(payload)

        def _static(self, path: str) -> None:
            relative = "index.html" if path == "/" else unquote(path).lstrip("/")
            candidate = (STATIC_ROOT / relative).resolve()
            try:
                candidate.relative_to(STATIC_ROOT.resolve())
            except ValueError as exc:
                raise NotFoundError() from exc
            if not candidate.is_file():
                raise NotFoundError()
            payload = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)

        def _trusted_host(self) -> bool:
            raw_host = self.headers.get("Host", "")
            if not raw_host or any(character in raw_host for character in "\r\n,\\"):
                return False
            try:
                parsed = urlsplit(f"//{raw_host}")
                hostname = parsed.hostname
                port = parsed.port
            except ValueError:
                return False
            if hostname is None or hostname.lower() not in LOOPBACK_HOSTS:
                return False
            expected_port = int(self.server.server_address[1])
            return port == expected_port or (port is None and expected_port == 80)

        def _trusted_origin(self) -> bool:
            origin = self.headers.get("Origin", "")
            if not origin or origin == "null":
                return False
            try:
                parsed = urlparse(origin)
                hostname = parsed.hostname
                origin_port = parsed.port
            except ValueError:
                return False
            expected_port = int(self.server.server_address[1])
            return (
                parsed.scheme == "http"
                and parsed.path in ("", "/")
                and not parsed.params
                and not parsed.query
                and not parsed.fragment
                and hostname is not None
                and hostname.lower() in LOOPBACK_HOSTS
                and origin_port == expected_port
            )

        def _security_error(self, code: str, message: str, status: HTTPStatus) -> None:
            return self._json(
                {"error": {"code": code, "message": message, "correlation_id": secrets.token_hex(8)}},
                status,
            )

        @staticmethod
        def _get_job(job_id: str) -> JobSnapshot:
            try:
                return services.get_job(job_id)
            except KeyError as exc:
                raise NotFoundError() from exc

        @staticmethod
        def _one_segment(path: str, prefix: str) -> str:
            value = unquote(path.removeprefix(prefix))
            if not value or "/" in value:
                raise NotFoundError()
            return value

        @staticmethod
        def _middle_segment(path: str, prefix: str, suffix: str) -> str:
            value = unquote(path[len(prefix) : -len(suffix)])
            if not value or "/" in value:
                raise NotFoundError()
            return value

        def _error(self, error: ApplicationError) -> None:
            return self._json(
                {
                    "error": {
                        "code": error.code,
                        "message": error.safe_message,
                        "correlation_id": secrets.token_hex(8),
                    }
                },
                _http_status(error),
            )

        def _json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return ApiRequestHandler


def create_api_server(
    services: ApiServices,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    on_close: CloseCallback | None = None,
) -> ThreadingHTTPServer:
    if host.lower() not in LOOPBACK_HOSTS:
        raise ValueError("The API server may only bind to a loopback host.")

    class LocalApiServer(ThreadingHTTPServer):
        daemon_threads = True
        _resources_closed = False

        def handle_error(self, _request: object, _client_address: object) -> None:
            # Browser disconnects must not dump request context or local paths.
            return

        def server_close(self) -> None:
            try:
                super().server_close()
            finally:
                if not self._resources_closed and on_close is not None:
                    self._resources_closed = True
                    on_close()

    return LocalApiServer((host, port), create_api_handler(services))
