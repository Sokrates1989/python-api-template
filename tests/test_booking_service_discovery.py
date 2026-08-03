"""Privacy, projection, and route-contract tests for BKG-203 discovery."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.booking_service import definition
from apps.booking_service.schemas.discovery import (
    DiscoveryServiceResponse,
    DiscoveryWorkerResponse,
)
from apps.booking_service.services.discovery_service import BookingDiscoveryService


class BookingDiscoveryProjectionTests(unittest.TestCase):
    """Prove the public service projection excludes internal booking state."""

    def test_service_projection_intersects_worker_and_service_locations(self) -> None:
        """Expose a worker only at locations where the service is offered."""
        offering = SimpleNamespace(
            id="service-a",
            name="Massage",
            description="Relaxing treatment",
            category="Wellness",
            duration_minutes=60,
            price_minor_units=8_500,
            currency="EUR",
            worker_selection_mode="specific_or_auto",
        )
        worker = DiscoveryWorkerResponse(
            worker_profile_id="worker-a",
            public_name="Alex",
            public_description=None,
            location_ids=("location-a", "location-private-for-this-service"),
        )
        response = BookingDiscoveryService._project_service(  # type: ignore[arg-type]
            offering,
            ("location-a",),
            {"service-a": (worker,)},
        )
        self.assertEqual(response.workers[0].location_ids, ("location-a",))
        self.assertEqual(response.duration_minutes, 60)
        self.assertEqual(response.price_minor_units, 8_500)

    def test_service_contract_omits_internal_fields(self) -> None:
        """Keep buffers, revisions, priorities, and membership IDs private."""
        fields = {
            "membership_id",
            "revision",
            "setup_buffer_minutes",
            "cleanup_buffer_minutes",
            "slot_step_minutes",
            "priority",
            "auto_eligible",
        }
        schema = definition.BACKEND_APP_DEFINITION
        self.assertEqual(schema.app_id, "booking_service")
        self.assertTrue(fields.isdisjoint(DiscoveryServiceResponse.model_fields))


class BookingDiscoveryRouteTests(unittest.TestCase):
    """Retain authentication metadata and service-root-relative route names."""

    def test_discovery_routes_are_versioned_without_api_prefix(self) -> None:
        """Register list, detail, and tenant-admin preview endpoints exactly."""
        routes: dict[str, set[str]] = {}
        for registration in definition.BACKEND_APP_DEFINITION.route_registrations:
            for route in registration.router.routes:
                routes.setdefault(route.path, set()).update(route.methods or set())
        self.assertEqual(routes["/v1/discovery/organizations"], {"GET"})
        self.assertEqual(
            routes["/v1/discovery/organizations/{organization_id}"],
            {"GET"},
        )
        self.assertEqual(
            routes["/v1/organizations/{organization_id}/discovery-preview"],
            {"GET"},
        )
        self.assertTrue(all(not path.startswith("/api") for path in routes))

    def test_discovery_openapi_requires_bearer_authentication(self) -> None:
        """Keep authenticated discovery explicit in generated OpenAPI metadata."""
        requirements = definition.BACKEND_APP_DEFINITION.openapi_route_security
        discovery = next(
            item for item in requirements if item.path_prefix == "/v1/discovery"
        )
        self.assertEqual(discovery.requirement, {"BookingBearer": []})
        self.assertEqual(discovery.methods, ("get",))


if __name__ == "__main__":
    unittest.main()
