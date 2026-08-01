"""Expose scoped membership commands under the organization API boundary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    get_booking_principal,
)
from apps.booking_service.routes.errors import raise_tenancy_http
from apps.booking_service.schemas.membership import (
    MembershipInvitationRequest,
    MembershipSummaryResponse,
    MembershipUpdateRequest,
)
from apps.booking_service.services import BookingMembershipService, TenancyError


router = APIRouter(tags=["booking-organization-memberships"])


def get_membership_service() -> BookingMembershipService:
    """Construct the stateless membership service dependency.

    Returns:
        BookingMembershipService: Service resolving runtime dependencies only
        when an operation begins.
    """
    return BookingMembershipService()


@router.get(
    "/{organization_id}/memberships",
    response_model=tuple[MembershipSummaryResponse, ...],
)
async def list_organization_memberships(
    organization_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingMembershipService = Depends(get_membership_service),
) -> tuple[MembershipSummaryResponse, ...]:
    """List one tenant's memberships through server-derived admin scope.

    Args:
        organization_id: Explicit tenant being administered.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional membership service.

    Returns:
        tuple[MembershipSummaryResponse, ...]: Sanitized scoped memberships.

    Raises:
        HTTPException: With safe 403 or private-scope 404 detail.
    """
    try:
        return await service.list_memberships(principal, organization_id)
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/memberships",
    response_model=MembershipSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_organization_membership(
    organization_id: str,
    request: MembershipInvitationRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingMembershipService = Depends(get_membership_service),
) -> MembershipSummaryResponse:
    """Create a durable invitation and attempt bounded provider delivery.

    Args:
        organization_id: Explicit tenant that owns the invitation.
        request: Opaque subject and allowlisted initial roles.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional membership service.

    Returns:
        MembershipSummaryResponse: Active or recoverable invited membership.

    Raises:
        HTTPException: With safe authorization, conflict, or validation detail.
    """
    try:
        return await service.invite_membership(
            principal,
            organization_id,
            request.subject_id,
            request.roles,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.put(
    "/{organization_id}/memberships/{membership_id}",
    response_model=MembershipSummaryResponse,
)
async def update_organization_membership(
    organization_id: str,
    membership_id: str,
    request: MembershipUpdateRequest,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingMembershipService = Depends(get_membership_service),
) -> MembershipSummaryResponse:
    """Replace roles and lifecycle state using optimistic concurrency.

    Args:
        organization_id: Tenant that must own the membership.
        membership_id: App-owned membership identifier.
        request: Complete target state and observed revision.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional membership service.

    Returns:
        MembershipSummaryResponse: Updated membership and provider recovery.

    Raises:
        HTTPException: With safe scope, policy, or revision detail.
    """
    try:
        return await service.update_membership(
            principal,
            organization_id,
            membership_id,
            request.expected_revision,
            request.status,
            request.roles,
        )
    except TenancyError as error:
        raise_tenancy_http(error)


@router.post(
    "/{organization_id}/memberships/{membership_id}/retry-identity-sync",
    response_model=MembershipSummaryResponse,
)
async def retry_membership_identity_sync(
    organization_id: str,
    membership_id: str,
    principal: BookingPrincipal = Depends(get_booking_principal),
    service: BookingMembershipService = Depends(get_membership_service),
) -> MembershipSummaryResponse:
    """Retry the newest recoverable identity-role outbox item.

    Args:
        organization_id: Tenant that must own the membership.
        membership_id: Membership with recoverable provider work.
        principal: Verified request-scoped Booking principal.
        service: Injected transactional membership service.

    Returns:
        MembershipSummaryResponse: Membership after the new provider attempt.

    Raises:
        HTTPException: With safe scope or non-retryable conflict detail.
    """
    try:
        return await service.retry_identity_sync(
            principal, organization_id, membership_id
        )
    except TenancyError as error:
        raise_tenancy_http(error)
