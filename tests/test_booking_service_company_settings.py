"""Policy, authorization, migration, and route tests for BKG-200."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.dependencies.identity import BookingPrincipal, BookingRole
from apps.booking_service.domain.company_settings import (
    PaymentConfigurationStatus,
    WorkerSelectionMode,
)
from apps.booking_service.domain.tenancy import MembershipRole
from apps.booking_service.models.tenancy import BookingOrganization
from apps.booking_service.schemas.company_settings import (
    CompanySettingsResponse,
    CompanySettingsUpdateRequest,
    LocationCreateRequest,
)
from apps.booking_service.services.company_settings_service import (
    BookingCompanySettingsService,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import (
    require_organization_administrator,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for source-level migration checks."""


def _settings_request(**changes: object) -> CompanySettingsUpdateRequest:
    """Build one valid complete company-settings replacement fixture.

    Args:
        **changes: Field overrides applied to the valid default payload.

    Returns:
        CompanySettingsUpdateRequest: Parsed replacement request.

    Raises:
        ValidationError: When an override deliberately violates the contract.
    """
    payload: dict[str, object] = {
        "expected_revision": 1,
        "public_name": "Quality Studio",
        "description": None,
        "contact_email": None,
        "contact_phone": None,
        "website_url": "https://felicitas-wisdom.com",
        "default_timezone": "Europe/Berlin",
        "default_locale": "de",
        "currency": "EUR",
        "booking_horizon_days": 90,
        "minimum_notice_minutes": 120,
        "cancellation_notice_minutes": 1440,
        "reschedule_notice_minutes": 1440,
        "worker_selection_mode": "next_available_or_specific",
    }
    payload.update(changes)
    return CompanySettingsUpdateRequest(**payload)


class _OrganizationRepositoryStub:
    """Provide deterministic app-owned tenancy rows for access-policy tests."""

    def __init__(self, *, role: MembershipRole | None) -> None:
        """Configure one active membership role or an absent membership.

        Args:
            role: Stored membership role, or ``None`` to hide the tenant.

        Returns:
            None: The fixture retains the configured role.
        """
        self._role = role

    async def ensure_subject(self, subject_id: str) -> SimpleNamespace:
        """Return one active app-owned subject.

        Args:
            subject_id: Verified subject accepted by the fixture.

        Returns:
            SimpleNamespace: Active subject lifecycle row.
        """
        del subject_id
        return SimpleNamespace(status="active")

    async def get_membership(
        self,
        organization_id: str,
        subject_id: str,
    ) -> SimpleNamespace | None:
        """Return an active membership only when a role was configured.

        Args:
            organization_id: Requested tenant identifier.
            subject_id: Verified subject identifier.

        Returns:
            SimpleNamespace | None: Active membership or ``None``.
        """
        del organization_id, subject_id
        if self._role is None:
            return None
        return SimpleNamespace(id="membership-1", status="active")

    async def get_organization(self, organization_id: str) -> SimpleNamespace:
        """Return one active organization fixture.

        Args:
            organization_id: Requested tenant identifier.

        Returns:
            SimpleNamespace: Active tenant row.
        """
        return SimpleNamespace(id=organization_id, status="active")

    async def get_membership_roles(
        self,
        organization_id: str,
        membership_id: str,
    ) -> set[MembershipRole]:
        """Return the configured same-tenant membership role.

        Args:
            organization_id: Tenant owning the role.
            membership_id: Membership owning the role.

        Returns:
            set[MembershipRole]: Empty or singleton role set.
        """
        del organization_id, membership_id
        return set() if self._role is None else {self._role}


class BookingCompanySettingsPolicyTests(unittest.TestCase):
    """Prove validation, normalization, and placeholder contracts."""

    def test_settings_normalize_supported_locale_currency_and_url(self) -> None:
        """Normalize supported values while retaining an explicit payment deferment."""
        request = _settings_request(
            public_name="  Quality Studio  ",
            default_locale="DE",
            currency="eur",
        )
        self.assertEqual(request.public_name, "Quality Studio")
        self.assertEqual(request.default_locale, "de")
        self.assertEqual(request.currency, "EUR")
        response_fields = request.model_dump(exclude={"expected_revision"})
        response = CompanySettingsResponse(
            organization_id="organization-1",
            payment_configuration_status=PaymentConfigurationStatus.NOT_CONFIGURED,
            revision=1,
            locations=(),
            **response_fields,
        )
        self.assertEqual(
            response.worker_selection_mode,
            WorkerSelectionMode.NEXT_AVAILABLE_OR_SPECIFIC,
        )
        self.assertEqual(response.payment_configuration_status, "not_configured")

    def test_settings_reject_unsupported_zone_currency_and_notice_window(self) -> None:
        """Reject unsupported scheduling inputs before persistence begins."""
        for override in (
            {"default_timezone": "Mars/Olympus"},
            {"currency": "ZZZ"},
            {"booking_horizon_days": 1, "minimum_notice_minutes": 1441},
        ):
            with self.subTest(override=override):
                with self.assertRaises(ValidationError):
                    _settings_request(**override)

    def test_location_normalizes_blank_address_and_country(self) -> None:
        """Support virtual/mobile places without inventing physical address data."""
        location = LocationCreateRequest(
            display_name="  Mobile service  ",
            timezone="Europe/Berlin",
            address_line_1="   ",
            country_code="de",
        )
        self.assertEqual(location.display_name, "Mobile service")
        self.assertIsNone(location.address_line_1)
        self.assertEqual(location.country_code, "DE")

    def test_public_company_name_synchronizes_tenant_selector_identity(self) -> None:
        """Keep the organization-context label aligned with the public name."""
        organization = BookingOrganization(
            id="organization-1",
            display_name="Old name",
            status="active",
            revision=4,
        )

        BookingCompanySettingsService._apply_organization_display_name(
            organization,
            "New public name",
        )

        self.assertEqual(organization.display_name, "New public name")
        self.assertEqual(organization.revision, 5)

        BookingCompanySettingsService._apply_organization_display_name(
            organization,
            "New public name",
        )
        self.assertEqual(organization.revision, 5)

class BookingCompanySettingsAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    """Prove same-tenant admin access without platform-role bypass."""

    async def test_platform_role_without_membership_cannot_manage_settings(self) -> None:
        """Keep platform administration separate from tenant configuration."""
        repository = _OrganizationRepositoryStub(role=None)
        principal = BookingPrincipal("platform", (BookingRole.PLATFORM_ADMIN,))
        with patch(
            "apps.booking_service.services.organization_access.TenancyRepository",
            return_value=repository,
        ):
            with self.assertRaises(TenancyError) as context:
                await require_organization_administrator(
                    SimpleNamespace(),  # type: ignore[arg-type]
                    principal,
                    "organization-1",
                )
        self.assertEqual(context.exception.status_code, 404)

    async def test_worker_cannot_manage_settings(self) -> None:
        """Reject a compatible active membership lacking administrator role."""
        repository = _OrganizationRepositoryStub(role=MembershipRole.WORKER)
        principal = BookingPrincipal("worker", (BookingRole.WORKER,))
        with patch(
            "apps.booking_service.services.organization_access.TenancyRepository",
            return_value=repository,
        ):
            with self.assertRaises(TenancyError) as context:
                await require_organization_administrator(
                    SimpleNamespace(),  # type: ignore[arg-type]
                    principal,
                    "organization-1",
                )
        self.assertEqual(context.exception.code, "organization_management_denied")


class BookingCompanySettingsContractTests(unittest.TestCase):
    """Retain migration, route, and forbidden-prefix evidence."""

    def test_name_reconciliation_migration_repairs_existing_drift(self) -> None:
        """Keep the data repair chained after the complete Phase 2 schema."""
        relative = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_006_canonical_company_name.py"
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

        self.assertIn('revision = "booking_service_006"', migration)
        self.assertIn('down_revision = "booking_service_005"', migration)
        self.assertIn("UPDATE booking_organizations AS organization", migration)
        self.assertIn("display_name = settings.public_name", migration)
        self.assertIn("revision = organization.revision + 1", migration)

    def test_migration_backfills_scoped_defaults_and_soft_lifecycle(self) -> None:
        """Require revision-chain, tenant uniqueness, backfill, and archive state."""
        relative = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_003_company_settings.py"
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
        self.assertIn('down_revision = "booking_service_002"', migration)
        self.assertIn('"uq_booking_location_org_id"', migration)
        self.assertIn("INSERT INTO booking_company_settings", migration)
        self.assertIn("status IN ('active', 'archived')", migration)

    def test_company_routes_share_versioned_organization_boundary(self) -> None:
        """Register settings/location methods without a forbidden `/api` prefix."""
        routes: dict[str, set[str]] = {}
        for route in definition.BACKEND_APP_DEFINITION.route_registrations[2].router.routes:
            routes.setdefault(route.path, set()).update(route.methods or set())
        settings_path = "/v1/organizations/{organization_id}/company-settings"
        locations_path = "/v1/organizations/{organization_id}/locations"
        location_path = (
            "/v1/organizations/{organization_id}/locations/{location_id}"
        )
        reactivation_path = f"{location_path}/reactivate"
        self.assertEqual(routes[settings_path], {"GET", "PUT"})
        self.assertEqual(routes[locations_path], {"POST"})
        self.assertEqual(routes[location_path], {"DELETE", "PUT"})
        self.assertEqual(routes[reactivation_path], {"POST"})
        self.assertTrue(all(not path.startswith("/api") for path in routes))


if __name__ == "__main__":
    unittest.main()
