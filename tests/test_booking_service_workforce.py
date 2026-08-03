"""Validation, lifecycle, migration, and route tests for BKG-202."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.domain.tenancy import MembershipRole
from apps.booking_service.domain.workforce import (
    ServiceWorkerSelectionMode,
    WorkerProfileStatus,
    service_mode_from_company_default,
)
from apps.booking_service.domain.company_settings import WorkerSelectionMode
from apps.booking_service.schemas.workforce import (
    WorkerProfileCreateRequest,
    WorkerProfileUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import ActiveOrganizationAccess
from apps.booking_service.services.workforce_service import BookingWorkforceService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for source-level migration checks."""


def _worker_request(**changes: object) -> WorkerProfileCreateRequest:
    """Build one valid explicit worker-profile request.

    Args:
        **changes: Fields replacing valid defaults.

    Returns:
        WorkerProfileCreateRequest: Parsed normalized request.

    Raises:
        ValidationError: When an override deliberately violates the contract.
    """
    payload: dict[str, object] = {
        "membership_id": "membership-worker",
        "public_name": "Alex Quality",
        "public_description": "Qualified massage professional",
        "is_publicly_bookable": True,
        "location_ids": ("location-b", "location-a"),
        "qualifications": (
            {
                "service_offering_id": "service-b",
                "auto_eligible": False,
                "priority": 200,
            },
            {
                "service_offering_id": "service-a",
                "auto_eligible": True,
                "priority": 50,
            },
        ),
    }
    payload.update(changes)
    return WorkerProfileCreateRequest(**payload)


class BookingWorkforcePolicyTests(unittest.TestCase):
    """Prove normalization, explicit assignment, and selection-mode policy."""

    def test_worker_normalizes_presentation_and_assignment_order(self) -> None:
        """Normalize optional text while retaining explicit sorted assignments."""
        request = _worker_request(
            public_name="  Alex Quality  ",
            public_description="   ",
        )
        self.assertEqual(request.public_name, "Alex Quality")
        self.assertIsNone(request.public_description)
        self.assertEqual(request.location_ids, ("location-a", "location-b"))
        self.assertEqual(
            tuple(item.service_offering_id for item in request.qualifications),
            ("service-a", "service-b"),
        )

    def test_public_worker_requires_name_and_unique_assignments(self) -> None:
        """Reject unsafe presentation and duplicate tenant associations."""
        invalid = (
            {"public_name": None},
            {"location_ids": ("location-a", "location-a")},
            {
                "qualifications": (
                    {"service_offering_id": "service-a"},
                    {"service_offering_id": "service-a"},
                )
            },
            {"membership_id": " membership-worker"},
        )
        for override in invalid:
            with self.subTest(override=override):
                with self.assertRaises(ValidationError):
                    _worker_request(**override)

    def test_company_default_only_initializes_service_owned_mode(self) -> None:
        """Map each company default to its service-level initial policy."""
        expected = {
            WorkerSelectionMode.NEXT_AVAILABLE_ONLY: (
                ServiceWorkerSelectionMode.AUTO_ONLY
            ),
            WorkerSelectionMode.SPECIFIC_WORKER_ONLY: (
                ServiceWorkerSelectionMode.SPECIFIC_ONLY
            ),
            WorkerSelectionMode.NEXT_AVAILABLE_OR_SPECIFIC: (
                ServiceWorkerSelectionMode.SPECIFIC_OR_AUTO
            ),
        }
        self.assertEqual(
            {mode: service_mode_from_company_default(mode) for mode in expected},
            expected,
        )


class BookingWorkforceLifecycleTests(unittest.TestCase):
    """Prove optimistic replacement and exact worker self visibility."""

    def test_complete_replacement_preserves_identity_and_lifecycle(self) -> None:
        """Apply mutable fields without changing tenant, membership, or status."""
        profile = SimpleNamespace(
            id="worker-a",
            organization_id="organization-a",
            membership_id="membership-worker",
            status=WorkerProfileStatus.ACTIVE.value,
        )
        fields = _worker_request(public_name="Updated public name").model_dump(
            mode="python",
            exclude={"membership_id"},
        )
        request = WorkerProfileUpdateRequest(expected_revision=2, **fields)
        BookingWorkforceService._apply_fields(profile, request)  # type: ignore[arg-type]
        self.assertEqual(profile.id, "worker-a")
        self.assertEqual(profile.organization_id, "organization-a")
        self.assertEqual(profile.membership_id, "membership-worker")
        self.assertEqual(profile.status, WorkerProfileStatus.ACTIVE.value)
        self.assertEqual(profile.public_name, "Updated public name")

    def test_stale_worker_revision_is_retryable(self) -> None:
        """Require a reload before replacing stale workforce state."""
        profile = SimpleNamespace(revision=4)
        with self.assertRaises(TenancyError) as context:
            BookingWorkforceService._require_profile(  # type: ignore[arg-type]
                profile,
                3,
            )
        self.assertEqual(context.exception.code, "worker_revision_conflict")
        self.assertTrue(context.exception.retryable)

    def test_worker_may_read_only_their_own_profile(self) -> None:
        """Hide colleague and foreign identifiers behind safe not-found behavior."""
        access = ActiveOrganizationAccess(
            organization=SimpleNamespace(id="organization-a"),  # type: ignore[arg-type]
            membership_id="membership-self",
            roles=(MembershipRole.WORKER,),
        )
        own = SimpleNamespace(membership_id="membership-self")
        BookingWorkforceService._require_visible_profile(  # type: ignore[arg-type]
            own,
            access,
        )
        with self.assertRaises(TenancyError) as context:
            BookingWorkforceService._require_visible_profile(  # type: ignore[arg-type]
                SimpleNamespace(membership_id="membership-colleague"),
                access,
            )
        self.assertEqual(context.exception.status_code, 404)


class BookingWorkforceContractTests(unittest.TestCase):
    """Retain migration, composite-FK, route, and prefix evidence."""

    def test_migration_uses_tenant_composite_foreign_keys(self) -> None:
        """Require the exact revision chain and database tenant ownership."""
        relative = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_005_workforce.py"
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
        self.assertIn('down_revision = "booking_service_004"', migration)
        self.assertIn("fk_booking_worker_membership_scope", migration)
        self.assertIn("fk_booking_worker_location_location_scope", migration)
        self.assertIn("fk_booking_worker_qualification_service_scope", migration)
        self.assertIn("worker_selection_mode", migration)

    def test_workforce_routes_are_versioned_and_service_root_relative(self) -> None:
        """Register exact workforce methods without a forbidden `/api` prefix."""
        routes: dict[str, set[str]] = {}
        registration = definition.BACKEND_APP_DEFINITION.route_registrations[2]
        for route in registration.router.routes:
            routes.setdefault(route.path, set()).update(route.methods or set())
        collection = "/v1/organizations/{organization_id}/workers"
        item = f"{collection}/{{worker_profile_id}}"
        self.assertEqual(routes[collection], {"GET", "POST"})
        self.assertEqual(routes[item], {"DELETE", "GET", "PUT"})
        self.assertEqual(routes[f"{item}/reactivate"], {"POST"})
        self.assertTrue(all(not path.startswith("/api") for path in routes))


if __name__ == "__main__":
    unittest.main()
