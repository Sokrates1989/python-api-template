"""Standard-library tests for relational Felix production identity policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPOSITORY_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from api.production_contract_validation import (  # noqa: E402
    collect_production_cors_errors,
    collect_production_keycloak_errors,
)


class FelixProductionContractValidationTests(unittest.TestCase):
    """Verify safe non-default identity and strict relational failures."""

    def _identity(self) -> dict[str, object]:
        """Return one coherent non-default Keycloak production identity.

        Returns:
            Keyword arguments accepted by the relational validator.
        """

        return {
            "server_url": "https://identity.release-smoke.example.com",
            "internal_url": "",
            "realm": "release-smoke-realm",
            "frontend_client_id": "release-smoke-frontend",
            "issuer_url": (
                "https://identity.release-smoke.example.com/"
                "realms/release-smoke-realm"
            ),
            "jwks_url": (
                "https://identity.release-smoke.example.com/"
                "realms/release-smoke-realm/protocol/openid-connect/certs"
            ),
            "enforce_audience": True,
            "audience": "release-smoke-api",
            "backend_client_id": "release-smoke-backend",
            "backend_secret_file": "/run/secrets/release_smoke_keycloak",
        }

    def test_non_default_coherent_identity_is_accepted(self) -> None:
        """Accept safe operator-selected values without frozen comparisons."""

        self.assertEqual(
            collect_production_keycloak_errors(**self._identity()),
            [],
        )
        self.assertEqual(
            collect_production_cors_errors(
                [
                    "https://web.release-smoke.example.com",
                    "https://admin.release-smoke.example.com",
                ]
            ),
            [],
        )

    def test_mismatched_issuer_and_jwks_fail(self) -> None:
        """Bind both token endpoints to the selected server and realm."""

        identity = self._identity()
        identity["issuer_url"] = (
            "https://identity.release-smoke.example.com/realms/wrong"
        )
        identity["jwks_url"] = (
            "https://identity.release-smoke.example.com/realms/wrong/"
            "protocol/openid-connect/certs"
        )

        errors = collect_production_keycloak_errors(**identity)

        self.assertTrue(any("ISSUER_URL must match" in error for error in errors))
        self.assertTrue(any("JWKS_URL must match" in error for error in errors))

    def test_unsafe_urls_and_client_ids_fail(self) -> None:
        """Reject local identity hosts, wildcard CORS, and malformed clients."""

        identity = self._identity()
        identity["server_url"] = "https://localhost"
        identity["frontend_client_id"] = "Unsafe Client"

        keycloak_errors = collect_production_keycloak_errors(**identity)
        cors_errors = collect_production_cors_errors(["https://*.example.com"])

        self.assertTrue(
            any("public, non-local hostname" in error for error in keycloak_errors)
        )
        self.assertTrue(
            any("lowercase safe identifier" in error for error in keycloak_errors)
        )
        self.assertTrue(
            any("wildcards or placeholders" in error for error in cors_errors)
        )

    def test_malformed_and_non_exact_endpoint_urls_fail_cleanly(self) -> None:
        """Reject malformed URLs and trailing-slash endpoint drift."""

        malformed = self._identity()
        malformed["server_url"] = "https://[invalid"
        malformed_errors = collect_production_keycloak_errors(**malformed)

        non_exact = self._identity()
        non_exact["issuer_url"] = f"{non_exact['issuer_url']}/"
        non_exact["jwks_url"] = f"{non_exact['jwks_url']}/"
        non_exact_errors = collect_production_keycloak_errors(**non_exact)

        self.assertTrue(
            any("structurally valid URL" in error for error in malformed_errors)
        )
        self.assertTrue(
            any("ISSUER_URL must match" in error for error in non_exact_errors)
        )
        self.assertTrue(
            any("JWKS_URL must match" in error for error in non_exact_errors)
        )

    def test_audience_enforcement_and_client_separation_remain_strict(self) -> None:
        """Reject disabled audience checks and public/backend identity overlap."""

        identity = self._identity()
        identity["enforce_audience"] = False
        identity["audience"] = "release-smoke-frontend"
        identity["backend_client_id"] = "release-smoke-frontend"

        errors = collect_production_keycloak_errors(**identity)

        self.assertIn("KEYCLOAK_ENFORCE_AUDIENCE must be enabled", errors)
        self.assertIn("Keycloak frontend and backend client IDs must differ", errors)
        self.assertIn(
            "KEYCLOAK_AUDIENCE must differ from the frontend client ID",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
