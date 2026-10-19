"""Side-effect-contained adapters for the existing Nova, Spot, FCM and crypto code."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Mapping
from typing import Protocol

from MapApp.domain.errors import (
    DecryptionFailed,
    GoogleUnavailable,
    KeyUnavailable,
    LocationTimeout,
    MalformedGoogleResponse,
)
from MapApp.domain.models import LocationKind, LocationStatus, RawLocationReport
from MapApp.domain.validation import require_text


NovaRequest = Callable[[str, str], str | bytes | None]
SpotRequest = Callable[[str, bytes], bytes | None]
LegacyDecrypt = Callable[[object], object]
RequestIdExtractor = Callable[[bytes], str]


class LegacyFcmReceiver(Protocol):
    location_update_callbacks: list[Callable[[str], None]]

    def register_for_location_updates(self, callback: Callable[[str], None]) -> str: ...

    def stop_listening(self) -> None: ...


def _load_nova_request() -> NovaRequest:
    from NovaApi.nova_request import nova_request

    return nova_request


def _load_spot_request() -> SpotRequest:
    from SpotApi.spot_request import spot_request

    return spot_request


def _load_fcm_receiver() -> LegacyFcmReceiver:
    from Auth.fcm_receiver import FcmReceiver

    return FcmReceiver()


def _load_decryptor() -> LegacyDecrypt:
    from NovaApi.ExecuteAction.LocateTracker.decrypt_locations import (
        decrypt_location_response_locations,
    )

    return decrypt_location_response_locations


def _extract_request_uuid(payload: bytes) -> str:
    from ProtoDecoders.decoder import parse_device_update_protobuf

    update = parse_device_update_protobuf(payload.hex())
    return update.fcmMetadata.requestUuid


def _require_bytes(payload: object) -> bytes:
    if not isinstance(payload, bytes):
        raise MalformedGoogleResponse()
    return payload


class LegacyNovaTransport:
    def __init__(self, request: NovaRequest | None = None) -> None:
        self._request = request

    def call(self, scope: str, payload: bytes) -> bytes:
        safe_scope = require_text(scope, "scope")
        request_payload = _require_bytes(payload)
        try:
            result = (self._request or _load_nova_request())(safe_scope, request_payload.hex())
        except Exception as exc:
            raise GoogleUnavailable() from exc
        if result is None:
            raise GoogleUnavailable()
        if isinstance(result, bytes):
            return result
        if not isinstance(result, str):
            raise MalformedGoogleResponse()
        try:
            return bytes.fromhex(result)
        except ValueError as exc:
            raise MalformedGoogleResponse() from exc


class LegacySpotTransport:
    def __init__(self, request: SpotRequest | None = None) -> None:
        self._request = request

    def call(self, method: str, payload: bytes) -> bytes:
        safe_method = require_text(method, "method")
        request_payload = _require_bytes(payload)
        try:
            result = (self._request or _load_spot_request())(safe_method, request_payload)
        except Exception as exc:
            raise GoogleUnavailable() from exc
        if result is None or result == b"":
            raise GoogleUnavailable()
        return _require_bytes(result)


class LegacyFcmSubscription:
    def __init__(
        self,
        receiver: LegacyFcmReceiver | None = None,
        request_id_extractor: RequestIdExtractor | None = None,
    ) -> None:
        self._receiver = receiver or _load_fcm_receiver()
        self._request_id_extractor = request_id_extractor or _extract_request_uuid
        self._condition = threading.Condition()
        self._messages: dict[str, list[bytes]] = {}
        self._callback_error: MalformedGoogleResponse | None = None
        self._closed = False
        try:
            registration_id = self._receiver.register_for_location_updates(self._on_message)
            self.registration_id = require_text(registration_id, "registration_id")
        except Exception as exc:
            self._remove_callback()
            raise GoogleUnavailable() from exc

    def _on_message(self, hex_payload: str) -> None:
        try:
            if not isinstance(hex_payload, str):
                raise ValueError
            payload = bytes.fromhex(hex_payload)
            request_uuid = require_text(
                self._request_id_extractor(payload), "request_uuid"
            )
        except Exception:
            with self._condition:
                self._callback_error = MalformedGoogleResponse()
                self._condition.notify_all()
            return
        with self._condition:
            if self._closed:
                return
            self._messages.setdefault(request_uuid, []).append(payload)
            self._condition.notify_all()

    def wait_for(self, request_uuid: str, timeout: float) -> bytes:
        safe_request_uuid = require_text(request_uuid, "request_uuid")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise LocationTimeout()
        timeout_value = float(timeout)
        if not math.isfinite(timeout_value) or timeout_value <= 0:
            raise LocationTimeout()
        deadline = time.monotonic() + timeout_value
        with self._condition:
            while True:
                if self._closed:
                    raise GoogleUnavailable("The notification subscription is closed.")
                queued = self._messages.get(safe_request_uuid)
                if queued:
                    payload = queued.pop(0)
                    if not queued:
                        del self._messages[safe_request_uuid]
                    return payload
                if self._callback_error is not None:
                    error = self._callback_error
                    self._callback_error = None
                    raise error
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LocationTimeout()
                self._condition.wait(remaining)

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._messages.clear()
            self._condition.notify_all()
        self._remove_callback()
        callbacks = getattr(self._receiver, "location_update_callbacks", ())
        if not callbacks:
            try:
                self._receiver.stop_listening()
            except Exception:
                pass

    def _remove_callback(self) -> None:
        callbacks = getattr(self._receiver, "location_update_callbacks", None)
        if isinstance(callbacks, list):
            while self._on_message in callbacks:
                callbacks.remove(self._on_message)

    def __enter__(self) -> "LegacyFcmSubscription":
        return self

    def __exit__(self, *args: object) -> bool:
        self.close()
        return False


class LegacyLocationDecryptor:
    def __init__(self, decrypt_function: LegacyDecrypt | None = None) -> None:
        self._decrypt_function = decrypt_function

    def decrypt(self, update: object) -> list[RawLocationReport]:
        try:
            result = (self._decrypt_function or _load_decryptor())(update)
        except SystemExit as exc:
            raise KeyUnavailable() from exc
        except Exception as exc:
            raise DecryptionFailed() from exc
        if not isinstance(result, list):
            raise MalformedGoogleResponse()
        try:
            return [self._map_report(item) for item in result]
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedGoogleResponse() from exc

    @staticmethod
    def _map_report(item: object) -> RawLocationReport:
        if not isinstance(item, Mapping):
            raise TypeError
        kind_text = str(item["kind"]).upper()
        kind = LocationKind(kind_text)
        status = LocationStatus(str(item["status"]).upper())
        common = {
            "kind": kind,
            "observed_at": item["timestamp"],
            "status": status,
            "is_own_report": item["is_own_report"],
        }
        if kind is LocationKind.SEMANTIC:
            return RawLocationReport(**common, semantic_name=item["name"])
        return RawLocationReport(
            **common,
            latitude=item["latitude"],
            longitude=item["longitude"],
            altitude=item.get("altitude"),
            accuracy=item.get("accuracy"),
        )
