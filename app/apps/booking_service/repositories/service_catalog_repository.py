"""Tenant-scoped persistence operations for the timed service catalog."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.models.company_settings import BookingLocation
from apps.booking_service.models.service_catalog import (
    BookingServiceLocationOffering,
    BookingServiceOffering,
)
from apps.booking_service.schemas.service_catalog import ServiceOfferingFields


class ServiceCatalogRepository:
    """Provide organization-bound catalog persistence in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository without taking commit ownership.

        Args:
            session: Caller-owned asynchronous SQLAlchemy session.

        Returns:
            None: The repository retains the session reference.
        """
        self._session = session

    async def list_offerings(
        self,
        organization_id: str,
        *,
        include_archived: bool,
        published_only: bool,
    ) -> tuple[BookingServiceOffering, ...]:
        """List services through explicit tenant and visibility predicates.

        Args:
            organization_id: Tenant owning every returned service.
            include_archived: Whether administrators may see archived rows.
            published_only: Whether unpublished active rows are excluded.

        Returns:
            tuple[BookingServiceOffering, ...]: Stable status/name/id order.
        """
        conditions = [BookingServiceOffering.organization_id == organization_id]
        if not include_archived:
            conditions.append(BookingServiceOffering.status == "active")
        if published_only:
            conditions.append(BookingServiceOffering.is_published.is_(True))
        result = await self._session.execute(
            select(BookingServiceOffering)
            .where(*conditions)
            .order_by(
                BookingServiceOffering.status,
                BookingServiceOffering.name,
                BookingServiceOffering.id,
            )
        )
        return tuple(result.scalars().all())

    async def get_offering(
        self,
        organization_id: str,
        service_offering_id: str,
    ) -> BookingServiceOffering | None:
        """Load one service through tenant and resource identifiers.

        Args:
            organization_id: Tenant that must own the service.
            service_offering_id: Exact service identifier inside the tenant.

        Returns:
            BookingServiceOffering | None: Matching row or ``None``.
        """
        result = await self._session.execute(
            select(BookingServiceOffering).where(
                BookingServiceOffering.organization_id == organization_id,
                BookingServiceOffering.id == service_offering_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_offering_for_update(
        self,
        organization_id: str,
        service_offering_id: str,
    ) -> BookingServiceOffering | None:
        """Lock one tenant-scoped service for optimistic mutation.

        Args:
            organization_id: Tenant that must own the service.
            service_offering_id: Exact service identifier inside the tenant.

        Returns:
            BookingServiceOffering | None: Locked matching row or ``None``.
        """
        result = await self._session.execute(
            select(BookingServiceOffering)
            .where(
                BookingServiceOffering.organization_id == organization_id,
                BookingServiceOffering.id == service_offering_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create_offering(
        self,
        organization_id: str,
        fields: ServiceOfferingFields,
    ) -> BookingServiceOffering:
        """Stage one active service without implicit location assignment.

        Args:
            organization_id: Tenant owning the new service.
            fields: Fully validated catalog fields.

        Returns:
            BookingServiceOffering: Newly staged first service revision.
        """
        offering = BookingServiceOffering(
            id=str(uuid4()),
            organization_id=organization_id,
            status="active",
            revision=1,
            **fields.model_dump(mode="python", exclude={"location_ids"}),
        )
        self._session.add(offering)
        await self._session.flush()
        return offering

    async def list_location_ids(
        self,
        organization_id: str,
        service_offering_id: str,
    ) -> tuple[str, ...]:
        """List deterministic explicit locations for one service.

        Args:
            organization_id: Tenant owning the assignment.
            service_offering_id: Service owning the assignment.

        Returns:
            tuple[str, ...]: Sorted assigned location identifiers.
        """
        result = await self._session.execute(
            select(BookingServiceLocationOffering.location_id)
            .where(
                BookingServiceLocationOffering.organization_id == organization_id,
                BookingServiceLocationOffering.service_offering_id
                == service_offering_id,
            )
            .order_by(BookingServiceLocationOffering.location_id)
        )
        return tuple(result.scalars().all())

    async def active_location_ids(
        self,
        organization_id: str,
        requested_ids: tuple[str, ...],
    ) -> frozenset[str]:
        """Resolve requested identifiers only against active tenant locations.

        Args:
            organization_id: Tenant that must own every location.
            requested_ids: Validated identifiers requested by the command.

        Returns:
            frozenset[str]: Active same-tenant identifiers that exist.
        """
        result = await self._session.execute(
            select(BookingLocation.id).where(
                BookingLocation.organization_id == organization_id,
                BookingLocation.status == "active",
                BookingLocation.id.in_(requested_ids),
            )
        )
        return frozenset(result.scalars().all())

    async def replace_locations(
        self,
        organization_id: str,
        service_offering_id: str,
        location_ids: tuple[str, ...],
    ) -> None:
        """Replace explicit service/location assignments atomically.

        Args:
            organization_id: Tenant owning every association.
            service_offering_id: Service receiving the complete assignment set.
            location_ids: Validated active same-tenant location identifiers.

        Returns:
            None: New rows are staged in the caller transaction.

        Side Effects:
            Deletes prior associations and flushes their complete replacement.
        """
        await self._session.execute(
            delete(BookingServiceLocationOffering).where(
                BookingServiceLocationOffering.organization_id == organization_id,
                BookingServiceLocationOffering.service_offering_id
                == service_offering_id,
            )
        )
        self._session.add_all(
            [
                BookingServiceLocationOffering(
                    organization_id=organization_id,
                    service_offering_id=service_offering_id,
                    location_id=location_id,
                )
                for location_id in location_ids
            ]
        )
        await self._session.flush()
