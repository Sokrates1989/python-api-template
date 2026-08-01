"""Privacy-minimized audit helpers for Booking membership commands."""

from __future__ import annotations

from apps.booking_service.domain.tenancy import MembershipRole
from apps.booking_service.models.tenancy import OrganizationMembership
from apps.booking_service.repositories import TenancyRepository


def membership_audit_state(
    status: str,
    roles: frozenset[MembershipRole],
    revision: int,
) -> dict[str, object]:
    """Build one sanitized membership audit snapshot.

    Args:
        status: App-owned membership lifecycle state.
        roles: Complete app-owned role set.
        revision: Monotonic membership revision.

    Returns:
        dict[str, object]: Status, ordered roles, and revision only.
    """
    return {
        "status": status,
        "roles": sorted(role.value for role in roles),
        "revision": revision,
    }


async def record_membership_command(
    repository: TenancyRepository,
    actor_subject_id: str,
    membership: OrganizationMembership,
    before_state: dict[str, object] | None,
    after_state: dict[str, object],
) -> None:
    """Write one sanitized membership command audit event.

    Args:
        repository: Transaction-bound audit repository.
        actor_subject_id: Verified actor subject used for attribution.
        membership: Mutated membership aggregate.
        before_state: Sanitized previous state or ``None`` for an invitation.
        after_state: Sanitized complete state after the command.

    Returns:
        None: The audit event remains staged in the current transaction.
    """
    if before_state is None:
        action = "membership.invited"
    elif before_state["status"] != after_state["status"]:
        action = f"membership.{after_state['status']}"
    else:
        action = "membership.roles_replaced"
    await repository.add_audit_event(
        actor_subject_id=actor_subject_id,
        organization_id=membership.organization_id,
        action=action,
        resource_type="membership",
        resource_id=membership.id,
        before_state=before_state,
        after_state=after_state,
    )
