"""Safe error contract shared by Booking tenancy services and HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenancyError(Exception):
    """Represent a safe tenancy failure without leaking private identifiers.

    Attributes:
        status_code: HTTP-compatible response status.
        code: Stable machine-readable error code.
        message: Sanitized user-facing description.
        retryable: Whether retry after reloading context may succeed.
    """

    status_code: int
    code: str
    message: str
    retryable: bool = False
