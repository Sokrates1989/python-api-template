"""Expose authenticated Booking Service user preference endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.preferences import (
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from apps.booking_service.services import BookingPreferencesService, TenancyError


router = APIRouter(tags=["booking-user-preferences"])


def get_preferences_service() -> BookingPreferencesService:
    """Construct the stateless user-preference service dependency.

    Returns:
        Service resolving the runtime database only when an operation begins.
    """

    return BookingPreferencesService()


@router.get("/preferences", response_model=UserPreferencesResponse)
async def read_user_preferences(
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingPreferencesService = Depends(get_preferences_service),
) -> UserPreferencesResponse:
    """Read preferences for the active verified account.

    Args:
        principal: Verified request-scoped Booking principal.
        service: Injected transactional preference service.

    Returns:
        Current locale and optimistic revision for this account only.

    Raises:
        HTTPException: With safe 401 or inactive-account 403 semantics.
    """

    try:
        return await service.read_preferences(principal)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_user_preferences(
    request: UserPreferencesUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingPreferencesService = Depends(get_preferences_service),
) -> UserPreferencesResponse:
    """Replace preferences for the active verified account.

    Args:
        request: Complete validated preference replacement.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional preference service.

    Returns:
        Updated locale and optimistic revision for this account only.

    Raises:
        HTTPException: With safe 401, 403, or retryable 409 semantics.
    """

    try:
        return await service.update_preferences(principal, request)
    except TenancyError as error:
        raise_tenancy_http(error)
