"""Contract tests for BKG-101 tenancy policy, routes, and safe failures."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.dependencies.identity import BookingPrincipal, BookingRole
from apps.booking_service.domain.tenancy import (
    BookingCapability,
    MembershipRole,
    capabilities_for_membership_roles,
    compatible_membership_roles,
)
from apps.booking_service.routes.context import read_effective_context
from apps.booking_service.schemas.tenancy import (
    EffectiveContextResponse,
    OrganizationCreateRequest,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.tenancy_service import BookingTenancyService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for migration source contract checks."""


class _ContextServiceStub:
    """Provide a deterministic async effective-context route dependency."""

    def __init__(self, response: EffectiveContextResponse | TenancyError) -> None:
        """Retain one response or safe error for a route test.

        Args:
            response: Effective context to return or tenancy error to raise.

        Returns:
            None: The fixture retains the supplied result.
        """
        self._response = response

    async def effective_context(
        self,
        principal: BookingPrincipal,
    ) -> EffectiveContextResponse:
        """Return the fixture response or raise its safe tenancy error.

        Args:
            principal: Verified principal accepted to mirror the real service.

        Returns:
            EffectiveContextResponse: Configured successful response.

        Raises:
            TenancyError: Configured safe service failure.
        """
        del principal
        if isinstance(self._response, TenancyError):
            raise self._response
        return self._response


class BookingTenancyPolicyTests(unittest.TestCase):
    """Prove role intersection, capability derivation, and schema contracts."""

    def test_membership_roles_require_matching_coarse_roles(self) -> None:
        """Ignore app-owned roles absent from verified Keycloak coarse roles."""
        roles = compatible_membership_roles(
            (BookingRole.WORKER, BookingRole.CUSTOMER),
            {
                MembershipRole.ORGANIZATION_ADMIN,
                MembershipRole.WORKER,
                MembershipRole.CUSTOMER,
            },
        )
        self.assertEqual(
            roles,
            (MembershipRole.WORKER, MembershipRole.CUSTOMER),
        )

    def test_capabilities_are_deduplicated_and_deterministic(self) -> None:
        """Derive shared reads once while retaining role-specific capabilities."""
        capabilities = capabilities_for_membership_roles(
            (MembershipRole.WORKER, MembershipRole.CUSTOMER)
        )
        self.assertEqual(
            capabilities,
            (
                BookingCapability.READ_ORGANIZATION,
                BookingCapability.MANAGE_OWN_WORKER_SCHEDULE,
                BookingCapability.MANAGE_OWN_BOOKINGS,
            ),
        )

    def test_every_persona_receives_only_compatible_capabilities(self) -> None:
        """Cover the complete BKG-102 coarse-role and membership matrix."""
        cases = (
            (
                "platform-without-membership",
                (BookingRole.PLATFORM_ADMIN,),
                {MembershipRole.ORGANIZATION_ADMIN},
                (),
                (),
            ),
            (
                "organization-admin",
                (BookingRole.ORGANIZATION_ADMIN,),
                {MembershipRole.ORGANIZATION_ADMIN},
                (MembershipRole.ORGANIZATION_ADMIN,),
                (
                    BookingCapability.READ_ORGANIZATION,
                    BookingCapability.MANAGE_ORGANIZATION,
                ),
            ),
            (
                "worker",
                (BookingRole.WORKER,),
                {MembershipRole.WORKER},
                (MembershipRole.WORKER,),
                (
                    BookingCapability.READ_ORGANIZATION,
                    BookingCapability.MANAGE_OWN_WORKER_SCHEDULE,
                ),
            ),
            (
                "customer",
                (BookingRole.CUSTOMER,),
                {MembershipRole.CUSTOMER},
                (MembershipRole.CUSTOMER,),
                (
                    BookingCapability.READ_ORGANIZATION,
                    BookingCapability.MANAGE_OWN_BOOKINGS,
                ),
            ),
            (
                "multi-role",
                (
                    BookingRole.ORGANIZATION_ADMIN,
                    BookingRole.WORKER,
                    BookingRole.CUSTOMER,
                ),
                {
                    MembershipRole.ORGANIZATION_ADMIN,
                    MembershipRole.WORKER,
                    MembershipRole.CUSTOMER,
                },
                (
                    MembershipRole.ORGANIZATION_ADMIN,
                    MembershipRole.WORKER,
                    MembershipRole.CUSTOMER,
                ),
                (
                    BookingCapability.READ_ORGANIZATION,
                    BookingCapability.MANAGE_ORGANIZATION,
                    BookingCapability.MANAGE_OWN_WORKER_SCHEDULE,
                    BookingCapability.MANAGE_OWN_BOOKINGS,
                ),
            ),
        )
        for (
            name,
            coarse,
            stored,
            expected_roles,
            expected_capabilities,
        ) in cases:
            with self.subTest(persona=name):
                effective_roles = compatible_membership_roles(coarse, stored)
                self.assertEqual(effective_roles, expected_roles)
                self.assertEqual(
                    capabilities_for_membership_roles(effective_roles),
                    expected_capabilities,
                )

    def test_platform_capability_requires_both_authorization_gates(self) -> None:
        """Deny a coarse role or app grant in isolation and allow both together."""
        platform = BookingPrincipal("platform", (BookingRole.PLATFORM_ADMIN,))
        customer = BookingPrincipal("customer", (BookingRole.CUSTOMER,))
        active_access = SimpleNamespace(status="active")
        self.assertEqual(
            BookingTenancyService._platform_capabilities(platform, active_access),
            (BookingCapability.MANAGE_PLATFORM_ORGANIZATIONS,),
        )
        self.assertEqual(BookingTenancyService._platform_capabilities(platform, None), ())
        self.assertEqual(
            BookingTenancyService._platform_capabilities(customer, active_access), ()
        )

    def test_organization_display_name_is_trimmed_and_bounded(self) -> None:
        """Normalize visible names and reject blank platform create payloads."""
        self.assertEqual(
            OrganizationCreateRequest(display_name="  Studio North  ").display_name,
            "Studio North",
        )
        with self.assertRaises(ValidationError):
            OrganizationCreateRequest(display_name="   ")

    def test_migration_binds_roles_to_membership_tenant(self) -> None:
        """Retain the composite database boundary and app-owned first revision."""
        relative_path = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_001_tenancy.py"
        )
        candidates = (
            REPOSITORY_ROOT / "app" / relative_path,
            REPOSITORY_ROOT / relative_path,
        )
        migration_path = next(path for path in candidates if path.is_file())
        migration = migration_path.read_text(encoding="utf-8")
        self.assertIn('down_revision = None', migration)
        self.assertIn('"fk_booking_role_membership_scope"', migration)
        self.assertIn('"booking_organization_memberships.organization_id"', migration)


class BookingTenancyRouteTests(unittest.IsolatedAsyncioTestCase):
    """Prove route registration and safe context error translation."""

    async def test_context_route_returns_only_service_projection(self) -> None:
        """Return the injected context unchanged after principal verification."""
        response = EffectiveContextResponse(
            subject_id="subject-1",
            coarse_roles=(BookingRole.CUSTOMER,),
            platform_capabilities=(),
            organizations=(),
            context_revision="revision-1",
        )
        principal = BookingPrincipal("subject-1", (BookingRole.CUSTOMER,))
        observed = await read_effective_context(
            principal,
            _ContextServiceStub(response),  # type: ignore[arg-type]
        )
        self.assertEqual(observed, response)

    async def test_context_route_preserves_safe_structured_error(self) -> None:
        """Translate an inactive subject without leaking internal identifiers."""
        principal = BookingPrincipal("subject-1", (BookingRole.CUSTOMER,))
        service = _ContextServiceStub(
            TenancyError(403, "subject_inactive", "Booking access is not active")
        )
        with self.assertRaises(HTTPException) as context:
            await read_effective_context(principal, service)  # type: ignore[arg-type]
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(
            context.exception.detail,
            {
                "code": "subject_inactive",
                "message": "Booking access is not active",
                "retryable": False,
            },
        )

    def test_definition_has_only_versioned_non_api_route_prefixes(self) -> None:
        """Register selected Booking families without forbidden `/api` routes."""
        backend = definition.BACKEND_APP_DEFINITION
        self.assertEqual(
            backend.registered_route_prefixes(),
            (
                "/v1/me",
                "/v1/platform/organizations",
                "/v1/organizations",
                "/v1/discovery",
            ),
        )
        for registration in backend.route_registrations:
            self.assertFalse(registration.public_prefix.startswith("/api"))


if __name__ == "__main__":
    unittest.main()
