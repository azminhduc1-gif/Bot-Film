"""Exceptions raised by the KKPhim API client."""
from __future__ import annotations


class KKPhimError(Exception):
    """Base exception for KKPhim provider errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class KKPhimAPIError(KKPhimError):
    """Non-2xx HTTP response from KKPhim."""


class KKPhimTimeoutError(KKPhimError):
    """Request to KKPhim timed out."""


class KKPhimValidationError(KKPhimError):
    """Response could not be validated against Pydantic models."""


class KKPhimNotFoundError(KKPhimError):
    """Requested movie/resource not found."""
