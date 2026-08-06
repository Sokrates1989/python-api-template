"""Transactional service for authenticated Booking user preferences.

The service authorizes solely through the verified subject and app-owned
subject lifecycle. It never reads or writes Keycloak profile attributes.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.tenancy import SubjectStatus
from apps.booking_service.models.preferences import BookingUserPreferences
from apps.booking_service.repositories.preferences_repository import (
    PreferencesRepository,
)
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.schemas.preferences import (
    UserPreferencesResponse,
    UserPreferencesUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned asynchronous database session."""


class BookingPreferencesService:
    """Read and replace the verified subject's account preferences."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        """Configure the service with an optional session factory.

        Args:
            session_factory: Injectable async session constructor. Runtime
                resolves the selected SQL handler when omitted.

        Returns:
            None: Only the optional factory is retained.
        """

        self._session_factory = session_factory

    def _sessions(self) -> SessionFactory:
        """Resolve the injected or initialized runtime session factory.

        Returns:
            Callable producing caller-owned async SQLAlchemy sessions.

        Raises:
            RuntimeError: When database startup has not completed.
        """

        if self._session_factory is not None:
            return self._session_factory
        handler = get_database_handler()
        return handler.AsyncSessionLocal  # type: ignore[attr-defined]

    async def read_preferences(
        self,
        principal: BookingPrincipal,
    ) -> UserPreferencesResponse:
        """Read or initialize preferences for one active verified subject.

        Args:
            principal: Verified request-scoped Booking principal.

        Returns:
            Current safe preference projection.

        Raises:
            TenancyError: With 403 when app-owned account access is inactive.
        """

        async with self._sessions()() as session:
            subject = await TenancyRepository(session).ensure_subject(
                principal.subject_id
            )
            self._require_active_subject(subject.status)
            preferences = await PreferencesRepository(session).ensure_defaults(
                principal.subject_id
            )
            response = self._response(preferences)
            await session.commit()
        return response

    async def update_preferences(
        self,
        principal: BookingPrincipal,
        request: UserPreferencesUpdateRequest,
    ) -> UserPreferencesResponse:
        """Replace preferences through subject scope and optimistic revision.

        Args:
            principal: Verified request-scoped Booking principal.
            request: Complete validated replacement and observed revision.

        Returns:
            Updated safe preference projection.

        Raises:
            TenancyError: With 403 for inactive access or retryable 409 for a
                stale preference revision.
        """

        async with self._sessions()() as session:
            subject = await TenancyRepository(session).ensure_subject(
                principal.subject_id
            )
            self._require_active_subject(subject.status)
            repository = PreferencesRepository(session)
            preferences = await repository.get_for_update(principal.subject_id)
            if preferences is None:
                preferences = await repository.ensure_defaults(principal.subject_id)
            if preferences.revision != request.expected_revision:
                raise TenancyError(
                    409,
                    "user_preferences_revision_conflict",
                    "Account preferences are stale",
                    True,
                )
            preferences.preferred_locale = request.preferred_locale
            preferences.revision += 1
            await session.flush()
            response = self._response(preferences)
            await session.commit()
        return response

    @staticmethod
    def _require_active_subject(status: str) -> None:
        """Reject preferences access for an inactive app-owned account.

        Args:
            status: Persisted Booking subject lifecycle value.

        Returns:
            None: Successful return means account access is active.

        Raises:
            TenancyError: With safe 403 semantics for inactive accounts.
        """

        if status != SubjectStatus.ACTIVE.value:
            raise TenancyError(
                403,
                "subject_inactive",
                "Booking access is not active",
            )

    @staticmethod
    def _response(preferences: BookingUserPreferences) -> UserPreferencesResponse:
        """Project one ORM row into the public preference contract.

        Args:
            preferences: Persisted subject-scoped preference row.

        Returns:
            Safe locale and optimistic revision response.
        """

        return UserPreferencesResponse(
            preferred_locale=preferences.preferred_locale,
            revision=preferences.revision,
        )
