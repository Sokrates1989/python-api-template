"""Authenticated published-catalog projection for customers and preview.

This service reuses the authoritative workforce eligibility policy and emits
only deliberately narrow discovery schemas. Public browsing requires a
verified active Booking subject, but never tenant membership.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.tenancy import OrganizationStatus, SubjectStatus
from apps.booking_service.models.company_settings import BookingLocation
from apps.booking_service.models.service_catalog import BookingServiceOffering
from apps.booking_service.models.tenancy import BookingOrganization
from apps.booking_service.repositories.company_settings_repository import CompanySettingsRepository
from apps.booking_service.repositories.service_catalog_repository import ServiceCatalogRepository
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.repositories.workforce_repository import WorkforceRepository
from apps.booking_service.schemas.discovery import (
    DiscoveryLocationResponse,
    DiscoveryOrganizationResponse,
    DiscoveryServiceResponse,
    DiscoveryWorkerResponse,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import require_organization_administrator
from apps.booking_service.services.workforce_policy import project_worker_profile
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned asynchronous database session."""


class BookingDiscoveryService:
    """Project the published catalog through authenticated privacy boundaries."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        """Configure an optional test/runtime session factory.

        Args:
            session_factory: Session constructor; runtime state is resolved
                lazily when omitted.

        Returns:
            None: The service retains only the optional constructor.
        """
        self._session_factory = session_factory

    def _sessions(self) -> SessionFactory:
        """Resolve the injected or initialized runtime session factory.

        Returns:
            SessionFactory: Callable producing asynchronous sessions.

        Raises:
            RuntimeError: When selected-app database startup is incomplete.
        """
        if self._session_factory is not None:
            return self._session_factory
        handler = get_database_handler()
        return handler.AsyncSessionLocal  # type: ignore[attr-defined]

    async def list_catalogs(
        self,
        principal: BookingPrincipal,
    ) -> tuple[DiscoveryOrganizationResponse, ...]:
        """List every active organization with published customer content.

        Args:
            principal: Verified request identity; membership is not required.

        Returns:
            tuple[DiscoveryOrganizationResponse, ...]: Stable public catalogs.

        Raises:
            TenancyError: When the app-owned subject lifecycle is inactive.
        """
        async with self._sessions()() as session:
            await self._require_active_subject(session, principal)
            organizations = await TenancyRepository(session).list_organizations()
            catalogs: list[DiscoveryOrganizationResponse] = []
            for organization in organizations:
                if organization.status != OrganizationStatus.ACTIVE.value:
                    continue
                catalog = await self._project_catalog(session, organization)
                if catalog is not None and catalog.services:
                    catalogs.append(catalog)
            await session.commit()
        return tuple(catalogs)

    async def read_catalog(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> DiscoveryOrganizationResponse:
        """Read one active organization only when published content exists.

        Args:
            principal: Verified request identity; membership is not required.
            organization_id: Exact company selected from discovery.

        Returns:
            DiscoveryOrganizationResponse: Sanitized published catalog.

        Raises:
            TenancyError: When subject is inactive or the catalog is absent.
        """
        async with self._sessions()() as session:
            await self._require_active_subject(session, principal)
            organization = await TenancyRepository(session).get_organization(
                organization_id
            )
            catalog = await self._visible_catalog(session, organization)
            await session.commit()
        return catalog

    async def preview_catalog(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> DiscoveryOrganizationResponse:
        """Preview the exact customer projection as an organization administrator.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Explicit tenant being previewed.

        Returns:
            DiscoveryOrganizationResponse: Customer-equivalent projection,
            including empty services when nothing is published.

        Raises:
            TenancyError: When tenant-administrator authority is absent.
        """
        async with self._sessions()() as session:
            access = await require_organization_administrator(
                session,
                principal,
                organization_id,
            )
            catalog = await self._project_catalog(session, access.organization)
            if catalog is None:
                raise self._catalog_not_found()
            await session.commit()
        return catalog

    async def _visible_catalog(
        self,
        session: AsyncSession,
        organization: BookingOrganization | None,
    ) -> DiscoveryOrganizationResponse:
        """Require one active, non-empty public catalog.

        Args:
            session: Current caller-owned transaction session.
            organization: Requested tenant row or ``None``.

        Returns:
            DiscoveryOrganizationResponse: Non-empty published projection.

        Raises:
            TenancyError: With uniform 404 semantics when not discoverable.
        """
        if organization is None or organization.status != OrganizationStatus.ACTIVE.value:
            raise self._catalog_not_found()
        catalog = await self._project_catalog(session, organization)
        if catalog is None or not catalog.services:
            raise self._catalog_not_found()
        return catalog

    async def _project_catalog(
        self,
        session: AsyncSession,
        organization: BookingOrganization,
    ) -> DiscoveryOrganizationResponse | None:
        """Build one sanitized catalog from existing tenant-owned records.

        Args:
            session: Current caller-owned transaction session.
            organization: Active organization being projected.

        Returns:
            DiscoveryOrganizationResponse | None: Projection or ``None`` when
            company settings have not been initialized.
        """
        settings_repository = CompanySettingsRepository(session)
        settings = await settings_repository.get_settings(organization.id)
        if settings is None:
            return None
        active_locations = await settings_repository.list_active_locations(organization.id)
        catalog_repository = ServiceCatalogRepository(session)
        offerings = await catalog_repository.list_offerings(
            organization.id,
            include_archived=False,
            published_only=True,
        )
        locations = {location.id: location for location in active_locations}
        services = await self._project_services(
            session,
            catalog_repository,
            offerings,
            locations,
        )
        used_locations = frozenset(
            location_id for service in services for location_id in service.location_ids
        )
        return DiscoveryOrganizationResponse(
            organization_id=organization.id,
            public_name=settings.public_name,
            description=settings.description,
            default_locale=settings.default_locale,
            currency=settings.currency,
            locations=tuple(
                self._project_location(location)
                for location in active_locations
                if location.id in used_locations
            ),
            services=services,
        )

    async def _project_services(
        self,
        session: AsyncSession,
        repository: ServiceCatalogRepository,
        offerings: tuple[BookingServiceOffering, ...],
        locations: dict[str, BookingLocation],
    ) -> tuple[DiscoveryServiceResponse, ...]:
        """Project published services and their selectable public workers.

        Args:
            session: Current caller-owned transaction session.
            repository: Catalog repository bound to the same transaction.
            offerings: Active published service rows.
            locations: Active tenant locations keyed by identifier.

        Returns:
            tuple[DiscoveryServiceResponse, ...]: Stable sanitized services.
        """
        if not offerings:
            return ()
        organization_id = offerings[0].organization_id
        workers_by_service = await self._workers_by_service(session, organization_id)
        projected: list[DiscoveryServiceResponse] = []
        for offering in offerings:
            assigned = await repository.list_location_ids(organization_id, offering.id)
            active = tuple(item for item in assigned if item in locations)
            if active:
                projected.append(self._project_service(offering, active, workers_by_service))
        return tuple(projected)

    async def _workers_by_service(
        self,
        session: AsyncSession,
        organization_id: str,
    ) -> dict[str, tuple[DiscoveryWorkerResponse, ...]]:
        """Group workers by authoritative effective individual eligibility.

        Args:
            session: Current caller-owned transaction session.
            organization_id: Tenant owning all candidate workers and services.

        Returns:
            dict[str, tuple[DiscoveryWorkerResponse, ...]]: Service-keyed public
            workers in stable profile order.
        """
        repository = WorkforceRepository(session)
        profiles = await repository.list_profiles(organization_id, include_inactive=False)
        grouped: dict[str, list[DiscoveryWorkerResponse]] = {}
        for profile in profiles:
            projected = await project_worker_profile(session, repository, profile)
            for qualification in projected.qualifications:
                if not qualification.is_individually_bookable:
                    continue
                grouped.setdefault(qualification.service_offering_id, []).append(
                    DiscoveryWorkerResponse(
                        worker_profile_id=projected.worker_profile_id,
                        public_name=projected.public_name or "",
                        public_description=projected.public_description,
                        location_ids=projected.location_ids,
                    )
                )
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _project_service(
        offering: BookingServiceOffering,
        location_ids: tuple[str, ...],
        workers_by_service: dict[str, tuple[DiscoveryWorkerResponse, ...]],
    ) -> DiscoveryServiceResponse:
        """Remove internal scheduling and lifecycle fields from one service.

        Args:
            offering: Active published service row.
            location_ids: Active locations explicitly offering the service.
            workers_by_service: Effective public worker groups.

        Returns:
            DiscoveryServiceResponse: Customer-safe service projection.
        """
        workers = tuple(
            worker.model_copy(
                update={
                    "location_ids": tuple(
                        item for item in worker.location_ids if item in location_ids
                    )
                }
            )
            for worker in workers_by_service.get(offering.id, ())
        )
        return DiscoveryServiceResponse(
            service_offering_id=offering.id,
            name=offering.name,
            description=offering.description,
            category=offering.category,
            duration_minutes=offering.duration_minutes,
            price_minor_units=offering.price_minor_units,
            currency=offering.currency,
            worker_selection_mode=offering.worker_selection_mode,
            location_ids=location_ids,
            workers=workers,
        )

    @staticmethod
    def _project_location(location: BookingLocation) -> DiscoveryLocationResponse:
        """Remove private contact and lifecycle state from one location.

        Args:
            location: Active location referenced by published services.

        Returns:
            DiscoveryLocationResponse: Customer-safe place projection.
        """
        return DiscoveryLocationResponse(
            location_id=location.id,
            display_name=location.display_name,
            timezone=location.timezone,
            address_line_1=location.address_line_1,
            address_line_2=location.address_line_2,
            postal_code=location.postal_code,
            locality=location.locality,
            region=location.region,
            country_code=location.country_code,
        )

    @staticmethod
    async def _require_active_subject(
        session: AsyncSession,
        principal: BookingPrincipal,
    ) -> None:
        """Require an active app-owned lifecycle for authenticated browsing.

        Args:
            session: Current caller-owned transaction session.
            principal: Verified request identity.

        Returns:
            None: Successful return permits membership-free discovery.

        Raises:
            TenancyError: When the subject is not active.
        """
        subject = await TenancyRepository(session).ensure_subject(principal.subject_id)
        if subject.status != SubjectStatus.ACTIVE.value:
            raise TenancyError(403, "subject_inactive", "Booking access is not active")

    @staticmethod
    def _catalog_not_found() -> TenancyError:
        """Build uniform hidden-resource semantics for unpublished catalogs.

        Returns:
            TenancyError: Safe 404 without tenant-publication detail.
        """
        return TenancyError(404, "catalog_not_found", "Published catalog was not found")
