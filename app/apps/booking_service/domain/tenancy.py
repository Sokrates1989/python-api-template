"""Pure organization-tenancy policy for the Booking Service.

This module intentionally has no database or web-framework dependency. It
defines stable wire values and the fail-closed intersection between Keycloak
coarse roles and app-owned organization membership roles.
"""

from __future__ import annotations

from enum import StrEnum

from apps.booking_service.dependencies.identity import BookingRole


class SubjectStatus(StrEnum):
    """Enumerate lifecycle states for an app-owned identity subject."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETION_PENDING = "deletion_pending"


class OrganizationStatus(StrEnum):
    """Enumerate lifecycle states for a tenant organization."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipStatus(StrEnum):
    """Enumerate lifecycle states for an organization membership."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class PlatformAccessStatus(StrEnum):
    """Enumerate lifecycle states for app-owned platform access."""

    ACTIVE = "active"
    REVOKED = "revoked"


class MembershipRole(StrEnum):
    """Enumerate roles that can be owned by one organization membership."""

    ORGANIZATION_ADMIN = "organization_admin"
    WORKER = "worker"
    CUSTOMER = "customer"


class BookingCapability(StrEnum):
    """Enumerate server-derived capabilities exposed to Booking clients."""

    MANAGE_PLATFORM_ORGANIZATIONS = "manage_platform_organizations"
    READ_ORGANIZATION = "read_organization"
    MANAGE_ORGANIZATION = "manage_organization"
    MANAGE_OWN_WORKER_SCHEDULE = "manage_own_worker_schedule"
    MANAGE_OWN_BOOKINGS = "manage_own_bookings"


MEMBERSHIP_ROLE_ORDER = (
    MembershipRole.ORGANIZATION_ADMIN,
    MembershipRole.WORKER,
    MembershipRole.CUSTOMER,
)
"""Deterministic serialization order for organization membership roles."""

BOOKING_CAPABILITY_ORDER = (
    BookingCapability.MANAGE_PLATFORM_ORGANIZATIONS,
    BookingCapability.READ_ORGANIZATION,
    BookingCapability.MANAGE_ORGANIZATION,
    BookingCapability.MANAGE_OWN_WORKER_SCHEDULE,
    BookingCapability.MANAGE_OWN_BOOKINGS,
)
"""Deterministic serialization order for effective capabilities."""

_ROLE_CAPABILITIES = {
    MembershipRole.ORGANIZATION_ADMIN: (
        BookingCapability.READ_ORGANIZATION,
        BookingCapability.MANAGE_ORGANIZATION,
    ),
    MembershipRole.WORKER: (
        BookingCapability.READ_ORGANIZATION,
        BookingCapability.MANAGE_OWN_WORKER_SCHEDULE,
    ),
    MembershipRole.CUSTOMER: (
        BookingCapability.READ_ORGANIZATION,
        BookingCapability.MANAGE_OWN_BOOKINGS,
    ),
}
"""Map each app-owned membership role to its current BKG-101 capabilities."""


def compatible_membership_roles(
    coarse_roles: tuple[BookingRole, ...],
    membership_roles: set[MembershipRole],
) -> tuple[MembershipRole, ...]:
    """Intersect app membership roles with verified Keycloak coarse roles.

    Args:
        coarse_roles: Verified request-scoped Keycloak client roles.
        membership_roles: Roles stored for one organization membership.

    Returns:
        tuple[MembershipRole, ...]: Compatible roles in stable order. Unknown
        or mismatched roles grant nothing.
    """
    coarse_values = {role.value for role in coarse_roles}
    return tuple(
        role
        for role in MEMBERSHIP_ROLE_ORDER
        if role in membership_roles and role.value in coarse_values
    )


def capabilities_for_membership_roles(
    roles: tuple[MembershipRole, ...],
) -> tuple[BookingCapability, ...]:
    """Derive deterministic organization capabilities from effective roles.

    Args:
        roles: Membership roles already intersected with coarse roles.

    Returns:
        tuple[BookingCapability, ...]: Deduplicated capabilities in stable
        order. An empty role tuple yields an empty capability tuple.
    """
    granted = {
        capability
        for role in roles
        for capability in _ROLE_CAPABILITIES.get(role, ())
    }
    return tuple(
        capability for capability in BOOKING_CAPABILITY_ORDER if capability in granted
    )
