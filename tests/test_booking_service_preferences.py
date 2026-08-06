"""Contract tests for Booking Service user-owned locale preferences."""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from apps.booking_service import definition
from apps.booking_service.dependencies.identity import BookingPrincipal, BookingRole
from apps.booking_service.routes.preferences import (
    read_user_preferences,
    update_user_preferences,
)
from apps.booking_service.schemas.preferences import (
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
"""Repository root used for migration source contract checks."""


class _PreferencesServiceStub:
    """Provide deterministic route results without database I/O."""

    def __init__(
        self,
        response: UserPreferencesResponse | TenancyError,
    ) -> None:
        """Retain one successful response or safe service error.

        Args:
            response: Value returned or error raised by both stub operations.

        Returns:
            None: The fixture retains only the supplied result.
        """

        self._response = response

    async def read_preferences(
        self,
        principal: BookingPrincipal,
    ) -> UserPreferencesResponse:
        """Return the fixture result for an authenticated read.

        Args:
            principal: Verified principal accepted to mirror the real service.

        Returns:
            Configured preference response.

        Raises:
            TenancyError: Configured safe service failure.
        """

        del principal
        return self._result()

    async def update_preferences(
        self,
        principal: BookingPrincipal,
        request: UserPreferencesUpdateRequest,
    ) -> UserPreferencesResponse:
        """Return the fixture result for an authenticated replacement.

        Args:
            principal: Verified principal accepted to mirror the real service.
            request: Validated replacement accepted to mirror the real service.

        Returns:
            Configured preference response.

        Raises:
            TenancyError: Configured safe service failure.
        """

        del principal, request
        return self._result()

    def _result(self) -> UserPreferencesResponse:
        """Return or raise the retained result.

        Returns:
            Configured preference response.

        Raises:
            TenancyError: Configured safe service failure.
        """

        if isinstance(self._response, TenancyError):
            raise self._response
        return self._response


class BookingPreferencesContractTests(unittest.IsolatedAsyncioTestCase):
    """Prove preference validation, routing, and migration ownership."""

    def test_locale_is_normalized_and_allowlisted(self) -> None:
        """Accept generated locales and reject unsupported client state."""

        request = UserPreferencesUpdateRequest(
            expected_revision=1,
            preferred_locale=" EN ",
        )
        self.assertEqual(request.preferred_locale, "en")
        with self.assertRaises(ValidationError):
            UserPreferencesUpdateRequest(
                expected_revision=1,
                preferred_locale="fr",
            )

    async def test_routes_return_only_the_current_subject_preferences(self) -> None:
        """Keep read and replacement projections free of identity metadata."""

        principal = BookingPrincipal("subject-1", (BookingRole.CUSTOMER,))
        response = UserPreferencesResponse(preferred_locale="en", revision=2)
        service = _PreferencesServiceStub(response)
        observed_read = await read_user_preferences(
            principal,
            service,  # type: ignore[arg-type]
        )
        observed_update = await update_user_preferences(
            UserPreferencesUpdateRequest(
                expected_revision=1,
                preferred_locale="en",
            ),
            principal,
            service,  # type: ignore[arg-type]
        )
        self.assertEqual(observed_read, response)
        self.assertEqual(observed_update, response)
        self.assertEqual(
            response.model_dump(mode="json"),
            {"preferred_locale": "en", "revision": 2},
        )

    async def test_route_preserves_safe_revision_conflict(self) -> None:
        """Translate stale account state into a retryable HTTP 409."""

        principal = BookingPrincipal("subject-1", (BookingRole.CUSTOMER,))
        service = _PreferencesServiceStub(
            TenancyError(
                409,
                "user_preferences_revision_conflict",
                "Account preferences are stale",
                True,
            )
        )
        with self.assertRaises(HTTPException) as context:
            await update_user_preferences(
                UserPreferencesUpdateRequest(
                    expected_revision=1,
                    preferred_locale="en",
                ),
                principal,
                service,  # type: ignore[arg-type]
            )
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail["code"],
            "user_preferences_revision_conflict",
        )

    def test_definition_and_migration_own_the_preference_boundary(self) -> None:
        """Require exact bearer security and a subject-bound revision table."""

        requirement = definition.BACKEND_APP_DEFINITION.openapi_route_security[2]
        self.assertTrue(requirement.matches_path("/v1/me/preferences"))
        self.assertFalse(requirement.matches_path("/v1/me/preferences/private"))
        relative_path = (
            Path("apps")
            / "booking_service"
            / "migrations"
            / "versions"
            / "booking_service_007_user_preferences.py"
        )
        candidates = (
            REPOSITORY_ROOT / "app" / relative_path,
            REPOSITORY_ROOT / relative_path,
        )
        migration_path = next(path for path in candidates if path.is_file())
        migration = migration_path.read_text(encoding="utf-8")
        self.assertIn('down_revision = "booking_service_006"', migration)
        self.assertIn('"booking_subjects.subject_id"', migration)
        self.assertNotIn("/api/", migration)


if __name__ == "__main__":
    unittest.main()
