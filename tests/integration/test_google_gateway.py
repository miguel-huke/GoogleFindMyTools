import unittest

from MapApp.domain.errors import GoogleUnavailable, LocationTimeout, MalformedGoogleResponse
from MapApp.domain.models import LocationKind, LocationStatus, RawLocationReport
from MapApp.domain.ports import GoogleGateway
from MapApp.infrastructure.google import GoogleFindMyToolsGateway
from MapApp.infrastructure.google.gateway import NOVA_ACTION_SCOPE, NOVA_LIST_DEVICES_SCOPE
from ProtoDecoders import DeviceUpdate_pb2


class SyntheticSubscription:
    def __init__(self):
        self.registration_id = "synthetic-registration"
        self.payload = None
        self.closed = False
        self.waited_for = None
        self.force_timeout = False

    def wait_for(self, request_uuid, timeout):
        self.waited_for = (request_uuid, timeout)
        if self.force_timeout or self.payload is None:
            raise LocationTimeout()
        return self.payload

    def close(self):
        self.closed = True


class SyntheticNova:
    def __init__(self, subscription):
        self.subscription = subscription
        self.calls = []
        self.list_response = self._build_device_list()

    @staticmethod
    def _build_device_list():
        response = DeviceUpdate_pb2.DevicesList()
        spot = response.deviceMetadata.add()
        spot.userDefinedDeviceName = "Chaves sintéticas"
        spot.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_SPOT
        spot.identifierInformation.canonicIds.canonicId.add().id = "backend-spot-1"
        registration = spot.information.deviceRegistration
        registration.deviceTypeInformation.deviceType = DeviceUpdate_pb2.DEVICE_TYPE_KEYS
        registration.manufacturer = "Acme"
        registration.model = "Test One"
        spot.imageInformation.imageUrl = "https://example.invalid/device.png"

        android = response.deviceMetadata.add()
        android.userDefinedDeviceName = "Telefone sintético"
        android.identifierInformation.type = DeviceUpdate_pb2.IDENTIFIER_ANDROID
        android.identifierInformation.phoneInformation.canonicIds.canonicId.add().id = (
            "backend-phone-1"
        )
        android.information.deviceRegistration.manufacturer = "Example"
        android.information.deviceRegistration.model = "Phone"
        return response.SerializeToString()

    def call(self, scope, payload):
        self.calls.append((scope, payload))
        if scope == NOVA_LIST_DEVICES_SCOPE:
            request = DeviceUpdate_pb2.DevicesListRequest()
            request.ParseFromString(payload)
            if request.deviceListRequestPayload.type != DeviceUpdate_pb2.SPOT_DEVICE:
                raise AssertionError("unexpected device type")
            return self.list_response
        if scope == NOVA_ACTION_SCOPE:
            request = DeviceUpdate_pb2.ExecuteActionRequest()
            request.ParseFromString(payload)
            update = DeviceUpdate_pb2.DeviceUpdate()
            update.fcmMetadata.requestUuid = request.requestMetadata.requestUuid
            self.subscription.payload = update.SerializeToString()
            return b"accepted"
        raise AssertionError("unexpected Nova scope")


class SyntheticDecryptor:
    def __init__(self):
        self.updates = []

    def decrypt(self, update):
        self.updates.append(update)
        return [
            RawLocationReport(
                kind=LocationKind.POINT,
                observed_at=1_700_000_000,
                status=LocationStatus.CROWDSOURCED,
                is_own_report=False,
                latitude=-23.5,
                longitude=-46.6,
                accuracy=5,
            )
        ]


class GoogleGatewayIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.subscription = SyntheticSubscription()
        self.nova = SyntheticNova(self.subscription)
        self.decryptor = SyntheticDecryptor()
        request_ids = iter(("list-request", "locate-request", "extra-request"))
        self.gateway = GoogleFindMyToolsGateway(
            self.nova,
            lambda: self.subscription,
            self.decryptor,
            uuid_factory=lambda: next(request_ids),
            clock=lambda: 1_700_000_000,
            client_uuid="client-session",
        )

    def test_gateway_implements_domain_port_and_lists_protobuf_devices(self):
        self.assertIsInstance(self.gateway, GoogleGateway)
        beacons = self.gateway.list_beacons()
        self.assertEqual([item.canonic_id for item in beacons], ["backend-spot-1", "backend-phone-1"])
        self.assertEqual(beacons[0].display_name, "Chaves sintéticas")
        self.assertEqual(beacons[0].device_type, "DEVICE_TYPE_KEYS")
        self.assertEqual(beacons[0].manufacturer, "Acme")
        self.assertEqual(beacons[1].device_type, "ANDROID_DEVICE")

    def test_locate_runs_protobuf_nova_fcm_and_decrypt_flow(self):
        reports = self.gateway.locate("backend-spot-1", timeout_seconds=2.5)
        scope, payload = self.nova.calls[-1]
        request = DeviceUpdate_pb2.ExecuteActionRequest()
        request.ParseFromString(payload)
        self.assertEqual(scope, NOVA_ACTION_SCOPE)
        self.assertEqual(request.scope.device.canonicId.id, "backend-spot-1")
        self.assertEqual(request.requestMetadata.requestUuid, "list-request")
        self.assertEqual(request.requestMetadata.fmdClientUuid, "client-session")
        self.assertEqual(request.requestMetadata.gcmRegistrationId.id, "synthetic-registration")
        self.assertEqual(request.action.locateTracker.lastHighTrafficEnablingTime.seconds, 1_700_000_000)
        self.assertEqual(self.subscription.waited_for, ("list-request", 2.5))
        self.assertTrue(self.subscription.closed)
        self.assertEqual(len(self.decryptor.updates), 1)
        self.assertEqual(reports[0].kind, LocationKind.POINT)

    def test_timeout_is_propagated_and_subscription_is_closed(self):
        self.subscription.force_timeout = True
        with self.assertRaises(LocationTimeout):
            self.gateway.locate("backend-spot-1", timeout_seconds=0.01)
        self.assertTrue(self.subscription.closed)

    def test_mismatched_fcm_request_is_rejected_and_closed(self):
        class MismatchedNova(SyntheticNova):
            def call(inner_self, scope, payload):
                result = super(MismatchedNova, inner_self).call(scope, payload)
                if scope == NOVA_ACTION_SCOPE:
                    update = DeviceUpdate_pb2.DeviceUpdate()
                    update.fcmMetadata.requestUuid = "different-request"
                    inner_self.subscription.payload = update.SerializeToString()
                return result

        subscription = SyntheticSubscription()
        gateway = GoogleFindMyToolsGateway(
            MismatchedNova(subscription),
            lambda: subscription,
            self.decryptor,
            uuid_factory=lambda: "expected-request",
            client_uuid="client-session",
        )
        with self.assertRaises(MalformedGoogleResponse):
            gateway.locate("backend-spot-1", 1)
        self.assertTrue(subscription.closed)

    def test_nova_failure_is_propagated_and_subscription_is_closed(self):
        class FailingNova:
            def call(_self, _scope, _payload):
                raise GoogleUnavailable()

        subscription = SyntheticSubscription()
        gateway = GoogleFindMyToolsGateway(
            FailingNova(),
            lambda: subscription,
            self.decryptor,
            uuid_factory=lambda: "request-id",
            client_uuid="client-session",
        )
        with self.assertRaises(GoogleUnavailable):
            gateway.locate("backend-spot-1", 1)
        self.assertTrue(subscription.closed)

    def test_malformed_device_list_is_typed(self):
        self.nova.list_response = b"\x80"
        with self.assertRaises(MalformedGoogleResponse):
            self.gateway.list_beacons()


if __name__ == "__main__":
    unittest.main()
