"""Unit tests for persistent Booking Service development fixture seeding."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import booking_service_local_seed as local_seed  # noqa: E402


class BookingServiceLocalSeedTests(unittest.TestCase):
    """Keep local tenant seeding bounded, role-safe, and credential-safe."""

    def test_collect_subjects_requires_exact_issuer_audience_and_roles(self) -> None:
        """Project all four opaque subjects only from matching local claims."""

        tokens: dict[str, str] = {}
        for _, username, _, role in local_seed.DEFAULT_IDENTITY_SPECS:
            claims = {
                "aud": "keycloak",
                "iss": local_seed.KEYCLOAK_ISSUER,
                "resource_access": {"keycloak": {"roles": [role]}},
                "sub": f"subject-{role}",
            }
            payload = base64.urlsafe_b64encode(
                json.dumps(claims).encode("utf-8")
            ).rstrip(b"=").decode("ascii")
            tokens[username] = f"header.{payload}.signature"
        requester = Mock(side_effect=lambda username, _: tokens[username])

        subjects = local_seed.collect_subjects("local-password", requester=requester)

        self.assertEqual(subjects["platform_admin"], "subject-platform_admin")
        self.assertEqual(subjects["customer"], "subject-customer")
        self.assertEqual(requester.call_count, 4)

    def test_seed_command_is_fixed_and_contains_no_password(self) -> None:
        """Build only the persistent Compose target with opaque subjects."""

        subjects = {
            "platform_admin": "platform-subject",
            "organization_admin": "admin-subject",
            "worker": "worker-subject",
            "customer": "customer-subject",
        }

        command = local_seed.build_seed_command(subjects)

        self.assertEqual(command[:2], ("docker", "compose"))
        self.assertIn("booking-service-local", command)
        self.assertIn("apps.booking_service.quality.seed_tenancy", command)
        self.assertIn("--customer-organization-id", command)
        self.assertNotIn("password", " ".join(command).lower())
        self.assertNotIn("9094", command)

    def test_runner_removes_demo_password_from_compose_environment(self) -> None:
        """Never forward the interactive login credential to Docker Compose."""

        runner = Mock()
        environment_file = Mock()
        environment_file.is_file.return_value = True
        with patch.object(local_seed, "COMPOSE_ENV_FILE", environment_file):
            local_seed.run_seed_command(
                ("docker", "compose", "ps"),
                source_environment={
                    local_seed.DEMO_PASSWORD_ENV: "local-secret-value",
                    "SAFE_VALUE": "retained",
                },
                runner=runner,
            )

        child_environment = runner.call_args.kwargs["env"]
        self.assertNotIn(local_seed.DEMO_PASSWORD_ENV, child_environment)
        self.assertEqual(child_environment["SAFE_VALUE"], "retained")


if __name__ == "__main__":
    unittest.main()
