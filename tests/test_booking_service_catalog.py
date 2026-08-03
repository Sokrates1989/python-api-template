"""Validation, lifecycle, migration, and route tests for BKG-201."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.domain.service_catalog import ServiceOfferingStatus
from apps.booking_service.schemas.service_catalog import (
    ServiceOfferingCreateRequest,
    ServiceOfferingResponse,
    ServiceOfferingUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.service_catalog_service import (
    BookingServiceCatalogService,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for source-level migration checks."""


def _service_request(**changes: object) -> ServiceOfferingCreateRequest:
    """Build one valid timed-service request with optional overrides.

    Args:
        **changes: Fields replacing valid defaults.

    Returns:
        ServiceOfferingCreateRequest: Parsed normalized request.

    Raises:
        ValidationError: When overrides deliberately violate the contract.
    """
    payload: dict[str, object] = {
        "name": "Quality massage",
        "description": "A calm quality fixture",
        "category": "Wellness",
        "duration_minutes": 60,
        "setup_buffer_minutes": 10,
        "cleanup_buffer_minutes": 15,
        "slot_step_minutes": 15,
        "price_minor_units": 8_500,
        "currency": "EUR",
        "is_published": True,
        "location_ids": ("location-b", "location-a"),
    }
    payload.update(changes)
    return ServiceOfferingCreateRequest(**payload)


class BookingServiceCatalogPolicyTests(unittest.TestCase):
    """Prove catalog normalization and finite scheduling/money bounds."""

    def test_service_normalizes_text_currency_and_locations(self) -> None:
        """Normalize safe presentation values and deterministic assignments."""
        request = _service_request(
            name="  Quality massage  ",
            description="   ",
            currency="eur",
        )
        self.assertEqual(request.name, "Quality massage")
        self.assertIsNone(request.description)
        self.assertEqual(request.currency, "EUR")
        self.assertEqual(request.location_ids, ("location-a", "location-b"))

    def test_service_rejects_invalid_time_money_and_assignments(self) -> None:
        """Reject invalid duration, step, price, and duplicate locations."""
        invalid = (
            {"duration_minutes": 0},
            {"setup_buffer_minutes": 1_441},
            {"slot_step_minutes": 7},
            {"price_minor_units": -1},
            {"currency": "ZZZ"},
            {"location_ids": ("location-a", "location-a")},
            {"location_ids": ()},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ValidationError):
                    _service_request(**override)

    def test_response_retains_versioned_snapshot_fields(self) -> None:
        """Expose every field later copied into immutable appointments."""
        request = _service_request()
        response = ServiceOfferingResponse(
            organization_id="organization-a",
            service_offering_id="service-a",
            status=ServiceOfferingStatus.ACTIVE,
            revision=3,
            **request.model_dump(mode="python"),
        )
        self.assertEqual(response.price_minor_units, 8_500)
        self.assertEqual(response.duration_minutes, 60)
        self.assertEqual(response.revision, 3)


class BookingServiceCatalogLifecycleTests(unittest.TestCase):
    """Prove fail-closed visibility and optimistic replacement helpers."""

    def test_ordinary_member_cannot_read_unpublished_or_archived_service(self) -> None:
        """Hide non-customer-visible rows behind the uniform not-found result."""
        for status, published in (("active", False), ("archived", True)):
            with self.subTest(status=status, published=published):
                offering = SimpleNamespace(status=status, is_published=published)
                with self.assertRaises(TenancyError) as context:
                    BookingServiceCatalogService._require_visible(
                        offering,  # type: ignore[arg-type]
                        administrator=False,
                    )
                self.assertEqual(context.exception.status_code, 404)

    def test_administrator_may_read_archived_service(self) -> None:
        """Retain archived catalog visibility needed for reactivation."""
        offering = SimpleNamespace(status="archived", is_published=False)
        BookingServiceCatalogService._require_visible(
            offering,  # type: ignore[arg-type]
            administrator=True,
        )

    def test_revision_conflict_is_retryable(self) -> None:
        """Require a reload before replacing stale catalog state."""
        offering = SimpleNamespace(revision=4, status="active")
        with self.assertRaises(TenancyError) as context:
            BookingServiceCatalogService._require_mutable(
                offering,  # type: ignore[arg-type]
                3,
            )
        self.assertEqual(context.exception.code, "service_revision_conflict")
        self.assertTrue(context.exception.retryable)

    def test_complete_replacement_does_not_change_identity_or_status(self) -> None:
        """Apply mutable fields while preserving resource and lifecycle identity."""
        offering = SimpleNamespace(
            id="service-a",
            organization_id="organization-a",
            status="active",
        )
        request = ServiceOfferingUpdateRequest(
            expected_revision=2,
            **_service_request(name="Updated service").model_dump(mode="python"),
        )
        BookingServiceCatalogService._apply_fields(  # type: ignore[arg-type]
            offering,
            request,
        )
        self.assertEqual(offering.id, "service-a")
        self.assertEqual(offering.organization_id, "organization-a")
        self.assertEqual(offering.status, "active")
        self.assertEqual(offering.name, "Updated service")


class BookingServiceCatalogContractTests(unittest.TestCase):
    """Retain migration, tenant-FK, route, and forbidden-prefix evidence."""

    def test_migration_uses_tenant_composite_foreign_keys(self) -> None:
        """Require exact revision chain and database tenant ownership."""
        relative = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_004_service_catalog.py"
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
        self.assertIn('down_revision = "booking_service_003"', migration)
        self.assertIn("fk_booking_service_location_service_tenant", migration)
        self.assertIn("fk_booking_service_location_location_tenant", migration)
        self.assertIn("price_minor_units BETWEEN 0", migration)

    def test_catalog_routes_are_versioned_and_service_root_relative(self) -> None:
        """Register exact catalog methods without a forbidden `/api` prefix."""
        routes: dict[str, set[str]] = {}
        registration = definition.BACKEND_APP_DEFINITION.route_registrations[2]
        for route in registration.router.routes:
            routes.setdefault(route.path, set()).update(route.methods or set())
        collection = "/v1/organizations/{organization_id}/services"
        item = f"{collection}/{{service_offering_id}}"
        self.assertEqual(routes[collection], {"GET", "POST"})
        self.assertEqual(routes[item], {"DELETE", "GET", "PUT"})
        self.assertEqual(routes[f"{item}/reactivate"], {"POST"})
        self.assertTrue(all(not path.startswith("/api") for path in routes))


if __name__ == "__main__":
    unittest.main()
