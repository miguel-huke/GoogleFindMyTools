"""Safe localhost smoke test for the containerized map application."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


TERMINAL_STATES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class SmokeFailure(RuntimeError):
    """A sanitized failure suitable for local logs and CI output."""


def _validated_base_url(value: str) -> str:
    candidate = value.rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOCAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeFailure("base URL must be an exact localhost HTTP origin")
    return candidate


def _request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    csrf_token: str | None = None,
    timeout: float = 3,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if method == "POST":
        headers["Origin"] = base_url
        if csrf_token:
            headers["X-FindHub-CSRF"] = csrf_token
    request = urllib.request.Request(base_url + path, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            payload = json.load(error)
            code = payload.get("error", {}).get("code", "http_error")
        except Exception:
            code = "http_error"
        raise SmokeFailure(f"{path} returned HTTP {error.code} ({code})") from None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SmokeFailure(f"{path} is unavailable or returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{path} returned an invalid object")
    return payload


def _poll_job(base_url: str, job_id: str, *, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _request_json(base_url, f"/api/v1/jobs/{job_id}")
        status = job.get("status")
        if status in TERMINAL_STATES:
            return job
        time.sleep(0.1)
    raise SmokeFailure("job did not finish before the smoke timeout")


def _submit_and_wait(base_url: str, path: str, csrf_token: str, *, timeout: float) -> dict[str, object]:
    submitted = _request_json(base_url, path, method="POST", csrf_token=csrf_token)
    job_id = submitted.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise SmokeFailure(f"{path} did not return a public job ID")
    return _poll_job(base_url, job_id, timeout=timeout)


def _cached_counts(base_url: str) -> tuple[int, int]:
    devices_payload = _request_json(base_url, "/api/v1/devices")
    map_payload = _request_json(base_url, "/api/v1/map/latest")
    devices = devices_payload.get("devices")
    features = map_payload.get("features")
    if not isinstance(devices, list) or not isinstance(features, list):
        raise SmokeFailure("cache endpoints returned invalid collections")
    serialized = json.dumps((devices_payload, map_payload), separators=(",", ":")).lower()
    for private_field in ("canonic_id", "canonical_id", "identity_key", "auth_token"):
        if private_field in serialized:
            raise SmokeFailure("a private backend field crossed the presentation boundary")
    return len(devices), len(features)


def run_smoke(base_url: str, *, verify_cache: bool = False, timeout: float = 20) -> dict[str, object]:
    base_url = _validated_base_url(base_url)
    health = _request_json(base_url, "/api/v1/health")
    if health.get("status") != "ok" or health.get("database") != "ok":
        raise SmokeFailure("healthcheck did not confirm API and database readiness")

    if verify_cache:
        device_count, feature_count = _cached_counts(base_url)
        if device_count < 1 or feature_count < 1:
            raise SmokeFailure("persisted demo cache is empty after restart")
        return {"mode": "cache", "status": "ok", "devices": device_count, "map_features": feature_count}

    session = _request_json(base_url, "/api/v1/session")
    csrf_token = session.get("csrf_token")
    if not isinstance(csrf_token, str) or len(csrf_token) < 32:
        raise SmokeFailure("session did not return a valid CSRF token")

    sync_job = _submit_and_wait(base_url, "/api/v1/sync/devices", csrf_token, timeout=timeout)
    if sync_job.get("status") != "SUCCEEDED":
        raise SmokeFailure(f"device synchronization ended as {sync_job.get('status', 'UNKNOWN')}")

    refresh_job = _submit_and_wait(base_url, "/api/v1/sync/locations", csrf_token, timeout=timeout)
    if refresh_job.get("status") != "SUCCEEDED":
        raise SmokeFailure(f"location refresh ended as {refresh_job.get('status', 'UNKNOWN')}")

    device_count, feature_count = _cached_counts(base_url)
    if device_count < 1 or feature_count < 1:
        raise SmokeFailure("demo synchronization did not populate the map cache")
    return {
        "mode": "full",
        "status": "ok",
        "devices": device_count,
        "map_features": feature_count,
        "sync_status": sync_job["status"],
        "refresh_status": refresh_job["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized localhost container smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--verify-cache", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args(argv)
    try:
        result = run_smoke(args.base_url, verify_cache=args.verify_cache, timeout=args.timeout)
    except SmokeFailure as error:
        print(f"container smoke failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
