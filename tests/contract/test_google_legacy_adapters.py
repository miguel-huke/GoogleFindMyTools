import unittest

from MapApp.domain.errors import (
    DecryptionFailed,
    GoogleUnavailable,
    KeyUnavailable,
    LocationTimeout,
    MalformedGoogleResponse,
)
from MapApp.domain.models import LocationKind, LocationStatus
from MapApp.infrastructure.google import (
    FcmSubscription,
    LegacyFcmSubscription,
    LegacyLocationDecryptor,
    LegacyNovaTransport,
    LegacySpotTransport,
    LocationDecryptor,
    NovaTransport,
    SpotTransport,
)


class FakeFcmReceiver:
    def __init__(self):
        self.location_update_callbacks = []
        self.stopped = False

    def register_for_location_updates(self, callback):
        self.location_update_callbacks.append(callback)
        return "synthetic-registration"

    def emit(self, payload):
        for callback in tuple(self.location_update_callbacks):
            callback(payload.hex())

    def stop_listening(self):
        self.stopped = True


class TransportContractTest(unittest.TestCase):
    def test_nova_converts_bytes_to_legacy_hex_and_back(self):
        calls = []

        def request(scope, hex_payload):
            calls.append((scope, hex_payload))
            return "aabb"

        transport = LegacyNovaTransport(request)
        self.assertIsInstance(transport, NovaTransport)
        self.assertEqual(transport.call("scope", b"\x01\x02"), b"\xaa\xbb")
        self.assertEqual(calls, [("scope", "0102")])

    def test_nova_rejects_missing_or_malformed_response(self):
        with self.assertRaises(GoogleUnavailable):
            LegacyNovaTransport(lambda _scope, _payload: None).call("scope", b"data")
        with self.assertRaises(MalformedGoogleResponse):
            LegacyNovaTransport(lambda _scope, _payload: "not-hex").call("scope", b"data")

    def test_spot_forwards_bytes_and_types_failures(self):
        calls = []

        def request(method, payload):
            calls.append((method, payload))
            return b"response"

        transport = LegacySpotTransport(request)
        self.assertIsInstance(transport, SpotTransport)
        self.assertEqual(transport.call("Method", b"request"), b"response")
        self.assertEqual(calls, [("Method", b"request")])
        with self.assertRaises(GoogleUnavailable):
            LegacySpotTransport(lambda _method, _payload: b"").call("Method", b"request")


class FcmSubscriptionContractTest(unittest.TestCase):
    @staticmethod
    def request_id(payload):
        return payload.decode("ascii").split("|", 1)[0]

    def test_correlates_buffered_message_by_request_uuid(self):
        receiver = FakeFcmReceiver()
        subscription = LegacyFcmSubscription(receiver, self.request_id)
        self.assertIsInstance(subscription, FcmSubscription)
        self.assertEqual(subscription.registration_id, "synthetic-registration")
        receiver.emit(b"other|payload")
        receiver.emit(b"wanted|payload")
        self.assertEqual(subscription.wait_for("wanted", 0.1), b"wanted|payload")
        self.assertEqual(subscription.wait_for("other", 0.1), b"other|payload")

    def test_timeout_and_malformed_callback_are_typed(self):
        receiver = FakeFcmReceiver()
        subscription = LegacyFcmSubscription(receiver, self.request_id)
        with self.assertRaises(LocationTimeout):
            subscription.wait_for("missing", 0.01)
        receiver.location_update_callbacks[0]("not-hex")
        with self.assertRaises(MalformedGoogleResponse):
            subscription.wait_for("missing", 0.1)
        subscription.close()

    def test_close_unregisters_callback_and_stops_last_listener(self):
        receiver = FakeFcmReceiver()
        subscription = LegacyFcmSubscription(receiver, self.request_id)
        subscription.close()
        subscription.close()
        self.assertEqual(receiver.location_update_callbacks, [])
        self.assertTrue(receiver.stopped)
        with self.assertRaises(GoogleUnavailable):
            subscription.wait_for("request", 0.1)


class DecryptorContractTest(unittest.TestCase):
    def test_maps_point_and_semantic_reports_to_domain(self):
        legacy_reports = [
            {
                "kind": "point",
                "latitude": -23.5,
                "longitude": -46.6,
                "altitude": -4,
                "accuracy": 7,
                "timestamp": 100,
                "status": "CROWDSOURCED",
                "is_own_report": False,
            },
            {
                "kind": "semantic",
                "name": "Casa sintética",
                "timestamp": 101,
                "status": "SEMANTIC",
                "is_own_report": True,
            },
        ]
        decryptor = LegacyLocationDecryptor(lambda _update: legacy_reports)
        self.assertIsInstance(decryptor, LocationDecryptor)
        reports = decryptor.decrypt(object())
        self.assertEqual(reports[0].kind, LocationKind.POINT)
        self.assertEqual(reports[0].status, LocationStatus.CROWDSOURCED)
        self.assertEqual(reports[0].altitude, -4)
        self.assertEqual(reports[1].kind, LocationKind.SEMANTIC)
        self.assertEqual(reports[1].semantic_name, "Casa sintética")

    def test_decrypt_and_key_failures_are_sanitized(self):
        def failed(_update):
            raise RuntimeError("sensitive legacy detail")

        def missing_key(_update):
            raise SystemExit(1)

        with self.assertRaises(DecryptionFailed) as failure:
            LegacyLocationDecryptor(failed).decrypt(object())
        self.assertNotIn("sensitive", str(failure.exception).lower())
        with self.assertRaises(KeyUnavailable):
            LegacyLocationDecryptor(missing_key).decrypt(object())

    def test_malformed_legacy_report_is_rejected(self):
        decryptor = LegacyLocationDecryptor(lambda _update: [{"kind": "point"}])
        with self.assertRaises(MalformedGoogleResponse):
            decryptor.decrypt(object())


if __name__ == "__main__":
    unittest.main()
