"""Expose audited platform lifecycle and member-scoped organization reads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.context import get_tenancy_service
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.tenancy import (
    OrganizationCreateRequest,
    OrganizationLifecycleRequest,
    OrganizationSummaryResponse,
)
from apps.booking_service.services import BookingTenancyService, TenancyError


platform_router = APIRouter(
    prefix="/v1/platform/organizations",
    tags=["booking-platform-organizations"],
)
organization_router = APIRouter(
    prefix="/v1/organizations",
    tags=["booking-organizations"],
)


@platform_router.get("", response_model=tuple[OrganizationSummaryResponse, ...])
async def list_platform_organizations(
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> tuple[OrganizationSummaryResponse, ...]:
    """List tenants for a coarse plus app-owned platform administrator.

    Args:
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        tuple[OrganizationSummaryResponse, ...]: All tenant summaries.

    Raises:
        HTTPException: With safe 403 detail when either authorization gate is
            inactive.
    """
    try:
        return await service.list_organizations(principal)
    except TenancyError as error:
        raise_tenancy_http(error)


@platform_router.post(
    "",
    response_model=OrganizationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_organization(
    request: OrganizationCreateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> OrganizationSummaryResponse:
    """Create and audit one active organization as a platform administrator.

    Args:
        request: Validated display-name payload.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        OrganizationSummaryResponse: Newly created organization.

    Raises:
        HTTPException: With safe 403 detail when dual authorization fails.
    """
    try:
        return await service.create_organization(principal, request.display_name)
    except TenancyError as error:
        raise_tenancy_http(error)


@platform_router.post(
    "/{organization_id}/suspend",
    response_model=OrganizationSummaryResponse,
)
async def suspend_platform_organization(
    organization_id: str,
    request: OrganizationLifecycleRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> OrganizationSummaryResponse:
    """Suspend one tenant using an optimistic revision and audit event.

    Args:
        organization_id: App-owned tenant identifier.
        request: Expected revision observed by the administrator.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        OrganizationSummaryResponse: Updated suspended organization.

    Raises:
        HTTPException: With safe 403, 404, or retryable 409 detail.
    """
    try:
        return await service.suspend_organization(
            principal, organization_id, request.expected_revision
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@platform_router.post(
    "/{organization_id}/reactivate",
    response_model=OrganizationSummaryResponse,
)
async def reactivate_platform_organization(
    organization_id: str,
    request: OrganizationLifecycleRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> OrganizationSummaryResponse:
    """Reactivate one tenant using an optimistic revision and audit event.

    Args:
        organization_id: App-owned tenant identifier.
        request: Expected revision observed by the administrator.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        OrganizationSummaryResponse: Updated active organization.

    Raises:
        HTTPException: With safe 403, 404, or retryable 409 detail.
    """
    try:
        return await service.reactivate_organization(
            principal, organization_id, request.expected_revision
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@organization_router.get(
    "/{organization_id}",
    response_model=OrganizationSummaryResponse,
)
async def read_member_organization(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingTenancyService = Depends(get_tenancy_service),
) -> OrganizationSummaryResponse:
    """Read one organization through active compatible membership.

    Args:
        organization_id: Explicit tenant context selected by the client.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional tenancy service.

    Returns:
        OrganizationSummaryResponse: Authorized active tenant summary.

    Raises:
        HTTPException: With 404 for absent/foreign tenants or safe 403 for a
            known but inactive scope.
    """
    try:
        return await service.read_member_organization(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)
