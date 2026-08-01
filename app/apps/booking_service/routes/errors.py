"""Translate safe Booking tenancy errors into stable HTTP details."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from apps.booking_service.services.errors import TenancyError


def raise_tenancy_http(error: TenancyError) -> NoReturn:
    """Raise a sanitized HTTP response for a tenancy service failure.

    Args:
        error: Safe service-layer error containing no credentials or foreign
            resource details.

    Returns:
        NoReturn: This translator always raises ``HTTPException``.

    Raises:
        HTTPException: With the service status and stable structured detail.
    """
    raise HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        },
    ) from error
