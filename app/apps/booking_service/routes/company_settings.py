"""Expose tenant-scoped company settings and location lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.company_settings import (
    CompanySettingsResponse,
    CompanySettingsUpdateRequest,
    LocationCreateRequest,
    LocationLifecycleRequest,
    LocationResponse,
    LocationUpdateRequest,
)
from apps.booking_service.services import BookingCompanySettingsService, TenancyError


router = APIRouter(tags=["booking-company-settings"])


def get_company_settings_service() -> BookingCompanySettingsService:
    """Construct the stateless company-settings service dependency.

    Returns:
        BookingCompanySettingsService: Service resolving the runtime database
        only when an operation begins.
    """
    return BookingCompanySettingsService()


@router.get(
    "/{organization_id}/company-settings",
    response_model=CompanySettingsResponse,
)
async def read_company_settings(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> CompanySettingsResponse:
    """Read company settings through an active organization membership.

    Args:
        organization_id: Explicit tenant selected by the client.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        CompanySettingsResponse: Sanitized profile, policy, and active locations.

    Raises:
        HTTPException: With safe 403, 404, or recoverable 409 detail.
    """
    try:
        return await service.read_company_settings(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put(
    "/{organization_id}/company-settings",
    response_model=CompanySettingsResponse,
)
async def update_company_settings(
    organization_id: str,
    request: CompanySettingsUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> CompanySettingsResponse:
    """Replace one tenant profile and policy as an organization administrator.

    Args:
        organization_id: Explicit tenant being mutated.
        request: Complete validated replacement and observed revision.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        CompanySettingsResponse: Updated profile, policy, and active locations.

    Raises:
        HTTPException: With safe authorization, scope, or revision detail.
    """
    try:
        return await service.update_company_settings(principal, organization_id, request)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    organization_id: str,
    request: LocationCreateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> LocationResponse:
    """Create one active location as an organization administrator.

    Args:
        organization_id: Explicit tenant owning the location.
        request: Validated complete location fields.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        LocationResponse: Newly created active location.

    Raises:
        HTTPException: With safe authorization or scope detail.
    """
    try:
        return await service.create_location(principal, organization_id, request)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put(
    "/{organization_id}/locations/{location_id}",
    response_model=LocationResponse,
)
async def update_location(
    organization_id: str,
    location_id: str,
    request: LocationUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> LocationResponse:
    """Replace one active location through tenant-bound revision checks.

    Args:
        organization_id: Explicit tenant owning the location.
        location_id: Exact location identifier inside the tenant.
        request: Complete replacement and revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        LocationResponse: Updated active location.

    Raises:
        HTTPException: With safe authorization, scope, lifecycle, or conflict detail.
    """
    try:
        return await service.update_location(
            principal,
            organization_id,
            location_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.delete(
    "/{organization_id}/locations/{location_id}",
    response_model=LocationResponse,
)
async def archive_location(
    organization_id: str,
    location_id: str,
    expected_revision: int = Query(ge=1),
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> LocationResponse:
    """Archive a non-final location without physically deleting references.

    Args:
        organization_id: Explicit tenant owning the location.
        location_id: Exact location identifier inside the tenant.
        expected_revision: Location revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        LocationResponse: Archived retained location.

    Raises:
        HTTPException: With safe authorization, conflict, or last-location detail.
    """
    try:
        return await service.archive_location(
            principal,
            organization_id,
            location_id,
            expected_revision,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/locations/{location_id}/reactivate",
    response_model=LocationResponse,
)
async def reactivate_location(
    organization_id: str,
    location_id: str,
    request: LocationLifecycleRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingCompanySettingsService = Depends(get_company_settings_service),
) -> LocationResponse:
    """Reactivate an archived location as an organization administrator.

    Args:
        organization_id: Explicit tenant owning the location.
        location_id: Exact location identifier inside the tenant.
        request: Revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional company-settings service.

    Returns:
        LocationResponse: Reactivated location.

    Raises:
        HTTPException: With safe authorization, lifecycle, or conflict detail.
    """
    try:
        return await service.reactivate_location(
            principal,
            organization_id,
            location_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)
