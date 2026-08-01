"""Build the fail-closed Booking Service principal from verified Keycloak claims.

The shared authentication dependency verifies token signature, issuer, time,
and audience before this module reads the configured client-role container.
Only the four app-owned coarse roles are projected; raw claims never leave the
request boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import Depends, HTTPException, status

from api.settings import settings
from api.shared_dependencies.auth import verify_auth_dependency


class BookingRole(StrEnum):
    """Enumerate independent coarse roles accepted by the booking product."""

    PLATFORM_ADMIN = "platform_admin"
    ORGANIZATION_ADMIN = "organization_admin"
    WORKER = "worker"
    CUSTOMER = "customer"


BOOKING_ROLE_ORDER = (
    BookingRole.PLATFORM_ADMIN,
    BookingRole.ORGANIZATION_ADMIN,
    BookingRole.WORKER,
    BookingRole.CUSTOMER,
)
"""Deterministic serialization order for independent coarse booking roles."""


@dataclass(frozen=True)
class BookingPrincipal:
    """Represent one verified subject and its allowlisted coarse roles.

    Attributes:
        subject_id: Immutable, non-empty Keycloak ``sub`` claim.
        roles: Deduplicated roles in :data:`BOOKING_ROLE_ORDER` order.
    """

    subject_id: str
    roles: tuple[BookingRole, ...]


def extract_booking_roles(
    claims: Mapping[str, Any],
    client_id: str,
) -> tuple[BookingRole, ...]:
    """Extract allowlisted roles from one configured Keycloak client.

    Args:
        claims: Claims returned only after shared JWT verification succeeds.
        client_id: Configured Booking API client identifier. An empty value
            grants no role.

    Returns:
        tuple[BookingRole, ...]: Deduplicated roles in deterministic contract
        order. Missing, malformed, realm-only, and unknown roles produce an
        empty or reduced tuple without raising.
    """
    normalized_client_id = client_id.strip()
    resource_access = claims.get("resource_access")
    if not normalized_client_id or not isinstance(resource_access, Mapping):
        return ()

    client_access = resource_access.get(normalized_client_id)
    if not isinstance(client_access, Mapping):
        return ()
    raw_roles = client_access.get("roles")
    if not isinstance(raw_roles, list):
        return ()

    recognized: set[BookingRole] = set()
    for raw_role in raw_roles:
        if not isinstance(raw_role, str):
            continue
        try:
            recognized.add(BookingRole(raw_role))
        except ValueError:
            continue
    return tuple(role for role in BOOKING_ROLE_ORDER if role in recognized)


def get_booking_principal(
    user_info: dict[str, Any] = Depends(verify_auth_dependency),
) -> BookingPrincipal:
    """Build a Booking principal from already verified Keycloak user info.

    Args:
        user_info: Shared authentication result injected after JWT validation.

    Returns:
        BookingPrincipal: Sanitized subject and deterministic coarse roles.

    Raises:
        HTTPException: With status 401 when the selected provider is not
            Keycloak, verified claims are unavailable, ``sub`` is missing, or
            the verified token is not a bearer access token.
    """
    if user_info.get("provider") != "keycloak":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified Booking Service identity is required",
        )

    claims = user_info.get("claims")
    if not isinstance(claims, Mapping):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified Booking Service identity is required",
        )
    raw_subject = claims.get("sub")
    subject_id = raw_subject.strip() if isinstance(raw_subject, str) else ""
    if not subject_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    token_type = claims.get("typ")
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified Booking Service access token is required",
        )

    roles = extract_booking_roles(claims, str(settings.KEYCLOAK_CLIENT_ID or ""))
    return BookingPrincipal(subject_id=subject_id, roles=roles)
