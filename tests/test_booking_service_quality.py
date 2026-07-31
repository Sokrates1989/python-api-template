"""Unit tests for the disposable Booking Service quality orchestrator."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from booking_quality.config import (  # noqa: E402
    BookingServiceQualityError,
    build_quality_runtime,
)
from booking_quality.orchestration import (  # noqa: E402
    API_PYTHON,
    compose_command,
    print_summary,
)
from booking_quality.runtime_checks import wait_for_health  # noqa: E402


class BookingServiceQualityTests(unittest.TestCase):
    """Prove environment ownership, command bounds, and safe summaries."""

    def test_automated_runtime_generates_all_private_values_in_memory(self) -> None:
        """Create four roles and infrastructure secrets without input files."""
        runtime = build_quality_runtime(
            source_environment={},
        )
        self.assertEqual(
            [identity.role for identity in runtime.identities],
            ["platform_admin", "organization_admin", "worker", "customer"],
        )
        self.assertEqual(runtime.api_origin, "http://localhost:8084")
        self.assertEqual(
            runtime.issuer_url,
            "http://localhost:9094/realms/booking-service-example",
        )
        self.assertEqual(len(runtime.sensitive_values), 9)
        self.assertTrue(all(runtime.sensitive_values))

    def test_interactive_runtime_requires_environment_owned_passwords(self) -> None:
        """Reject interactive startup before Docker when a password is absent."""
        with self.assertRaises(BookingServiceQualityError):
            build_quality_runtime(
                require_explicit_passwords=True,
                source_environment={},
            )

    def test_summary_and_compose_vector_never_contain_secret_values(self) -> None:
        """Keep credentials out of public output and process arguments."""
        environment = {
            "BOOKING_QUALITY_PLATFORM_ADMIN_PASSWORD": "PlatformSecret123!",
            "BOOKING_QUALITY_ORGANIZATION_ADMIN_PASSWORD": "OrgSecret123!",
            "BOOKING_QUALITY_WORKER_PASSWORD": "WorkerSecret123!",
            "BOOKING_QUALITY_CUSTOMER_PASSWORD": "CustomerSecret123!",
        }
        runtime = build_quality_runtime(
            require_explicit_passwords=True,
            source_environment=environment,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            print_summary(runtime, "verified")
        rendered = output.getvalue()
        command = " ".join(
            compose_command(runtime, "up", "--detach")
        )
        for secret in runtime.sensitive_values:
            self.assertNotIn(secret, rendered)
            self.assertNotIn(secret, command)
        self.assertIn('"status": "verified"', rendered)
        self.assertIn("--project-name booking-service-quality", command)
        self.assertEqual(API_PYTHON, "/app/.venv/bin/python")

    def test_public_port_and_project_inputs_fail_closed(self) -> None:
        """Reject invalid public orchestration values before Compose starts."""
        invalid_environments = (
            {"BOOKING_QUALITY_API_PORT": "0"},
            {"BOOKING_QUALITY_KEYCLOAK_PORT": "not-a-port"},
            {"BOOKING_QUALITY_REDIS_PORT": "70000"},
            {"BOOKING_QUALITY_PROJECT_NAME": "Unsafe Project"},
            {"BOOKING_QUALITY_CUSTOMER_PASSWORD": "short"},
            {"BOOKING_QUALITY_DB_PASSWORD": "unsafe:database:secret"},
        )
        for environment in invalid_environments:
            with self.subTest(environment=environment):
                with self.assertRaises(BookingServiceQualityError):
                    build_quality_runtime(
                        source_environment=environment,
                    )

    def test_health_wait_retries_transient_disconnected_socket(self) -> None:
        """Treat the observed pre-Uvicorn disconnect as retryable startup state."""
        runtime = build_quality_runtime(source_environment={})
        expected_health = {"status": "OK"}
        with (
            patch(
                "booking_quality.runtime_checks.read_json",
                side_effect=(ConnectionResetError(), expected_health),
            ),
            patch("booking_quality.runtime_checks.time.sleep"),
        ):
            observed = wait_for_health(runtime, timeout_seconds=1.0)
        self.assertEqual(observed, expected_health)


if __name__ == "__main__":
    unittest.main()
