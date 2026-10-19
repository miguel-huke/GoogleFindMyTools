"""Google gateway orchestrating transports without persistence or presentation concerns."""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Callable

from MapApp.domain.errors import ApplicationError, LocationTimeout, MalformedGoogleResponse
from MapApp.domain.models import DiscoveredBeacon, RawLocationReport
from MapApp.domain.validation import require_text

from .contracts import FcmSubscription, GoogleProtocolCodec, LocationDecryptor, NovaTransport
from .protobuf_mapper import GoogleProtobufCodec


NOVA_LIST_DEVICES_SCOPE = "nbe_list_devices"
NOVA_ACTION_SCOPE = "nbe_execute_action"

SubscriptionFactory = Callable[[], FcmSubscription]
UuidFactory = Callable[[], str]
Clock = Callable[[], int]


class GoogleFindMyToolsGateway:
    def __init__(
        self,
        nova: NovaTransport,
        subscription_factory: SubscriptionFactory,
        decryptor: LocationDecryptor,
        *,
        codec: GoogleProtocolCodec | None = None,
        uuid_factory: UuidFactory | None = None,
        clock: Clock | None = None,
        client_uuid: str | None = None,
    ) -> None:
        self._nova = nova
        self._subscription_factory = subscription_factory
        self._decryptor = decryptor
        self._codec = codec or GoogleProtobufCodec()
        self._uuid_factory = uuid_factory or (lambda: str(uuid.uuid4()))
        self._clock = clock or (lambda: int(time.time()))
        self._client_uuid = require_text(
            client_uuid if client_uuid is not None else self._uuid_factory(),
            "client_uuid",
        )

    def list_beacons(self) -> list[DiscoveredBeacon]:
        request_uuid = self._new_request_uuid()
        try:
            request = self._codec.build_list_request(request_uuid)
            response = self._nova.call(NOVA_LIST_DEVICES_SCOPE, request)
            beacons = self._codec.parse_beacons(response)
        except ApplicationError:
            raise
        except Exception as exc:
            raise MalformedGoogleResponse() from exc
        if not all(isinstance(beacon, DiscoveredBeacon) for beacon in beacons):
            raise MalformedGoogleResponse()
        return beacons

    def locate(self, canonic_id: str, timeout_seconds: float) -> list[RawLocationReport]:
        safe_canonic_id = require_text(canonic_id, "canonic_id")
        timeout = self._validate_timeout(timeout_seconds)
        request_uuid = self._new_request_uuid()
        subscription: FcmSubscription | None = None
        try:
            subscription = self._subscription_factory()
            request = self._codec.build_locate_request(
                safe_canonic_id,
                require_text(subscription.registration_id, "registration_id"),
                request_uuid,
                self._client_uuid,
                self._clock(),
            )
            self._nova.call(NOVA_ACTION_SCOPE, request)
            update_payload = subscription.wait_for(request_uuid, timeout)
            update = self._codec.parse_device_update(update_payload)
            if self._codec.device_update_request_uuid(update) != request_uuid:
                raise MalformedGoogleResponse()
            reports = self._decryptor.decrypt(update)
            if not isinstance(reports, list) or not all(
                isinstance(report, RawLocationReport) for report in reports
            ):
                raise MalformedGoogleResponse()
            return reports
        except ApplicationError:
            raise
        except Exception as exc:
            raise MalformedGoogleResponse() from exc
        finally:
            if subscription is not None:
                try:
                    subscription.close()
                except Exception:
                    pass

    def _new_request_uuid(self) -> str:
        try:
            return require_text(self._uuid_factory(), "request_uuid")
        except ApplicationError:
            raise
        except Exception as exc:
            raise MalformedGoogleResponse() from exc

    @staticmethod
    def _validate_timeout(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LocationTimeout()
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise LocationTimeout()
        return timeout
