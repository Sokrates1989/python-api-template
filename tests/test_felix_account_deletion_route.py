"""Unit tests for Felix self-service account deletion route mapping.

The tests call the route function directly with a verified-subject stand-in.
They verify stable success and partial-failure envelopes without starting an
HTTP server or touching a real identity provider.
"""

from __future__ import annotations

import asyncio
import unittest

from fastapi import HTTPException

from apps.felix.routes.account import delete_current_account
from apps.felix.services.account_deletion_service import (
    FelixAccountDeletionError,
    FelixAccountDeletionResult,
)


class _RouteDeletionService:
    """Return or raise one deterministic deletion result for route tests."""

    def __init__(
        self,
        *,
        result: FelixAccountDeletionResult | None = None,
        error: FelixAccountDeletionError | None = None,
    ) -> None:
        """Create a deterministic route service.

        Args:
            result (FelixAccountDeletionResult | None): Successful result.
            error (FelixAccountDeletionError | None): Classified failure.

        Returns:
            None.
        """
        self._result = result
        self._error = error
        self.received_user_id: str | None = None

    async def delete_account(self, user_id: str) -> FelixAccountDeletionResult:
        """Record the verified subject and return the configured behavior.

        Args:
            user_id (str): Verified bearer-token subject from the route.

        Returns:
            FelixAccountDeletionResult: Configured complete result.

        Raises:
            FelixAccountDeletionError: Configured classified failure.
            AssertionError: When neither a result nor error was configured.
        """
        self.received_user_id = user_id
        if self._error is not None:
            raise self._error
        if self._result is None:
            raise AssertionError("Route test service has no configured result.")
        return self._result


class FelixAccountDeletionRouteTests(unittest.TestCase):
    """Verify response contracts for complete and partial erasure."""

    def test_success_uses_only_verified_subject(self) -> None:
        """A successful response must reflect complete provider markers.

        Returns:
            None.
        """
        service = _RouteDeletionService(
            result=FelixAccountDeletionResult(
                backend_data_deleted=True,
                identity_deleted=True,
            )
        )

        response = asyncio.run(
            delete_current_account("verified-subject", service)
        )

        self.assertEqual(service.received_user_id, "verified-subject")
        self.assertTrue(response.data.backend_data_deleted)
        self.assertTrue(response.data.identity_deleted)

    def test_partial_identity_failure_returns_retryable_502(self) -> None:
        """Backend-complete failures must preserve retry guidance.

        Returns:
            None.
        """
        service = _RouteDeletionService(
            error=FelixAccountDeletionError(
                "identity_deletion_failed",
                "safe failure",
                backend_data_deleted=True,
            )
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(delete_current_account("verified-subject", service))

        self.assertEqual(context.exception.status_code, 502)
        self.assertTrue(context.exception.detail["backend_data_deleted"])
        self.assertEqual(
            context.exception.detail["code"],
            "identity_deletion_failed",
        )

    def test_missing_identity_configuration_fails_before_claiming_success(
        self,
    ) -> None:
        """Unsupported identity configuration must map to conflict.

        Returns:
            None.
        """
        service = _RouteDeletionService(
            error=FelixAccountDeletionError(
                "identity_provider_not_configured",
                "safe configuration failure",
            )
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(delete_current_account("verified-subject", service))

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail["code"],
            "identity_provider_not_configured",
        )


if __name__ == "__main__":
    unittest.main()
