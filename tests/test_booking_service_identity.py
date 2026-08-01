"""Contract tests for Booking Service role extraction and identity projection."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from apps.booking_service import definition
from apps.booking_service.dependencies import identity as identity_module
from apps.booking_service.dependencies.identity import (
    BookingPrincipal,
    BookingRole,
    extract_booking_roles,
    get_booking_principal,
)
from apps.booking_service.routes.identity import read_effective_identity


def _verified_user_info(claims: object, provider: str = "keycloak") -> dict[str, object]:
    """Build one shared-auth-shaped user info fixture.

    Args:
        claims: Raw verified-claims stand-in supplied to principal construction.
        provider: Provider label; defaults to Keycloak.

    Returns:
        dict[str, object]: Minimal normalized authentication payload.
    """
    return {"provider": provider, "claims": claims}


class BookingIdentityTests(unittest.TestCase):
    """Prove client-role allowlisting and fail-closed subject projection."""

    def test_client_roles_are_allowlisted_deduplicated_and_ordered(self) -> None:
        """Ignore unknown roles and emit the fixed independent-role order."""
        claims = {
            "resource_access": {
                "keycloak": {
                    "roles": [
                        "customer",
                        "worker",
                        "customer",
                        "unknown",
                        "platform_admin",
                    ]
                }
            }
        }
        self.assertEqual(
            extract_booking_roles(claims, "keycloak"),
            (
                BookingRole.PLATFORM_ADMIN,
                BookingRole.WORKER,
                BookingRole.CUSTOMER,
            ),
        )

    def test_realm_only_and_malformed_claims_grant_no_role(self) -> None:
        """Treat every unconfigured or incorrectly typed role source as empty."""
        malformed_claims = (
            {"realm_access": {"roles": ["platform_admin"]}},
            {"resource_access": []},
            {"resource_access": {"keycloak": []}},
            {"resource_access": {"keycloak": {"roles": "customer"}}},
            {"resource_access": {"other-client": {"roles": ["worker"]}}},
        )
        for claims in malformed_claims:
            with self.subTest(claims=claims):
                self.assertEqual(extract_booking_roles(claims, "keycloak"), ())
        self.assertEqual(
            extract_booking_roles(
                {"resource_access": {"keycloak": {"roles": ["customer"]}}},
                "",
            ),
            (),
        )

    def test_principal_requires_keycloak_claims_and_exact_subject(self) -> None:
        """Reject debug-provider and fallback identity fields before projection."""
        invalid_payloads = (
            _verified_user_info({"sub": "subject", "typ": "Bearer"}, provider="none"),
            _verified_user_info(None),
            _verified_user_info({"sid": "fallback-is-forbidden"}),
            _verified_user_info({"sub": "   ", "typ": "Bearer"}),
            _verified_user_info({"sub": "subject", "typ": "ID"}),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(HTTPException) as context:
                get_booking_principal(payload)
            self.assertEqual(context.exception.status_code, 401)

    def test_principal_allows_valid_subject_with_no_booking_roles(self) -> None:
        """Represent an authenticated but unentitled subject without invention."""
        settings_stub = SimpleNamespace(KEYCLOAK_CLIENT_ID="keycloak")
        with patch.object(identity_module, "settings", settings_stub):
            principal = get_booking_principal(
                _verified_user_info(
                    {
                        "sub": "subject-without-membership",
                        "typ": "Bearer",
                        "realm_access": {"roles": ["customer"]},
                    }
                )
            )
        self.assertEqual(principal.subject_id, "subject-without-membership")
        self.assertEqual(principal.roles, ())

    def test_route_returns_only_the_sanitized_projection(self) -> None:
        """Expose only subject and allowlisted roles from a verified principal."""
        response = read_effective_identity(
            BookingPrincipal(
                subject_id="subject-1",
                roles=(BookingRole.ORGANIZATION_ADMIN, BookingRole.WORKER),
            )
        )
        self.assertEqual(
            response.model_dump(mode="json"),
            {
                "subject_id": "subject-1",
                "roles": ["organization_admin", "worker"],
            },
        )

    def test_definition_registers_exact_bearer_protected_route(self) -> None:
        """Keep identity exact while BKG-101 adds protected route families."""
        backend = definition.BACKEND_APP_DEFINITION
        self.assertEqual(
            backend.registered_route_prefixes(),
            (
                "/v1/me",
                "/v1/platform/organizations",
                "/v1/organizations",
            ),
        )
        self.assertEqual(
            tuple(scheme.name for scheme in backend.openapi_security_schemes),
            ("BookingBearer",),
        )
        requirement = backend.openapi_route_security[0]
        self.assertTrue(requirement.matches_path("/v1/me/identity"))
        self.assertFalse(requirement.matches_path("/v1/me/context"))
        context_requirement = backend.openapi_route_security[1]
        self.assertTrue(context_requirement.matches_path("/v1/me/context"))


if __name__ == "__main__":
    unittest.main()
