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
    / "felix_api_contract.v2.json"
)


class FelixApiReleaseContractTests(unittest.TestCase):
    """Verifies the API identity, provider, routes, and secret-file boundary."""

    def setUp(self) -> None:
        """Load a fresh contract object for each test."""

        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_runtime_identity_is_explicitly_felix(self) -> None:
        """Build and runtime selectors both target Felix production."""

        self.assertEqual(self.contract["schemaVersion"], 2)
        self.assertEqual(self.contract["owner"], "api")
        self.assertEqual(self.contract["appId"], "felix")
        identity = self.contract["fixedRuntimeIdentity"]
        self.assertEqual(identity["APP_PROFILE"], "felix")
        self.assertEqual(identity["BACKEND_APP_ID"], "felix")
        self.assertEqual(identity["APP_ENVIRONMENT"], "production")
        self.assertEqual(identity["AUTH_PROVIDER"], "keycloak")
        self.assertEqual(identity["DB_TYPE"], "postgresql")

    def test_keycloak_contract_uses_relationships_not_frozen_identity(self) -> None:
        """Permit coherent deployment identity without weakening boundaries."""

        keycloak = self.contract["keycloak"]
        relationships = keycloak["relationships"]
        serialized = json.dumps(keycloak)

        self.assertIn("KEYCLOAK_REALM", keycloak["requiredFields"])
        self.assertIn("KEYCLOAK_CLIENT_ID", keycloak["requiredFields"])
        self.assertEqual(
            relationships["issuer"],
            "{KEYCLOAK_SERVER_URL}/realms/{KEYCLOAK_REALM}",
        )
        self.assertIs(relationships["frontendAndBackendClientIdsDiffer"], True)
        self.assertIs(relationships["audienceDiffersFromFrontendClientId"], True)
        self.assertIs(keycloak["constraints"]["audienceEnforcement"], True)
        self.assertNotIn("keycloak.fe-wi.com", serialized)
        self.assertNotIn("felix-new-frontend", serialized)

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

        self.assertEqual(
            secret_fields,
            ["DB_PASSWORD_FILE", "KEYCLOAK_ADMIN_CLIENT_SECRET_FILE"],
        )
        self.assertNotIn("client_secret=", serialized)
        self.assertNotIn("password=", serialized)


if __name__ == "__main__":
    unittest.main()
