"""Expose authenticated published discovery and customer-equivalent preview."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.booking_service.dependencies.identity import BookingPrincipal, get_booking_principal
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.discovery import DiscoveryOrganizationResponse
from apps.booking_service.services.discovery_service import BookingDiscoveryService
from apps.booking_service.services.errors import TenancyError


discovery_router = APIRouter(prefix="/v1/discovery", tags=["booking-discovery"])
preview_router = APIRouter(tags=["booking-discovery-preview"])


def get_discovery_service() -> BookingDiscoveryService:
    """Construct the stateless published-catalog dependency.

    Returns:
        BookingDiscoveryService: Lazily database-backed discovery service.
    """
    return BookingDiscoveryService()


@discovery_router.get(
    "/organizations",
    response_model=tuple[DiscoveryOrganizationResponse, ...],
)
async def list_discovery_organizations(
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingDiscoveryService = Depends(get_discovery_service),
) -> tuple[DiscoveryOrganizationResponse, ...]:
    """List published catalogs for any verified active Booking subject.

    Args:
        principal: Verified request identity; membership is not required.
        service: Injected transactional discovery service.

    Returns:
        tuple[DiscoveryOrganizationResponse, ...]: Sanitized published catalogs.

    Raises:
        HTTPException: With safe authentication or subject-lifecycle detail.
    """
    try:
        return await service.list_catalogs(principal)
    except TenancyError as error:
        raise_tenancy_http(error)


@discovery_router.get(
    "/organizations/{organization_id}",
    response_model=DiscoveryOrganizationResponse,
)
async def read_discovery_organization(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingDiscoveryService = Depends(get_discovery_service),
) -> DiscoveryOrganizationResponse:
    """Read one published catalog without requiring tenant membership.

    Args:
        organization_id: Exact organization selected from discovery.
        principal: Verified request identity.
        service: Injected transactional discovery service.

    Returns:
        DiscoveryOrganizationResponse: Sanitized non-empty published catalog.

    Raises:
        HTTPException: With safe authentication, lifecycle, or 404 detail.
    """
    try:
        return await service.read_catalog(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)


@preview_router.get(
    "/{organization_id}/discovery-preview",
    response_model=DiscoveryOrganizationResponse,
)
async def preview_discovery_organization(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingDiscoveryService = Depends(get_discovery_service),
) -> DiscoveryOrganizationResponse:
    """Show an administrator the exact customer-visible catalog projection.

    Args:
        organization_id: Explicit tenant being previewed.
        principal: Verified request identity.
        service: Injected transactional discovery service.

    Returns:
        DiscoveryOrganizationResponse: Published-only customer projection.

    Raises:
        HTTPException: With safe tenant-administrator authorization detail.
    """
    try:
        return await service.preview_catalog(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)
