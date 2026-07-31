"""Security tests for credential-free Keycloak bootstrap diagnostics."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_ROOT = REPOSITORY_ROOT / "keycloak" / "bootstrap"
if str(BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_ROOT))
try:
    import requests as _requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = MagicMock()

import keycloak_bootstrap  # noqa: E402


class KeycloakBootstrapRedactionTests(unittest.TestCase):
    """Prove user passwords and client secrets never enter summaries/errors."""

    def test_invalid_user_spec_error_does_not_echo_password(self) -> None:
        """Report an indexed specification failure without reflecting input."""
        password = "NeverEchoThisPassword!"
        with self.assertRaises(keycloak_bootstrap.KeycloakBootstrapError) as context:
            keycloak_bootstrap.parse_user_specs([f"demo:{password}"])
        self.assertNotIn(password, str(context.exception))
        self.assertIn("#1", str(context.exception))

    def test_local_user_payload_completes_profile_without_credentials(self) -> None:
        """Seed a non-personal complete profile with no password field."""
        payload = keycloak_bootstrap.build_local_user_payload("booking-customer")
        self.assertEqual(payload["username"], "booking-customer")
        self.assertEqual(payload["requiredActions"], [])
        self.assertTrue(str(payload["email"]).endswith("@local.invalid"))
        self.assertNotIn("password", payload)

    def test_bootstrap_summary_contains_only_public_identity(self) -> None:
        """Run the orchestration seam and scan captured output for secrets."""
        user_password = "NeverEchoUserPassword!"
        client_secret = "NeverEchoClientSecret!"
        arguments = argparse.Namespace(
            base_url="http://keycloak:8080",
            admin_user="quality-admin",
            admin_password="NeverEchoAdminPassword!",
            realm="booking-service-example",
            frontend_client_id="keycloak",
            backend_client_id="booking-service-backend",
            frontend_root_url="http://localhost:3000",
            api_root_url="http://localhost:8084",
            role=["customer"],
            user=[f"booking-customer:{user_password}:customer"],
            assign_service_account_role=None,
        )
        output = io.StringIO()
        with (
            patch.object(keycloak_bootstrap, "get_admin_token", return_value="token"),
            patch.object(keycloak_bootstrap, "ensure_realm"),
            patch.object(keycloak_bootstrap, "ensure_roles"),
            patch.object(
                keycloak_bootstrap,
                "ensure_client",
                side_effect=("frontend-uuid", "backend-uuid"),
            ),
            patch.object(
                keycloak_bootstrap,
                "get_client_secret",
                return_value=client_secret,
            ),
            patch.object(keycloak_bootstrap, "ensure_user", return_value="user-uuid"),
            patch.object(keycloak_bootstrap, "set_user_password"),
            patch.object(keycloak_bootstrap, "assign_realm_roles"),
            contextlib.redirect_stdout(output),
        ):
            keycloak_bootstrap.run_bootstrap(arguments)

        rendered = output.getvalue()
        self.assertNotIn(user_password, rendered)
        self.assertNotIn(client_secret, rendered)
        self.assertNotIn(arguments.admin_password, rendered)
        self.assertNotIn("backend_client_secret\"", rendered)
        self.assertIn('"backend_client_secret_configured": true', rendered)
        self.assertIn('"username": "booking-customer"', rendered)
        self.assertIn('"roles": [', rendered)


if __name__ == "__main__":
    unittest.main()
