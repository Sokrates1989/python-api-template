"""Tenant-scoped persistence operations for company settings and locations."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.company_settings import (
    DEFAULT_COMPANY_CURRENCY,
    DEFAULT_COMPANY_LOCALE,
    DEFAULT_COMPANY_TIMEZONE,
    WorkerSelectionMode,
)
from apps.booking_service.models.company_settings import (
    BookingCompanySettings,
    BookingLocation,
)
from apps.booking_service.schemas.company_settings import LocationFields


class CompanySettingsRepository:
    """Provide organization-bound persistence within one caller transaction.

    Attributes:
        session: Caller-owned asynchronous SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository without taking commit ownership.

        Args:
            session: Transaction session used by every repository operation.

        Returns:
            None: The repository retains the session reference.
        """
        self._session = session

    async def ensure_defaults(
        self,
        organization_id: str,
        public_name: str,
    ) -> tuple[BookingCompanySettings, BookingLocation]:
        """Ensure one valid settings row and at least one active location.

        Args:
            organization_id: Tenant receiving neutral initial configuration.
            public_name: Tenant display name used for the initial public profile.

        Returns:
            tuple[BookingCompanySettings, BookingLocation]: Persisted settings
            and the existing or newly staged first active location.

        Side Effects:
            Stages missing defaults and flushes them in the caller transaction.
        """
        settings = await self.get_settings(organization_id)
        if settings is None:
            settings = self._default_settings(organization_id, public_name)
            self._session.add(settings)
            await self._session.flush()
        locations = await self.list_active_locations(organization_id)
        if locations:
            return settings, locations[0]
        location = self._default_location(organization_id)
        self._session.add(location)
        await self._session.flush()
        return settings, location

    async def get_settings(
        self,
        organization_id: str,
    ) -> BookingCompanySettings | None:
        """Load one settings row by its tenant primary key.

        Args:
            organization_id: Exact tenant identifier.

        Returns:
            BookingCompanySettings | None: Matching row or ``None``.
        """
        return await self._session.get(BookingCompanySettings, organization_id)

    async def get_settings_for_update(
        self,
        organization_id: str,
    ) -> BookingCompanySettings | None:
        """Lock one tenant settings row for optimistic replacement.

        Args:
            organization_id: Exact tenant identifier.

        Returns:
            BookingCompanySettings | None: Locked row or ``None``.
        """
        result = await self._session.execute(
            select(BookingCompanySettings)
            .where(BookingCompanySettings.organization_id == organization_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_active_locations(
        self,
        organization_id: str,
    ) -> tuple[BookingLocation, ...]:
        """List only active locations through a mandatory tenant predicate.

        Args:
            organization_id: Tenant owning every returned location.

        Returns:
            tuple[BookingLocation, ...]: Stable name/identifier ordered rows.
        """
        result = await self._session.execute(
            select(BookingLocation)
            .where(
                BookingLocation.organization_id == organization_id,
                BookingLocation.status == "active",
            )
            .order_by(BookingLocation.display_name, BookingLocation.id)
        )
        return tuple(result.scalars().all())

    async def create_location(
        self,
        organization_id: str,
        fields: LocationFields,
    ) -> BookingLocation:
        """Stage one active location inside an explicit tenant scope.

        Args:
            organization_id: Tenant owning the new location.
            fields: Fully validated location fields.

        Returns:
            BookingLocation: Newly staged active row.
        """
        location = BookingLocation(
            id=str(uuid4()),
            organization_id=organization_id,
            status="active",
            revision=1,
            **fields.model_dump(mode="python"),
        )
        self._session.add(location)
        await self._session.flush()
        return location

    async def get_location_for_update(
        self,
        organization_id: str,
        location_id: str,
    ) -> BookingLocation | None:
        """Lock one location using both tenant and resource predicates.

        Args:
            organization_id: Tenant that must own the resource.
            location_id: Exact location identifier within the tenant.

        Returns:
            BookingLocation | None: Locked scoped row or ``None``.
        """
        result = await self._session.execute(
            select(BookingLocation)
            .where(
                BookingLocation.organization_id == organization_id,
                BookingLocation.id == location_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_active_locations(self, organization_id: str) -> int:
        """Count active locations inside one organization.

        Args:
            organization_id: Tenant owning the counted locations.

        Returns:
            int: Number of active tenant locations.
        """
        result = await self._session.execute(
            select(func.count(BookingLocation.id)).where(
                BookingLocation.organization_id == organization_id,
                BookingLocation.status == "active",
            )
        )
        return int(result.scalar_one())

    @staticmethod
    def _default_settings(
        organization_id: str,
        public_name: str,
    ) -> BookingCompanySettings:
        """Build neutral German-first settings for a new tenant.

        Args:
            organization_id: Tenant primary key.
            public_name: Initial customer-visible company name.

        Returns:
            BookingCompanySettings: Unpersisted first settings revision.
        """
        return BookingCompanySettings(
            organization_id=organization_id,
            public_name=public_name,
            default_timezone=DEFAULT_COMPANY_TIMEZONE,
            default_locale=DEFAULT_COMPANY_LOCALE,
            currency=DEFAULT_COMPANY_CURRENCY,
            booking_horizon_days=90,
            minimum_notice_minutes=120,
            cancellation_notice_minutes=1440,
            reschedule_notice_minutes=1440,
            worker_selection_mode=WorkerSelectionMode.NEXT_AVAILABLE_OR_SPECIFIC.value,
            revision=1,
        )

    @staticmethod
    def _default_location(organization_id: str) -> BookingLocation:
        """Build the first active location without inventing an address.

        Args:
            organization_id: Tenant owning the initial location.

        Returns:
            BookingLocation: Unpersisted active primary location.
        """
        return BookingLocation(
            id=str(uuid4()),
            organization_id=organization_id,
            display_name="Primary location",
            timezone=DEFAULT_COMPANY_TIMEZONE,
            status="active",
            revision=1,
        )
