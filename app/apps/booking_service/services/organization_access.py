"""Reusable same-tenant authorization boundary for Booking domain services.

Keycloak client roles remain coarse input. Access is granted only when the
verified role intersects an active app-owned membership in the explicit active
organization supplied by the request path.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.tenancy import (
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    SubjectStatus,
    compatible_membership_roles,
)
from apps.booking_service.models.tenancy import BookingOrganization
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.services.errors import TenancyError


@dataclass(frozen=True)
class ActiveOrganizationAccess:
    """Carry server-derived active organization access for one request.

    Attributes:
        organization: Authorized active tenant row.
        membership_id: Active app-owned membership identifier.
        roles: Roles surviving Keycloak/app-owned intersection.
    """

    organization: BookingOrganization
    membership_id: str
    roles: tuple[MembershipRole, ...]


async def require_active_organization_access(
    session: AsyncSession,
    principal: BookingPrincipal,
    organization_id: str,
) -> ActiveOrganizationAccess:
    """Require one active compatible membership in an explicit tenant.

    Args:
        session: Current transaction session.
        principal: Verified request-scoped identity and coarse roles.
        organization_id: Explicit tenant requested by the caller.

    Returns:
        ActiveOrganizationAccess: Active tenant, membership, and effective roles.

    Raises:
        TenancyError: With safe 404 for absent/foreign scope or 403 for inactive
            subject, organization, membership, or incompatible roles.
    """
    repository = TenancyRepository(session)
    subject = await repository.ensure_subject(principal.subject_id)
    if subject.status != SubjectStatus.ACTIVE.value:
        raise TenancyError(403, "subject_inactive", "Booking access is not active")
    membership = await repository.get_membership(organization_id, principal.subject_id)
    if membership is None:
        raise _organization_not_found()
    organization = await repository.get_organization(organization_id)
    if organization is None:
        raise _organization_not_found()
    _require_active_lifecycle(organization.status, membership.status)
    stored_roles = await repository.get_membership_roles(organization_id, membership.id)
    roles = compatible_membership_roles(principal.roles, stored_roles)
    if not roles:
        raise TenancyError(403, "organization_access_denied", "Organization access is not active")
    return ActiveOrganizationAccess(organization, membership.id, roles)


async def require_organization_administrator(
    session: AsyncSession,
    principal: BookingPrincipal,
    organization_id: str,
) -> ActiveOrganizationAccess:
    """Require active same-tenant organization-administrator authority.

    Args:
        session: Current transaction session.
        principal: Verified request-scoped identity and coarse roles.
        organization_id: Explicit tenant being mutated.

    Returns:
        ActiveOrganizationAccess: Authorized tenant management scope.

    Raises:
        TenancyError: When same-tenant active access or administrator role is
            absent. Platform role alone deliberately grants no tenant mutation.
    """
    access = await require_active_organization_access(
        session,
        principal,
        organization_id,
    )
    if MembershipRole.ORGANIZATION_ADMIN not in access.roles:
        raise TenancyError(
            403,
            "organization_management_denied",
            "Organization management is not allowed",
        )
    return access


def _require_active_lifecycle(
    organization_status: str,
    membership_status: str,
) -> None:
    """Reject known organization context with an inactive lifecycle gate.

    Args:
        organization_status: Persisted organization lifecycle value.
        membership_status: Persisted membership lifecycle value.

    Returns:
        None: Successful return means both gates are active.

    Raises:
        TenancyError: With safe 403 semantics for either inactive gate.
    """
    if organization_status != OrganizationStatus.ACTIVE.value:
        raise TenancyError(403, "organization_suspended", "Organization access is not active")
    if membership_status != MembershipStatus.ACTIVE.value:
        raise TenancyError(403, "membership_inactive", "Organization access is not active")


def _organization_not_found() -> TenancyError:
    """Build a uniform private-resource response hiding tenant existence.

    Returns:
        TenancyError: Safe organization not-found error.
    """
    return TenancyError(404, "organization_not_found", "Organization was not found")
