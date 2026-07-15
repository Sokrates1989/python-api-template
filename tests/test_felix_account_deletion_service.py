"""Unit tests for Felix account erasure ordering and provider behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from apps.felix.services.account_deletion_service import (
    FelixAccountDeletionError,
    FelixAccountDeletionService,
    KeycloakIdentityDeletionGateway,
)


class _RecordingIdentityGateway:
    """Record support validation and deletion ordering for service tests."""

    def __init__(self, events: list[str], *, fail_delete: bool = False) -> None:
        """Create a recording identity gateway.

        Args:
            events (list[str]): Shared ordered event sink.
            fail_delete (bool): Whether identity deletion should fail.

        Returns:
            None.
        """
        self._events = events
        self._fail_delete = fail_delete

    def validate_support(self) -> None:
        """Record preflight validation.

        Returns:
            None.
        """
        self._events.append("validate")

    async def delete_identity(self, user_id: str) -> None:
        """Record identity deletion and optionally fail.

        Args:
            user_id (str): Authenticated identity under test.

        Returns:
            None.

        Raises:
            FelixAccountDeletionError: When configured to simulate failure.
        """
        self._events.append(f"identity:{user_id}")
        if self._fail_delete:
            raise FelixAccountDeletionError(
                "identity_deletion_failed",
                "simulated identity failure",
            )


class _RecordingDeletionService(FelixAccountDeletionService):
    """Replace database mutation with an ordered test event."""

    def __init__(self, events: list[str], identity_gateway: object) -> None:
        """Create the recording service.

        Args:
            events (list[str]): Shared ordered event sink.
            identity_gateway (object): Recording identity gateway.

        Returns:
            None.
        """
        self._events = events
        super().__init__(
            database_handler=object(),
            identity_gateway=identity_gateway,
        )

    async def _delete_backend_data(self, user_id: str) -> None:
        """Record backend deletion without touching a database.

        Args:
            user_id (str): Authenticated identity under test.

        Returns:
            None.
        """
        self._events.append(f"backend:{user_id}")


class _FakeResponse:
    """Minimal requests response used by Keycloak gateway tests."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        """Create a fake response.

        Args:
            status_code (int): HTTP status exposed to the gateway.
            payload (dict | None): Optional JSON payload.

        Returns:
            None.
        """
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        """Return the configured JSON payload.

        Returns:
            dict: Response JSON data.
        """
        return self._payload


class _FakeRequestSession:
    """Record confidential Keycloak token and delete calls."""

    def __init__(self, delete_status: int = 204) -> None:
        """Create a fake request session.

        Args:
            delete_status (int): Status returned by the DELETE request.

        Returns:
            None.
        """
        self.delete_status = delete_status
        self.deleted_urls: list[str] = []

    def post(self, url: str, *, data: dict, timeout: int) -> _FakeResponse:
        """Return a service-account access token.

        Args:
            url (str): Token endpoint URL.
            data (dict): Client-credentials form body.
            timeout (int): Request timeout in seconds.

        Returns:
            _FakeResponse: Successful token response.
        """
        del url, data, timeout
        return _FakeResponse(200, {"access_token": "test-token"})

    def delete(
        self,
        url: str,
        *,
        headers: dict,
        timeout: int,
    ) -> _FakeResponse:
        """Record and return the configured deletion response.

        Args:
            url (str): Keycloak admin user URL.
            headers (dict): Authorization header mapping.
            timeout (int): Request timeout in seconds.

        Returns:
            _FakeResponse: Configured deletion response.
        """
        del headers, timeout
        self.deleted_urls.append(url)
        return _FakeResponse(self.delete_status)


def _keycloak_settings() -> SimpleNamespace:
    """Build complete Keycloak settings for gateway tests.

    Returns:
        SimpleNamespace: Settings-shaped Keycloak configuration.
    """
    return SimpleNamespace(
        KEYCLOAK_INTERNAL_URL="http://keycloak:8080",
        KEYCLOAK_SERVER_URL="http://localhost:9090",
        KEYCLOAK_REALM="felix",
        KEYCLOAK_CLIENT_ID="felix-backend",
        KEYCLOAK_CLIENT_SECRET="secret",
        get_auth_provider=lambda: "keycloak",
    )


class FelixAccountDeletionServiceTests(unittest.TestCase):
    """Verify destructive ordering, retry state, and Keycloak idempotency."""

    def test_backend_is_deleted_before_identity(self) -> None:
        """Backend purge must precede identity removal after preflight.

        Returns:
            None.
        """
        events: list[str] = []
        gateway = _RecordingIdentityGateway(events)
        service = _RecordingDeletionService(events, gateway)

        result = asyncio.run(service.delete_account(" user-1 "))

        self.assertEqual(events, ["validate", "backend:user-1", "identity:user-1"])
        self.assertTrue(result.backend_data_deleted)
        self.assertTrue(result.identity_deleted)

    def test_identity_failure_reports_completed_backend_purge(self) -> None:
        """Identity failure must stay retryable without false completion.

        Returns:
            None.
        """
        events: list[str] = []
        gateway = _RecordingIdentityGateway(events, fail_delete=True)
        service = _RecordingDeletionService(events, gateway)

        with self.assertRaises(FelixAccountDeletionError) as context:
            asyncio.run(service.delete_account("user-1"))

        self.assertTrue(context.exception.backend_data_deleted)
        self.assertEqual(context.exception.code, "identity_deletion_failed")

    def test_keycloak_missing_user_is_idempotent_success(self) -> None:
        """A retried Keycloak 404 must count as already deleted.

        Returns:
            None.
        """
        request_session = _FakeRequestSession(delete_status=404)
        gateway = KeycloakIdentityDeletionGateway(
            _keycloak_settings(),
            request_session=request_session,
        )

        asyncio.run(gateway.delete_identity("user/with space"))

        self.assertEqual(len(request_session.deleted_urls), 1)
        self.assertTrue(request_session.deleted_urls[0].endswith("user%2Fwith%20space"))

    def test_missing_keycloak_secret_fails_before_mutation(self) -> None:
        """A missing confidential secret must fail closed during preflight.

        Returns:
            None.
        """
        runtime_settings = _keycloak_settings()
        runtime_settings.KEYCLOAK_CLIENT_SECRET = ""
        gateway = KeycloakIdentityDeletionGateway(runtime_settings)

        with self.assertRaises(FelixAccountDeletionError) as context:
            gateway.validate_support()

        self.assertEqual(context.exception.code, "identity_provider_not_configured")


if __name__ == "__main__":
    unittest.main()
