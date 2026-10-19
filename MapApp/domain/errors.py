"""Typed failures with messages safe to expose outside the backend."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base failure carrying only a stable code and a sanitized message."""

    default_code = "application_error"
    default_message = "The operation could not be completed."
    default_retryable = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.safe_message = message or self.default_message
        self.retryable = self.default_retryable if retryable is None else retryable
        super().__init__(self.safe_message)


class DomainValidationError(ApplicationError, ValueError):
    default_code = "invalid_domain_value"
    default_message = "A domain value is invalid."

    def __init__(self, field: str, message: str | None = None) -> None:
        self.field = field
        super().__init__(message or f"Invalid value for {field}.")


class AuthenticationRequired(ApplicationError):
    default_code = "authentication_required"
    default_message = "Interactive authentication is required."


class AuthenticationExpired(ApplicationError):
    default_code = "authentication_expired"
    default_message = "The authentication session has expired."


class GoogleUnavailable(ApplicationError):
    default_code = "google_unavailable"
    default_message = "The location service is temporarily unavailable."
    default_retryable = True


class RateLimited(ApplicationError):
    default_code = "rate_limited"
    default_message = "Too many requests. Try again later."
    default_retryable = True


class LocationTimeout(ApplicationError):
    default_code = "location_timeout"
    default_message = "The location request timed out."
    default_retryable = True


class MalformedGoogleResponse(ApplicationError):
    default_code = "malformed_google_response"
    default_message = "The location service returned an invalid response."


class KeyUnavailable(ApplicationError):
    default_code = "key_unavailable"
    default_message = "The device key is unavailable."


class DecryptionFailed(ApplicationError):
    default_code = "decryption_failed"
    default_message = "The location report could not be decoded."


class PersistenceFailed(ApplicationError):
    default_code = "persistence_failed"
    default_message = "The local data could not be saved."
    default_retryable = True


class NotFoundError(ApplicationError):
    default_code = "not_found"
    default_message = "The requested resource was not found."
