"""
Tests for the API-owned Felix release-orchestration contract.

The test is standard-library-only so contract validation remains available even
when the full API dependency environment has not been materialized locally.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "release_contracts"
    / "felix_api_contract.v1.json"
)


class FelixApiReleaseContractTests(unittest.TestCase):
    """Verifies the API identity, provider, routes, and secret-file boundary."""

    def setUp(self) -> None:
        """Load a fresh contract object for each test."""

        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_runtime_identity_is_explicitly_felix(self) -> None:
        """Build and runtime selectors both target Felix production."""

        self.assertEqual(self.contract["schemaVersion"], 1)
        self.assertEqual(self.contract["owner"], "api")
        self.assertEqual(self.contract["appId"], "felix")
        self.assertEqual(self.contract["appProfile"], "felix")
        self.assertEqual(self.contract["backendAppId"], "felix")
        self.assertEqual(self.contract["environment"], "production")
        self.assertEqual(self.contract["authProvider"], "keycloak")

    def test_candidate_keycloak_identity_is_isolated(self) -> None:
        """The API expects the new realm/client rather than either legacy realm."""

        candidate = self.contract["candidate"]

        self.assertEqual(candidate["realm"], "felix-new")
        self.assertEqual(candidate["frontendClientId"], "felix-new-frontend")
        self.assertTrue(candidate["issuerUrl"].endswith("/realms/felix-new"))

    def test_api_service_routes_have_no_redundant_api_prefix(self) -> None:
        """No API-owned route uses the forbidden `/api` prefix."""

        routes = self.contract["routePrefixes"]

        self.assertTrue(routes)
        self.assertFalse(
            any(route == "/api" or route.startswith("/api/") for route in routes)
        )

    def test_secret_material_is_file_backed(self) -> None:
        """The contract names a secret-file setting without storing its value."""

        secret_fields = self.contract["requiredSecretFileFields"]
        serialized = json.dumps(self.contract).lower()

        self.assertEqual(secret_fields, ["KEYCLOAK_ADMIN_CLIENT_SECRET_FILE"])
        self.assertNotIn("client_secret=", serialized)
        self.assertNotIn("password=", serialized)


if __name__ == "__main__":
    unittest.main()
