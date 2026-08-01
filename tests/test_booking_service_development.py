"""Verify the persistent Booking Service local-development Compose boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_ROOT = (
    REPOSITORY_ROOT / "app" / "apps" / "booking_service" / "development"
)


class BookingServiceDevelopmentTests(unittest.TestCase):
    """Keep persistent development on the shared localhost:9090 identity host."""

    def test_compose_reuses_keycloak_without_defining_an_identity_service(self) -> None:
        """Require API/database/cache only and the exact persistent issuer."""

        compose = yaml.safe_load(
            (DEVELOPMENT_ROOT / "compose.yml").read_text(encoding="utf-8")
        )
        services = compose["services"]
        self.assertEqual(set(services), {"api", "postgres", "redis"})

        environment = services["api"]["environment"]
        self.assertEqual(
            environment["KEYCLOAK_ISSUER_URL"],
            "http://localhost:9090/realms/booking-service-example",
        )
        self.assertEqual(
            environment["KEYCLOAK_INTERNAL_URL"],
            "http://host.docker.internal:9090",
        )
        self.assertEqual(environment["KEYCLOAK_CLIENT_ID"], "keycloak")
        self.assertNotIn("9094", (DEVELOPMENT_ROOT / "compose.yml").read_text())

    def test_local_ports_and_private_inputs_are_fail_closed(self) -> None:
        """Require loopback bindings and environment-owned secret inputs."""

        source = (DEVELOPMENT_ROOT / "compose.yml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:${BOOKING_LOCAL_API_PORT:-8084}:8000"', source)
        self.assertIn("${BOOKING_LOCAL_DB_PASSWORD:?", source)
        self.assertIn("${BOOKING_LOCAL_BACKEND_SECRET_PATH:?", source)
        self.assertNotIn("/api/", source)

        example = (DEVELOPMENT_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("replace-with-local-only", example)
        self.assertNotIn("BookingLocalOnly", example)


if __name__ == "__main__":
    unittest.main()
