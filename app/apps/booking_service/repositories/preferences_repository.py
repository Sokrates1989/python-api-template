"""Subject-scoped SQLAlchemy access for Booking user preferences."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.preferences import DEFAULT_USER_LOCALE
from apps.booking_service.models.preferences import BookingUserPreferences


class PreferencesRepository:
    """Persist preferences inside one caller-owned async transaction.

    Attributes:
        session: Caller-owned SQLAlchemy session defining the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to a caller-owned transaction.

        Args:
            session: Async SQLAlchemy session used by every operation.

        Returns:
            None: The repository retains the session without committing it.
        """

        self._session = session

    async def ensure_defaults(self, subject_id: str) -> BookingUserPreferences:
        """Load or stage default preferences for one verified subject.

        Args:
            subject_id: Immutable verified identity-provider subject.

        Returns:
            Existing or newly staged preference row.
        """

        preferences = await self._session.get(BookingUserPreferences, subject_id)
        if preferences is None:
            preferences = BookingUserPreferences(
                subject_id=subject_id,
                preferred_locale=DEFAULT_USER_LOCALE,
                revision=1,
            )
            self._session.add(preferences)
            await self._session.flush()
        return preferences

    async def get_for_update(
        self,
        subject_id: str,
    ) -> BookingUserPreferences | None:
        """Lock one subject's preferences for optimistic replacement.

        Args:
            subject_id: Immutable verified identity-provider subject.

        Returns:
            Locked preference row, or ``None`` before defaults are created.
        """

        result = await self._session.execute(
            select(BookingUserPreferences)
            .where(BookingUserPreferences.subject_id == subject_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()
