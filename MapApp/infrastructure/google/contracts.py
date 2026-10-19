"""Narrow integration contracts used by the future Google gateway."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from MapApp.domain.models import DiscoveredBeacon, RawLocationReport


@runtime_checkable
class NovaTransport(Protocol):
    def call(self, scope: str, payload: bytes) -> bytes: ...


@runtime_checkable
class SpotTransport(Protocol):
    def call(self, method: str, payload: bytes) -> bytes: ...


@runtime_checkable
class FcmSubscription(Protocol):
    registration_id: str

    def wait_for(self, request_uuid: str, timeout: float) -> bytes: ...

    def close(self) -> None: ...


@runtime_checkable
class LocationDecryptor(Protocol):
    def decrypt(self, update: object) -> list[RawLocationReport]: ...


@runtime_checkable
class GoogleProtocolCodec(Protocol):
    def build_list_request(self, request_uuid: str) -> bytes: ...

    def parse_beacons(self, payload: bytes) -> list[DiscoveredBeacon]: ...

    def build_locate_request(
        self,
        canonic_id: str,
        registration_id: str,
        request_uuid: str,
        client_uuid: str,
        now_utc_seconds: int,
    ) -> bytes: ...

    def parse_device_update(self, payload: bytes) -> object: ...

    def device_update_request_uuid(self, update: object) -> str: ...
