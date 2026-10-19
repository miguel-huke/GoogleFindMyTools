"""Validation and deterministic identity rules shared by domain models."""

from __future__ import annotations

import hashlib
import json
import math

from .errors import DomainValidationError


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(field)
    return value.strip()


def optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return require_text(value, field)


def require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainValidationError(field)
    return value


def optional_non_negative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return require_non_negative_int(value, field)


def optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainValidationError(field)
    return value


def require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise DomainValidationError(field)
    return value


def finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainValidationError(field)
    normalized = float(value)
    if not math.isfinite(normalized):
        raise DomainValidationError(field)
    return normalized


def optional_finite_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    return finite_number(value, field)


def latitude(value: object) -> float:
    normalized = finite_number(value, "latitude")
    if not -90.0 <= normalized <= 90.0:
        raise DomainValidationError("latitude")
    return normalized


def longitude(value: object) -> float:
    normalized = finite_number(value, "longitude")
    if not -180.0 <= normalized <= 180.0:
        raise DomainValidationError("longitude")
    return normalized


def optional_accuracy(value: object) -> float | None:
    if value is None:
        return None
    normalized = finite_number(value, "accuracy")
    if normalized < 0:
        raise DomainValidationError("accuracy")
    return normalized


def build_location_dedup_key(
    *,
    beacon_public_id: str,
    kind: str,
    observed_at: int,
    latitude_value: float | None,
    longitude_value: float | None,
    status: str,
    is_own_report: bool,
) -> str:
    """Hash only the sanitized fields specified by the architecture blueprint."""

    payload = [
        require_text(beacon_public_id, "beacon_public_id"),
        require_text(kind, "kind"),
        require_non_negative_int(observed_at, "observed_at"),
        optional_finite_number(latitude_value, "latitude"),
        optional_finite_number(longitude_value, "longitude"),
        require_text(status, "status"),
        require_bool(is_own_report, "is_own_report"),
    ]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
