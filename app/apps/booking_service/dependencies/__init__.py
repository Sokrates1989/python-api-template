"""Booking Service request dependencies.

The package keeps product-specific identity and authorization policy inside the
selected backend app rather than moving role names into shared infrastructure.
"""

from apps.booking_service.dependencies.identity import (
    BOOKING_ROLE_ORDER,
    BookingPrincipal,
    BookingRole,
    extract_booking_roles,
    get_booking_principal,
)

__all__ = [
    "BOOKING_ROLE_ORDER",
    "BookingPrincipal",
    "BookingRole",
    "extract_booking_roles",
    "get_booking_principal",
]
