"""Expose tenant-scoped timed service catalog endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.service_catalog import (
    ServiceOfferingCreateRequest,
    ServiceOfferingLifecycleRequest,
    ServiceOfferingResponse,
    ServiceOfferingUpdateRequest,
)
from apps.booking_service.services import BookingServiceCatalogService, TenancyError


router = APIRouter(tags=["booking-service-catalog"])


def get_service_catalog_service() -> BookingServiceCatalogService:
    """Construct the stateless service-catalog dependency.

    Returns:
        BookingServiceCatalogService: Lazily database-backed application service.
    """
    return BookingServiceCatalogService()


@router.get(
    "/{organization_id}/services",
    response_model=tuple[ServiceOfferingResponse, ...],
)
async def list_service_offerings(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> tuple[ServiceOfferingResponse, ...]:
    """List role-filtered service offerings for one active tenant.

    Args:
        organization_id: Explicit tenant selected by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        tuple[ServiceOfferingResponse, ...]: Admin-complete or published rows.

    Raises:
        HTTPException: With safe authorization or scope detail.
    """
    try:
        return await service.list_offerings(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/services",
    response_model=ServiceOfferingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_offering(
    organization_id: str,
    request: ServiceOfferingCreateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> ServiceOfferingResponse:
    """Create one timed service as an organization administrator.

    Args:
        organization_id: Tenant owning the new service.
        request: Validated service fields and explicit locations.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        ServiceOfferingResponse: Newly created first revision.

    Raises:
        HTTPException: With safe authorization or validation detail.
    """
    try:
        return await service.create_offering(principal, organization_id, request)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.get(
    "/{organization_id}/services/{service_offering_id}",
    response_model=ServiceOfferingResponse,
)
async def read_service_offering(
    organization_id: str,
    service_offering_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> ServiceOfferingResponse:
    """Read one visible tenant-owned service revision.

    Args:
        organization_id: Explicit tenant selected by the caller.
        service_offering_id: Exact service identifier inside the tenant.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        ServiceOfferingResponse: Sanitized role-visible service.

    Raises:
        HTTPException: With safe scope or hidden-resource detail.
    """
    try:
        return await service.read_offering(
            principal,
            organization_id,
            service_offering_id,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put(
    "/{organization_id}/services/{service_offering_id}",
    response_model=ServiceOfferingResponse,
)
async def update_service_offering(
    organization_id: str,
    service_offering_id: str,
    request: ServiceOfferingUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> ServiceOfferingResponse:
    """Replace one active service through optimistic concurrency.

    Args:
        organization_id: Tenant owning the service.
        service_offering_id: Exact service being replaced.
        request: Complete replacement and observed revision.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        ServiceOfferingResponse: Persisted next revision.

    Raises:
        HTTPException: With safe authorization, lifecycle, or conflict detail.
    """
    try:
        return await service.update_offering(
            principal,
            organization_id,
            service_offering_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.delete(
    "/{organization_id}/services/{service_offering_id}",
    response_model=ServiceOfferingResponse,
)
async def archive_service_offering(
    organization_id: str,
    service_offering_id: str,
    expected_revision: int = Query(ge=1),
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> ServiceOfferingResponse:
    """Archive and unpublish one service without deleting history.

    Args:
        organization_id: Tenant owning the service.
        service_offering_id: Exact service being archived.
        expected_revision: Revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        ServiceOfferingResponse: Archived retained revision.

    Raises:
        HTTPException: With safe authorization, lifecycle, or conflict detail.
    """
    try:
        return await service.archive_offering(
            principal,
            organization_id,
            service_offering_id,
            expected_revision,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/services/{service_offering_id}/reactivate",
    response_model=ServiceOfferingResponse,
)
async def reactivate_service_offering(
    organization_id: str,
    service_offering_id: str,
    request: ServiceOfferingLifecycleRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingServiceCatalogService = Depends(get_service_catalog_service),
) -> ServiceOfferingResponse:
    """Reactivate one service in an unpublished safe state.

    Args:
        organization_id: Tenant owning the service.
        service_offering_id: Exact service being reactivated.
        request: Revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional catalog service.

    Returns:
        ServiceOfferingResponse: Active unpublished next revision.

    Raises:
        HTTPException: With safe authorization, location, or conflict detail.
    """
    try:
        return await service.reactivate_offering(
            principal,
            organization_id,
            service_offering_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)
