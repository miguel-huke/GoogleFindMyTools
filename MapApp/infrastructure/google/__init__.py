"""Injectable boundaries around the legacy GoogleFindMyTools integrations."""

from .contracts import (
    FcmSubscription,
    GoogleProtocolCodec,
    LocationDecryptor,
    NovaTransport,
    SpotTransport,
)
from .demo_gateway import DemoGoogleGateway
from .gateway import GoogleFindMyToolsGateway
from .legacy_adapters import (
    LegacyFcmSubscription,
    LegacyLocationDecryptor,
    LegacyNovaTransport,
    LegacySpotTransport,
)

__all__ = [
    "FcmSubscription",
    "DemoGoogleGateway",
    "GoogleFindMyToolsGateway",
    "GoogleProtocolCodec",
    "LegacyFcmSubscription",
    "LegacyLocationDecryptor",
    "LegacyNovaTransport",
    "LegacySpotTransport",
    "LocationDecryptor",
    "NovaTransport",
    "SpotTransport",
]
