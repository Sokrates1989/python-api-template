"""Unit tests for persistent Booking Service development fixture seeding."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import booking_service_local_seed as local_seed  # noqa: E402


class BookingServiceLocalSeedTests(unittest.TestCase):
    """Keep local tenant seeding bounded, role-safe, and credential-safe."""

    def _write_manifest(
        self,
        directory: str,
        mutate: Any | None = None,
    ) -> Path:
        """Write one disposable reconciler-compatible subject manifest.

        Args:
            directory: Temporary destination directory.
            mutate: Optional callable that changes the decoded manifest.

        Returns:
            Path to the written JSON manifest.

        Side Effects:
            Writes one temporary JSON file.
        """

        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "kind": "local-keycloak-demo-user-subjects",
            "contractFingerprint": "a" * 64,
            "targetOrigin": local_seed.KEYCLOAK_ORIGIN,
            "realm": local_seed.KEYCLOAK_REALM,
            "users": [
                {
                    "username": username,
                    "subject": f"subject-{role}",
                    "roles": [role],
                }
                for _, username, _, role in local_seed.DEFAULT_IDENTITY_SPECS
            ],
        }
        if mutate is not None:
            mutate(payload)
        path = Path(directory) / "subjects.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_collect_subjects_requires_exact_manifest_identity_and_roles(self) -> None:
        """Project all four opaque subjects from reconciler output only."""

        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(directory)
            subjects = local_seed.collect_subjects(path)

        self.assertEqual(subjects["platform_admin"], "subject-platform_admin")
        self.assertEqual(subjects["customer"], "subject-customer")

    def test_collect_subjects_rejects_wrong_realm_and_duplicate_subjects(self) -> None:
        """Fail closed for foreign manifests and ambiguous Keycloak subjects."""

        with tempfile.TemporaryDirectory() as directory:
            foreign = self._write_manifest(
                directory,
                lambda payload: payload.__setitem__("realm", "foreign-realm"),
            )
            with self.assertRaises(local_seed.BookingServiceLocalSeedError):
                local_seed.collect_subjects(foreign)

            duplicate = self._write_manifest(
                directory,
                lambda payload: payload["users"][1].__setitem__(
                    "subject",
                    payload["users"][0]["subject"],
                ),
            )
            with self.assertRaises(local_seed.BookingServiceLocalSeedError):
                local_seed.collect_subjects(duplicate)

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

    def test_runner_never_constructs_a_credential_environment(self) -> None:
        """Execute Compose without reading or forwarding demo credentials."""

        runner = Mock()
        environment_file = Mock()
        environment_file.is_file.return_value = True
        with patch.object(local_seed, "COMPOSE_ENV_FILE", environment_file):
            local_seed.run_seed_command(
                ("docker", "compose", "ps"),
                runner=runner,
            )

        self.assertNotIn("env", runner.call_args.kwargs)
        self.assertNotIn("password", " ".join(runner.call_args.args[0]).lower())


if __name__ == "__main__":
    unittest.main()
