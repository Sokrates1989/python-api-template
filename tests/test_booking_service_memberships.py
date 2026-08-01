"""Security and provider-boundary tests for BKG-103 memberships."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.domain.membership_policy import (
    MembershipManagementScope,
    MembershipPolicyError,
    validate_membership_roles,
    validate_membership_transition,
)
from apps.booking_service.domain.tenancy import MembershipRole, MembershipStatus
from apps.booking_service.schemas.membership import (
    MembershipInvitationRequest,
    MembershipUpdateRequest,
)
from apps.booking_service.services.identity_administration import (
    IdentityAdministrationError,
    KeycloakIdentityAdministrationAdapter,
)
from apps.booking_service.services.membership_audit import membership_audit_state


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for migration and route contract checks."""


class _FakeResponse:
    """Provide one minimal requests-compatible response."""

    def __init__(self, status_code: int, payload: object | None = None) -> None:
        """Retain a status and JSON payload.

        Args:
            status_code: HTTP status returned to the adapter.
            payload: Optional JSON-compatible response body.

        Returns:
            None: The fixture retains both values.
        """
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        """Return the configured JSON payload.

        Returns:
            object: Configured response payload.
        """
        return self._payload


class _FakeRequestSession:
    """Capture the exact bounded Keycloak request sequence."""

    def __init__(self) -> None:
        """Create an empty request capture.

        Returns:
            None: Calls are appended as the adapter runs.
        """
        self.calls: list[tuple[str, str, object | None]] = []

    def post(self, url: str, *, data: object, timeout: int) -> _FakeResponse:
        """Return a service-account token without retaining its secret.

        Args:
            url: Token endpoint URL.
            data: Client-credentials form payload.
            timeout: Bounded request timeout.

        Returns:
            _FakeResponse: Successful token response.
        """
        self.calls.append(("TOKEN", url, {"timeout": timeout, "grant_type": data["grant_type"]}))
        return _FakeResponse(200, {"access_token": "provider-token"})

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: object | None,
        params: object | None,
        timeout: int,
    ) -> _FakeResponse:
        """Return deterministic user, client, role, and mapping responses.

        Args:
            method: Requested HTTP method.
            url: Provider URL.
            headers: Authorization header, deliberately not retained.
            json: Optional role-mapping payload.
            params: Optional client lookup parameters.
            timeout: Bounded request timeout.

        Returns:
            _FakeResponse: Response appropriate to the requested path.
        """
        del headers, timeout
        self.calls.append((method, url, json if json is not None else params))
        if url.endswith("/users/subject-1"):
            return _FakeResponse(200, {})
        if url.endswith("/clients"):
            return _FakeResponse(200, [{"id": "frontend-uuid"}])
        if "/roles/" in url:
            role_name = url.rsplit("/", maxsplit=1)[-1]
            return _FakeResponse(200, {"id": f"role-{role_name}", "name": role_name})
        return _FakeResponse(204, None)


def _identity_settings(*, configured: bool = True) -> SimpleNamespace:
    """Build the minimal Settings-compatible identity adapter fixture.

    Args:
        configured: Whether the dedicated admin client ID is present.

    Returns:
        SimpleNamespace: Public configuration plus secret-reader methods.
    """
    value = SimpleNamespace(
        KEYCLOAK_INTERNAL_URL="http://keycloak:8080",
        KEYCLOAK_SERVER_URL="https://keycloak.example",
        KEYCLOAK_REALM="booking-service-example",
        KEYCLOAK_CLIENT_ID="keycloak",
        KEYCLOAK_ADMIN_CLIENT_ID="booking-membership-admin" if configured else None,
    )
    value.get_auth_provider = lambda: "keycloak"
    value.get_keycloak_admin_client_secret = lambda: "admin-secret"
    return value


class BookingMembershipPolicyTests(unittest.TestCase):
    """Prove scoped grants, lifecycle, and last-admin invariants."""

    def test_organization_admin_manages_only_worker_and_customer(self) -> None:
        """Reject organization-admin role management by a tenant administrator."""
        validate_membership_roles(
            MembershipManagementScope.ORGANIZATION,
            frozenset(),
            frozenset({MembershipRole.WORKER, MembershipRole.CUSTOMER}),
        )
        with self.assertRaises(MembershipPolicyError) as context:
            validate_membership_roles(
                MembershipManagementScope.ORGANIZATION,
                frozenset(),
                frozenset({MembershipRole.ORGANIZATION_ADMIN}),
            )
        self.assertEqual(context.exception.code, "membership_role_escalation_denied")

    def test_final_active_administrator_cannot_be_removed(self) -> None:
        """Prevent role removal, suspension, and revocation of the final admin."""
        for status, roles in (
            (MembershipStatus.ACTIVE, frozenset({MembershipRole.WORKER})),
            (MembershipStatus.SUSPENDED, frozenset({MembershipRole.ORGANIZATION_ADMIN})),
            (MembershipStatus.REVOKED, frozenset({MembershipRole.ORGANIZATION_ADMIN})),
        ):
            with self.subTest(status=status, roles=roles):
                with self.assertRaises(MembershipPolicyError) as context:
                    validate_membership_transition(
                        scope=MembershipManagementScope.PLATFORM,
                        current_status=MembershipStatus.ACTIVE,
                        current_roles=frozenset({MembershipRole.ORGANIZATION_ADMIN}),
                        target_status=status,
                        target_roles=roles,
                        active_admin_count=1,
                    )
                self.assertEqual(
                    context.exception.code,
                    "last_organization_admin_required",
                )

    def test_second_administrator_allows_safe_revocation(self) -> None:
        """Allow a platform actor to revoke one of two active administrators."""
        validate_membership_transition(
            scope=MembershipManagementScope.PLATFORM,
            current_status=MembershipStatus.ACTIVE,
            current_roles=frozenset({MembershipRole.ORGANIZATION_ADMIN}),
            target_status=MembershipStatus.REVOKED,
            target_roles=frozenset({MembershipRole.ORGANIZATION_ADMIN}),
            active_admin_count=2,
        )

    def test_schema_cannot_accept_platform_admin_membership(self) -> None:
        """Reject platform access and empty roles before service mutation."""
        with self.assertRaises(ValidationError):
            MembershipInvitationRequest(
                subject_id="subject-1",
                roles=["platform_admin"],
            )
        with self.assertRaises(ValidationError):
            MembershipUpdateRequest(
                expected_revision=1,
                status="active",
                roles=[],
            )

    def test_subject_identifier_rejects_profile_like_whitespace(self) -> None:
        """Keep the invitation contract on one opaque immutable identifier."""
        with self.assertRaises(ValidationError):
            MembershipInvitationRequest(
                subject_id="user@example.com display",
                roles=[MembershipRole.CUSTOMER],
            )


class BookingIdentityAdministrationTests(unittest.IsolatedAsyncioTestCase):
    """Prove the Keycloak adapter's least-privilege request surface."""

    async def test_adapter_grants_only_requested_booking_client_roles(self) -> None:
        """Send no password, profile, realm-role, or unrelated mutation payload."""
        session = _FakeRequestSession()
        adapter = KeycloakIdentityAdministrationAdapter(
            _identity_settings(),  # type: ignore[arg-type]
            request_session=session,  # type: ignore[arg-type]
        )
        await adapter.ensure_client_roles(
            "subject-1",
            frozenset({MembershipRole.WORKER, MembershipRole.CUSTOMER}),
        )
        mapping_method, mapping_url, mapping_payload = session.calls[-1]
        self.assertEqual(mapping_method, "POST")
        self.assertIn("/role-mappings/clients/frontend-uuid", mapping_url)
        self.assertEqual(
            {item["name"] for item in mapping_payload},
            {"worker", "customer"},
        )
        rendered = repr(session.calls).lower()
        self.assertNotIn("password", rendered)
        self.assertNotIn("email", rendered)
        self.assertNotIn("admin-secret", rendered)
        self.assertNotIn("provider-token", rendered)

    async def test_missing_admin_client_is_safe_non_retryable_failure(self) -> None:
        """Classify incomplete deployment configuration without network access."""
        adapter = KeycloakIdentityAdministrationAdapter(
            _identity_settings(configured=False),  # type: ignore[arg-type]
            request_session=_FakeRequestSession(),  # type: ignore[arg-type]
        )
        with self.assertRaises(IdentityAdministrationError) as context:
            await adapter.ensure_client_roles(
                "subject-1", frozenset({MembershipRole.CUSTOMER})
            )
        self.assertEqual(context.exception.code, "identity_provider_not_configured")
        self.assertFalse(context.exception.retryable)


class BookingMembershipContractTests(unittest.TestCase):
    """Retain migration, route, and forbidden-prefix evidence."""

    def test_audit_snapshot_excludes_identity_and_provider_secrets(self) -> None:
        """Persist only membership lifecycle data in audit snapshots."""
        state = membership_audit_state(
            status=MembershipStatus.ACTIVE.value,
            roles=frozenset({MembershipRole.CUSTOMER}),
            revision=3,
        )
        self.assertEqual(
            state,
            {"status": "active", "roles": ["customer"], "revision": 3},
        )
        rendered = repr(state).lower()
        self.assertNotIn("subject", rendered)
        self.assertNotIn("token", rendered)

    def test_outbox_migration_is_scoped_to_membership_revision(self) -> None:
        """Require durable tenant binding and deterministic newest-work ordering."""
        relative = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_002_membership_identity_outbox.py"
        )
        path = next(
            candidate
            for candidate in (
                REPOSITORY_ROOT / "app" / relative,
                REPOSITORY_ROOT / relative,
            )
            if candidate.is_file()
        )
        migration = path.read_text(encoding="utf-8")
        self.assertIn('down_revision = "booking_service_001"', migration)
        self.assertIn('"membership_revision"', migration)
        self.assertIn('"fk_booking_identity_outbox_membership_scope"', migration)

    def test_membership_routes_share_versioned_organization_boundary(self) -> None:
        """Register list, invite, update, and retry without an `/api` prefix."""
        routes = {
            route.path: route.methods
            for route in definition.BACKEND_APP_DEFINITION.route_registrations[2].router.routes
        }
        self.assertIn("/v1/organizations/{organization_id}/memberships", routes)
        self.assertIn(
            "/v1/organizations/{organization_id}/memberships/{membership_id}",
            routes,
        )
        self.assertIn(
            "/v1/organizations/{organization_id}/memberships/{membership_id}/retry-identity-sync",
            routes,
        )
        self.assertTrue(all(not path.startswith("/api") for path in routes))


if __name__ == "__main__":
    unittest.main()
