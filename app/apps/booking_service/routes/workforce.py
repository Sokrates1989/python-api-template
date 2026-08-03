"""Expose tenant-scoped BKG-202 workforce administration and self-summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.workforce import (
    WorkerProfileCreateRequest,
    WorkerProfileLifecycleRequest,
    WorkerProfileResponse,
    WorkerProfileUpdateRequest,
)
from apps.booking_service.services import BookingWorkforceService, TenancyError


router = APIRouter(tags=["booking-workforce"])


def get_workforce_service() -> BookingWorkforceService:
    """Construct the stateless workforce dependency.

    Returns:
        BookingWorkforceService: Lazily database-backed application service.
    """
    return BookingWorkforceService()


@router.get(
    "/{organization_id}/workers",
    response_model=tuple[WorkerProfileResponse, ...],
)
async def list_worker_profiles(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> tuple[WorkerProfileResponse, ...]:
    """List admin workforce state or the authenticated worker's own summary.

    Args:
        organization_id: Explicit tenant selected by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        tuple[WorkerProfileResponse, ...]: Authorized worker projections.

    Raises:
        HTTPException: With safe authorization or tenant detail.
    """
    try:
        return await service.list_profiles(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/workers",
    response_model=WorkerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_worker_profile(
    organization_id: str,
    request: WorkerProfileCreateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> WorkerProfileResponse:
    """Create a worker profile for one valid tenant membership.

    Args:
        organization_id: Tenant owning the new profile.
        request: Membership, presentation, and assignment configuration.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        WorkerProfileResponse: Newly created worker revision.

    Raises:
        HTTPException: With safe authorization or validation detail.
    """
    try:
        return await service.create_profile(principal, organization_id, request)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.get(
    "/{organization_id}/workers/{worker_profile_id}",
    response_model=WorkerProfileResponse,
)
async def read_worker_profile(
    organization_id: str,
    worker_profile_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> WorkerProfileResponse:
    """Read one worker through administrator or exact self authorization.

    Args:
        organization_id: Tenant owning the worker profile.
        worker_profile_id: Exact profile identifier.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        WorkerProfileResponse: Sanitized visible worker state.

    Raises:
        HTTPException: With safe authorization or hidden-resource detail.
    """
    try:
        return await service.read_profile(
            principal,
            organization_id,
            worker_profile_id,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put(
    "/{organization_id}/workers/{worker_profile_id}",
    response_model=WorkerProfileResponse,
)
async def update_worker_profile(
    organization_id: str,
    worker_profile_id: str,
    request: WorkerProfileUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> WorkerProfileResponse:
    """Replace one worker configuration through optimistic concurrency.

    Args:
        organization_id: Tenant owning the worker profile.
        worker_profile_id: Exact profile identifier.
        request: Complete state and revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        WorkerProfileResponse: Persisted next revision.

    Raises:
        HTTPException: With safe authorization, conflict, or policy detail.
    """
    try:
        return await service.update_profile(
            principal,
            organization_id,
            worker_profile_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.delete(
    "/{organization_id}/workers/{worker_profile_id}",
    response_model=WorkerProfileResponse,
)
async def deactivate_worker_profile(
    organization_id: str,
    worker_profile_id: str,
    expected_revision: int = Query(ge=1),
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> WorkerProfileResponse:
    """Deactivate one worker while retaining configuration and history.

    Args:
        organization_id: Tenant owning the worker profile.
        worker_profile_id: Exact profile identifier.
        expected_revision: Revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        WorkerProfileResponse: Inactive retained worker revision.

    Raises:
        HTTPException: With safe authorization, conflict, or dependency detail.
    """
    try:
        return await service.deactivate_profile(
            principal,
            organization_id,
            worker_profile_id,
            expected_revision,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/workers/{worker_profile_id}/reactivate",
    response_model=WorkerProfileResponse,
)
async def reactivate_worker_profile(
    organization_id: str,
    worker_profile_id: str,
    request: WorkerProfileLifecycleRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingWorkforceService = Depends(get_workforce_service),
) -> WorkerProfileResponse:
    """Reactivate one retained worker after membership revalidation.

    Args:
        organization_id: Tenant owning the worker profile.
        worker_profile_id: Exact profile identifier.
        request: Revision last observed by the caller.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional workforce service.

    Returns:
        WorkerProfileResponse: Active retained worker revision.

    Raises:
        HTTPException: With safe authorization, lifecycle, or validation detail.
    """
    try:
        return await service.reactivate_profile(
            principal,
            organization_id,
            worker_profile_id,
            request,
        )
    except TenancyError as error:
        raise_tenancy_http(error)
