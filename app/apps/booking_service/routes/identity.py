"""Expose the authenticated Booking Service coarse identity projection."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.schemas.identity import EffectiveIdentityResponse


router = APIRouter(prefix="/v1/me", tags=["booking-identity"])


@router.get("/identity", response_model=EffectiveIdentityResponse)
def read_effective_identity(
    principal: BookingPrincipal = Depends(get_booking_principal),
) -> EffectiveIdentityResponse:
    """Return one sanitized identity after fail-closed JWT verification.

    Args:
        principal: Verified request-scoped Booking principal.

    Returns:
        EffectiveIdentityResponse: Stable subject and allowlisted coarse roles.

    Raises:
        HTTPException: Propagated as 401 by authentication or principal
            construction when the bearer token cannot establish identity.
    """
    return EffectiveIdentityResponse(
        subject_id=principal.subject_id,
        roles=principal.roles,
    )
