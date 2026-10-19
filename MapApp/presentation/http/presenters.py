"""JSON-safe presenters that never expose backend-only identifiers."""

from __future__ import annotations

from MapApp.application.dto import DeviceSummary, LocationPoint, PublicLocation, SemanticLocation, SyncStatus
from MapApp.application.jobs import JobSnapshot


def location_json(location: PublicLocation) -> dict[str, object]:
    payload = location.to_dict()
    payload["kind"] = "point" if isinstance(location, LocationPoint) else "semantic"
    return payload


def device_json(device: DeviceSummary) -> dict[str, object]:
    payload = device.to_dict()
    if device.latest_location is not None:
        payload["latest_location"] = location_json(device.latest_location)
    return payload


def job_json(snapshot: JobSnapshot) -> dict[str, object]:
    run = snapshot.run
    status = SyncStatus(
        job_id=run.id,
        operation=run.operation.value,
        status=run.status.value,
        progress=snapshot.progress,
        safe_error=run.error_message,
    ).to_dict()
    status.update(
        {
            "completed": snapshot.completed,
            "total": snapshot.total,
            "cancellation_requested": snapshot.cancellation_requested,
            "counts": {
                "devices": run.devices_discovered,
                "reports_received": run.reports_received,
                "reports_inserted": run.reports_inserted,
                "reports_duplicated": run.reports_duplicated,
            },
        }
    )
    return status


def map_geojson(devices: list[DeviceSummary]) -> dict[str, object]:
    features = []
    for device in devices:
        location = device.latest_location
        if not isinstance(location, LocationPoint):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [location.longitude, location.latitude],
                },
                "properties": {
                    "device_public_id": device.public_id,
                    "name": device.name,
                    "observed_at": location.observed_at,
                    "accuracy": location.accuracy,
                    "status": location.status,
                    "own_report": location.own_report,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
