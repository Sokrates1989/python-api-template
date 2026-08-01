"""Security tests for credential-free Keycloak bootstrap diagnostics."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
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
import keycloak_admin_operations  # noqa: E402


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

    def test_frontend_client_adds_only_its_access_token_audience(self) -> None:
        """Configure audience verification without a frontend client secret."""
        frontend, _ = keycloak_bootstrap.build_client_payloads(
            "keycloak",
            "booking-service-backend",
            "http://localhost:3000",
            "http://localhost:8084",
        )
        mapper = frontend["protocolMappers"][0]
        self.assertEqual(mapper["protocolMapper"], "oidc-audience-mapper")
        self.assertEqual(mapper["config"]["included.client.audience"], "keycloak")
        self.assertEqual(mapper["config"]["access.token.claim"], "true")
        self.assertTrue(frontend["publicClient"])
        self.assertNotIn("secret", frontend)

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
            client_role=["customer"],
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
            patch.object(keycloak_bootstrap, "ensure_client_roles"),
            patch.object(
                keycloak_bootstrap,
                "get_client_secret",
                return_value=client_secret,
            ),
            patch.object(keycloak_bootstrap, "ensure_user", return_value="user-uuid"),
            patch.object(keycloak_bootstrap, "set_user_password"),
            patch.object(keycloak_bootstrap, "assign_realm_roles"),
            patch.object(keycloak_bootstrap, "assign_client_roles"),
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

    def test_disposable_secret_file_is_written_without_console_output(self) -> None:
        """Share a generated proof secret only through the selected volume file."""
        secret = "NeverPrintGeneratedClientSecret!"
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "identity-admin-client"
            with contextlib.redirect_stdout(output):
                keycloak_bootstrap.write_disposable_client_secret(
                    secret, str(destination)
                )
            self.assertEqual(destination.read_text(encoding="utf-8"), secret)
        self.assertNotIn(secret, output.getvalue())

    def test_service_account_receives_only_selected_client_roles(self) -> None:
        """Map the exact realm-management subset to the backend service user."""
        roles = ["manage-users", "query-clients", "view-clients", "view-users"]
        with (
            patch.object(
                keycloak_admin_operations,
                "resolve_client_id",
                return_value="realm-management-uuid",
            ),
            patch.object(
                keycloak_admin_operations,
                "resolve_service_account_user_id",
                return_value="service-user-uuid",
            ),
            patch.object(
                keycloak_admin_operations,
                "assign_client_roles",
            ) as assign,
        ):
            keycloak_admin_operations.assign_service_account_client_roles(
                "http://keycloak:8080",
                "bootstrap-token",
                "booking-service-example",
                "backend-client-uuid",
                "realm-management",
                roles,
            )
        assign.assert_called_once_with(
            "http://keycloak:8080",
            "bootstrap-token",
            "booking-service-example",
            "realm-management-uuid",
            "service-user-uuid",
            roles,
        )


if __name__ == "__main__":
    unittest.main()
