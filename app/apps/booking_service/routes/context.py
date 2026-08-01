"""Expose the authenticated Booking Service effective tenancy context."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.tenancy import EffectiveContextResponse
from apps.booking_service.services import BookingTenancyService, TenancyError


router = APIRouter(tags=["booking-context"])


def get_tenancy_service() -> BookingTenancyService:
    """Construct the stateless tenancy service for FastAPI dependency use.

    Returns:
        BookingTenancyService: Service resolving the initialized database
        handler only when an operation begins.
    """
    return BookingTenancyService()


@router.get("/context", response_model=EffectiveContextResponse)
async def read_effective_context(
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> EffectiveContextResponse:
    """Return active app-owned context after coarse-role intersection.

    Args:
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        EffectiveContextResponse: Effective platform and organization context.

    Raises:
        HTTPException: With safe 403 detail when app-owned subject access is
            inactive; authentication failures remain 401.
    """
    try:
        return await service.effective_context(principal)
    except TenancyError as error:
        raise_tenancy_http(error)
