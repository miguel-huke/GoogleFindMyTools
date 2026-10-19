"""Deterministic Google gateway replacement for local demos and tests."""

from __future__ import annotations

import datetime

from MapApp.domain.models import (
    DiscoveredBeacon,
    LocationKind,
    LocationStatus,
    RawLocationReport,
)


class DemoGoogleGateway:
    """Return synthetic beacons and coordinates without authentication or network."""

    _devices = (
        DiscoveredBeacon("demo-keys", "Chaves (demo)", "DEVICE_TYPE_KEYS"),
        DiscoveredBeacon("demo-bag", "Mochila (demo)", "DEVICE_TYPE_TRACKER"),
    )
    _locations = {
        "demo-keys": (
            (-23.56144, -46.65588, 760, 18.0, 0),
            (-23.56018, -46.65374, 762, 12.0, 420),
            (-23.55892, -46.65136, 765, 9.0, 840),
        ),
        "demo-bag": (
            (-23.56631, -46.65018, 748, 26.0, 120),
            (-23.56482, -46.64802, 751, 17.0, 600),
        ),
    }

    def list_beacons(self) -> list[DiscoveredBeacon]:
        return list(self._devices)

    def locate(self, canonic_id: str, timeout_seconds: float) -> list[RawLocationReport]:
        del timeout_seconds
        base = int(
            datetime.datetime(
                2026, 10, 19, 15, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
        )
        return [
            RawLocationReport(
                kind=LocationKind.POINT,
                observed_at=base + offset,
                status=LocationStatus.CROWDSOURCED,
                is_own_report=False,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                accuracy=accuracy,
            )
            for latitude, longitude, altitude, accuracy, offset in self._locations.get(
                canonic_id, ()
            )
        ]
