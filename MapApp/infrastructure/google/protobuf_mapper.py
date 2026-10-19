"""Pure Protobuf construction and parsing for the Google integration boundary."""

from __future__ import annotations

from google.protobuf.message import DecodeError, Message

from MapApp.domain.errors import DomainValidationError, MalformedGoogleResponse
from MapApp.domain.models import DiscoveredBeacon
from MapApp.domain.validation import require_non_negative_int, require_text
from ProtoDecoders import DeviceUpdate_pb2


class GoogleProtobufCodec:
    def build_list_request(self, request_uuid: str) -> bytes:
        request = DeviceUpdate_pb2.DevicesListRequest()
        request.deviceListRequestPayload.type = DeviceUpdate_pb2.DeviceType.SPOT_DEVICE
        request.deviceListRequestPayload.id = require_text(request_uuid, "request_uuid")
        return request.SerializeToString()

    def parse_beacons(self, payload: bytes) -> list[DiscoveredBeacon]:
        if not isinstance(payload, bytes):
            raise MalformedGoogleResponse()
        response = DeviceUpdate_pb2.DevicesList()
        try:
            response.ParseFromString(payload)
            beacons: list[DiscoveredBeacon] = []
            seen_ids: set[str] = set()
            for metadata in response.deviceMetadata:
                identifiers = metadata.identifierInformation
                if identifiers.type == DeviceUpdate_pb2.IDENTIFIER_ANDROID:
                    canonic_ids = identifiers.phoneInformation.canonicIds.canonicId
                    device_type = "ANDROID_DEVICE"
                else:
                    canonic_ids = identifiers.canonicIds.canonicId
                    raw_type = metadata.information.deviceRegistration.deviceTypeInformation.deviceType
                    device_type = DeviceUpdate_pb2.SpotDeviceType.Name(raw_type)
                registration = metadata.information.deviceRegistration
                for identifier in canonic_ids:
                    canonic_id = require_text(identifier.id, "canonic_id")
                    if canonic_id in seen_ids:
                        continue
                    seen_ids.add(canonic_id)
                    beacons.append(
                        DiscoveredBeacon(
                            canonic_id=canonic_id,
                            display_name=require_text(metadata.userDefinedDeviceName, "display_name"),
                            device_type=device_type,
                            manufacturer=registration.manufacturer or None,
                            model=registration.model or None,
                            image_url=metadata.imageInformation.imageUrl or None,
                        )
                    )
            return beacons
        except (DecodeError, DomainValidationError, TypeError, ValueError) as exc:
            raise MalformedGoogleResponse() from exc

    def build_locate_request(
        self,
        canonic_id: str,
        registration_id: str,
        request_uuid: str,
        client_uuid: str,
        now_utc_seconds: int,
    ) -> bytes:
        request = DeviceUpdate_pb2.ExecuteActionRequest()
        request.scope.type = DeviceUpdate_pb2.DeviceType.SPOT_DEVICE
        request.scope.device.canonicId.id = require_text(canonic_id, "canonic_id")
        request.requestMetadata.type = DeviceUpdate_pb2.DeviceType.SPOT_DEVICE
        request.requestMetadata.requestUuid = require_text(request_uuid, "request_uuid")
        request.requestMetadata.fmdClientUuid = require_text(client_uuid, "client_uuid")
        request.requestMetadata.gcmRegistrationId.id = require_text(
            registration_id, "registration_id"
        )
        request.requestMetadata.unknown = True
        request.action.locateTracker.lastHighTrafficEnablingTime.seconds = require_non_negative_int(
            now_utc_seconds, "now_utc_seconds"
        )
        request.action.locateTracker.contributorType = (
            DeviceUpdate_pb2.SpotContributorType.FMDN_ALL_LOCATIONS
        )
        return request.SerializeToString()

    def parse_device_update(self, payload: bytes) -> Message:
        if not isinstance(payload, bytes):
            raise MalformedGoogleResponse()
        update = DeviceUpdate_pb2.DeviceUpdate()
        try:
            update.ParseFromString(payload)
        except DecodeError as exc:
            raise MalformedGoogleResponse() from exc
        return update

    def device_update_request_uuid(self, update: object) -> str:
        if not isinstance(update, DeviceUpdate_pb2.DeviceUpdate):
            raise MalformedGoogleResponse()
        try:
            return require_text(update.fcmMetadata.requestUuid, "request_uuid")
        except DomainValidationError as exc:
            raise MalformedGoogleResponse() from exc
