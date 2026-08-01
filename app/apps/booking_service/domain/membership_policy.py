"""Pure authorization and lifecycle policy for organization memberships.

The policy keeps privilege and last-administrator decisions independent from
FastAPI, SQLAlchemy, and Keycloak. Service code supplies the persisted actor
scope and active-administrator count, then applies only transitions accepted
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apps.booking_service.domain.tenancy import MembershipRole, MembershipStatus


class MembershipManagementScope(StrEnum):
    """Identify which trusted server-side authority manages a membership."""

    PLATFORM = "platform"
    ORGANIZATION = "organization"


@dataclass(frozen=True)
class MembershipPolicyError(ValueError):
    """Describe a safe rejected membership transition.

    Attributes:
        code: Stable machine-readable rejection code.
        message: Sanitized explanation suitable for an administrative UI.
    """

    code: str
    message: str


_ORGANIZATION_ADMIN_ROLES = frozenset(
    {MembershipRole.WORKER, MembershipRole.CUSTOMER}
)
"""Roles an organization administrator may grant or revoke."""

_TRANSITIONS = {
    MembershipStatus.INVITED: frozenset(
        {MembershipStatus.INVITED, MembershipStatus.REVOKED}
    ),
    MembershipStatus.ACTIVE: frozenset(
        {
            MembershipStatus.ACTIVE,
            MembershipStatus.SUSPENDED,
            MembershipStatus.REVOKED,
        }
    ),
    MembershipStatus.SUSPENDED: frozenset(
        {
            MembershipStatus.ACTIVE,
            MembershipStatus.SUSPENDED,
            MembershipStatus.REVOKED,
        }
    ),
    MembershipStatus.REVOKED: frozenset(
        {MembershipStatus.INVITED, MembershipStatus.REVOKED}
    ),
}
"""Explicit membership lifecycle transitions; provider sync activates invites."""


def validate_membership_roles(
    scope: MembershipManagementScope,
    current_roles: frozenset[MembershipRole],
    target_roles: frozenset[MembershipRole],
) -> None:
    """Reject empty or privilege-escalating role changes.

    Args:
        scope: Server-derived platform or organization management authority.
        current_roles: Roles currently owned by the membership.
        target_roles: Complete desired app-owned role set.

    Returns:
        None: Successful return means the role set is in authority scope.

    Raises:
        MembershipPolicyError: When no role remains or an organization actor
            tries to manage the organization-administrator boundary.
    """
    if not target_roles:
        raise MembershipPolicyError(
            "membership_roles_required",
            "At least one organization role is required.",
        )
    if scope is MembershipManagementScope.ORGANIZATION and (
        MembershipRole.ORGANIZATION_ADMIN in current_roles
        or not target_roles.issubset(_ORGANIZATION_ADMIN_ROLES)
    ):
        raise MembershipPolicyError(
            "membership_role_escalation_denied",
            "Organization administrators may manage worker and customer roles only.",
        )


def validate_membership_transition(
    *,
    scope: MembershipManagementScope,
    current_status: MembershipStatus,
    current_roles: frozenset[MembershipRole],
    target_status: MembershipStatus,
    target_roles: frozenset[MembershipRole],
    active_admin_count: int,
) -> None:
    """Validate one complete role and lifecycle transition.

    Args:
        scope: Server-derived platform or organization authority.
        current_status: Persisted membership lifecycle state.
        current_roles: Persisted roles before the change.
        target_status: Requested lifecycle state.
        target_roles: Complete requested role set.
        active_admin_count: Active administrator memberships in the tenant.

    Returns:
        None: Successful return means the service may persist the transition.

    Raises:
        MembershipPolicyError: For invalid lifecycle transitions, privilege
            escalation, or removal of the final active administrator.
    """
    validate_membership_roles(scope, current_roles, target_roles)
    if target_status not in _TRANSITIONS[current_status]:
        raise MembershipPolicyError(
            "membership_transition_invalid",
            "The requested membership transition is not allowed.",
        )
    removes_active_admin = (
        current_status is MembershipStatus.ACTIVE
        and MembershipRole.ORGANIZATION_ADMIN in current_roles
        and (
            target_status is not MembershipStatus.ACTIVE
            or MembershipRole.ORGANIZATION_ADMIN not in target_roles
        )
    )
    if removes_active_admin and active_admin_count <= 1:
        raise MembershipPolicyError(
            "last_organization_admin_required",
            "At least one active organization administrator must remain.",
        )
