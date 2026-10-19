"""User-safe exceptions. None include credentials or response bodies."""

from __future__ import annotations


class UniFiError(Exception):
    """Base error for this package."""


class ConfigurationError(UniFiError):
    """A profile or runtime setting is invalid."""


class CredentialError(UniFiError):
    """An API key is missing or cannot be stored securely."""


class ReadOnlyViolation(UniFiError):
    """A caller attempted an HTTP method that can change the controller."""


class ConnectionFailed(UniFiError):
    """The configured UniFi endpoint could not be reached."""


class AuthenticationFailed(UniFiError):
    """The API key was rejected."""


class PermissionDenied(UniFiError):
    """The API key cannot access the requested resource."""


class ResourceNotFound(UniFiError):
    """The requested endpoint or resource is not available."""


class RateLimited(UniFiError):
    """UniFi asked the client to slow down."""

    def __init__(self, retry_after: str | None = None) -> None:
        message = "UniFi rate limit reached"
        if retry_after:
            message += f"; retry after {retry_after} seconds"
        super().__init__(message)
        self.retry_after = retry_after


class InvalidResponse(UniFiError):
    """UniFi returned malformed or unexpectedly large data."""


class ApiError(UniFiError):
    """UniFi returned an unhandled HTTP error."""

    def __init__(self, status_code: int, operation: str) -> None:
        super().__init__(f"UniFi returned HTTP {status_code} for {operation}")
        self.status_code = status_code
        self.operation = operation
