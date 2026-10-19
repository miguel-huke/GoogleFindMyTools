import datetime
from typing import Protocol


class ReportsProvider(Protocol):
    def list_devices(self): ...

    def locate(self, canonic_id, name): ...


class GoogleFindMyToolsProvider:
    """Loads the original network stack only after an explicit API request."""

    def list_devices(self):
        from NovaApi.ListDevices.nbe_list_devices import get_devices

        return get_devices()

    def locate(self, canonic_id, name):
        from NovaApi.ExecuteAction.LocateTracker.location_request import (
            get_location_data_for_device,
        )

        return get_location_data_for_device(canonic_id, name)


class DemoReportsProvider:
    """Deterministic, synthetic reports for local and visual validation."""

    _devices = (
        ("Chaves (demo)", "demo-keys"),
        ("Mochila (demo)", "demo-bag"),
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

    def list_devices(self):
        return list(self._devices)

    def locate(self, canonic_id, name):
        base = int(
            datetime.datetime(
                2026, 10, 19, 15, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
        )
        reports = []
        for latitude, longitude, altitude, accuracy, offset in self._locations.get(
            canonic_id, ()
        ):
            reports.append(
                {
                    "kind": "point",
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude,
                    "accuracy": accuracy,
                    "timestamp": base + offset,
                    "status": "CROWDSOURCED",
                    "is_own_report": False,
                }
            )
        return reports
