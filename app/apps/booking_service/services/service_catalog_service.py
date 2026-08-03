"""Transactional application service for the timed service catalog."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.service_catalog import ServiceOfferingStatus
from apps.booking_service.domain.tenancy import MembershipRole
from apps.booking_service.models.service_catalog import BookingServiceOffering
from apps.booking_service.repositories.company_settings_repository import (
    CompanySettingsRepository,
)
from apps.booking_service.repositories.service_catalog_repository import (
    ServiceCatalogRepository,
)
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.schemas.service_catalog import (
    ServiceOfferingCreateRequest,
    ServiceOfferingLifecycleRequest,
    ServiceOfferingResponse,
    ServiceOfferingUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import (
    require_active_organization_access,
    require_organization_administrator,
)
from apps.booking_service.services.service_catalog_projection import (
    service_offering_audit_state,
    service_offering_response,
)
from apps.booking_service.services.workforce_policy import (
    require_no_stranded_specific_services,
)
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned asynchronous database session."""


class BookingServiceCatalogService:
    """Enforce catalog authorization, validation, lifecycle, and audit policy."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        """Configure an optional test/runtime session factory.

        Args:
            session_factory: Session constructor; runtime database state is
                resolved lazily when omitted.

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

    async def list_offerings(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> tuple[ServiceOfferingResponse, ...]:
        """List admin-complete or member-published services for one tenant.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit active tenant selected by the caller.

        Returns:
            tuple[ServiceOfferingResponse, ...]: Role-filtered catalog rows.

        Raises:
            TenancyError: For absent, foreign, inactive, or incompatible scope.
        """
        async with self._sessions()() as session:
            access = await require_active_organization_access(
                session,
                principal,
                organization_id,
            )
            administrator = MembershipRole.ORGANIZATION_ADMIN in access.roles
            repository = ServiceCatalogRepository(session)
            rows = await repository.list_offerings(
                organization_id,
                include_archived=administrator,
                published_only=not administrator,
            )
            response = tuple(
                [
                    service_offering_response(
                        row,
                        await repository.list_location_ids(organization_id, row.id),
                    )
                    for row in rows
                ]
            )
            await session.commit()
        return response

    async def read_offering(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        service_offering_id: str,
    ) -> ServiceOfferingResponse:
        """Read one service with role-aware publication visibility.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant selected by the caller.
            service_offering_id: Requested tenant-owned service identifier.

        Returns:
            ServiceOfferingResponse: Sanitized visible service revision.

        Raises:
            TenancyError: For absent scope or a hidden/unpublished resource.
        """
        async with self._sessions()() as session:
            access = await require_active_organization_access(
                session,
                principal,
                organization_id,
            )
            repository = ServiceCatalogRepository(session)
            offering = await repository.get_offering(
                organization_id,
                service_offering_id,
            )
            administrator = MembershipRole.ORGANIZATION_ADMIN in access.roles
            self._require_visible(offering, administrator=administrator)
            assert offering is not None
            locations = await repository.list_location_ids(
                organization_id,
                service_offering_id,
            )
            response = service_offering_response(offering, locations)
            await session.commit()
        return response

    async def create_offering(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        request: ServiceOfferingCreateRequest,
    ) -> ServiceOfferingResponse:
        """Create and audit one active service at valid tenant locations.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the new service.
            request: Validated complete service fields and locations.

        Returns:
            ServiceOfferingResponse: Newly persisted first revision.

        Raises:
            TenancyError: For scope, currency, or location-policy failures.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = ServiceCatalogRepository(session)
            await self._validate_policy(session, repository, organization_id, request)
            offering = await repository.create_offering(organization_id, request)
            await repository.replace_locations(
                organization_id,
                offering.id,
                request.location_ids,
            )
            await require_no_stranded_specific_services(session, organization_id)
            after = service_offering_audit_state(offering, request.location_ids)
            await self._audit(session, principal, offering, "service.created", None, after)
            await session.commit()
        return service_offering_response(offering, request.location_ids)

    async def update_offering(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        service_offering_id: str,
        request: ServiceOfferingUpdateRequest,
    ) -> ServiceOfferingResponse:
        """Replace one active service and assignments atomically.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the service.
            service_offering_id: Exact service being replaced.
            request: Complete replacement and observed revision.

        Returns:
            ServiceOfferingResponse: Persisted next revision.

        Raises:
            TenancyError: For scope, lifecycle, validation, or stale revision.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = ServiceCatalogRepository(session)
            offering = self._require_mutable(
                await repository.get_offering_for_update(
                    organization_id,
                    service_offering_id,
                ),
                request.expected_revision,
            )
            before_locations = await repository.list_location_ids(
                organization_id,
                service_offering_id,
            )
            before = service_offering_audit_state(offering, before_locations)
            await self._validate_policy(session, repository, organization_id, request)
            self._apply_fields(offering, request)
            offering.revision += 1
            await repository.replace_locations(
                organization_id,
                service_offering_id,
                request.location_ids,
            )
            await require_no_stranded_specific_services(session, organization_id)
            after = service_offering_audit_state(offering, request.location_ids)
            await self._audit(session, principal, offering, "service.updated", before, after)
            await session.commit()
        return service_offering_response(offering, request.location_ids)

    async def archive_offering(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        service_offering_id: str,
        expected_revision: int,
    ) -> ServiceOfferingResponse:
        """Archive and unpublish one service without deleting history.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the service.
            service_offering_id: Exact service being archived.
            expected_revision: Revision last observed by the caller.

        Returns:
            ServiceOfferingResponse: Archived retained revision.

        Raises:
            TenancyError: For scope, lifecycle, or revision failure.
        """
        return await self._transition(
            principal,
            organization_id,
            service_offering_id,
            expected_revision,
            activate=False,
        )

    async def reactivate_offering(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        service_offering_id: str,
        request: ServiceOfferingLifecycleRequest,
    ) -> ServiceOfferingResponse:
        """Reactivate one service as unpublished after location revalidation.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the service.
            service_offering_id: Exact service being reactivated.
            request: Revision last observed by the caller.

        Returns:
            ServiceOfferingResponse: Active unpublished next revision.

        Raises:
            TenancyError: For scope, lifecycle, location, or revision failure.
        """
        return await self._transition(
            principal,
            organization_id,
            service_offering_id,
            request.expected_revision,
            activate=True,
        )

    async def _transition(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        service_offering_id: str,
        expected_revision: int,
        *,
        activate: bool,
    ) -> ServiceOfferingResponse:
        """Apply one audited reversible service lifecycle transition.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the service.
            service_offering_id: Exact service being transitioned.
            expected_revision: Revision last observed by the caller.
            activate: Whether archived state becomes active.

        Returns:
            ServiceOfferingResponse: Resulting retained service revision.

        Raises:
            TenancyError: For scope, lifecycle, location, or revision failure.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = ServiceCatalogRepository(session)
            offering = self._require(
                await repository.get_offering_for_update(
                    organization_id,
                    service_offering_id,
                ),
                expected_revision,
            )
            expected_status = (
                ServiceOfferingStatus.ARCHIVED
                if activate
                else ServiceOfferingStatus.ACTIVE
            )
            if offering.status != expected_status.value:
                raise TenancyError(
                    409,
                    "service_lifecycle_conflict",
                    "Service lifecycle changed",
                )
            locations = await repository.list_location_ids(
                organization_id,
                service_offering_id,
            )
            if activate:
                await self._require_active_locations(repository, organization_id, locations)
            before = service_offering_audit_state(offering, locations)
            offering.status = (
                ServiceOfferingStatus.ACTIVE.value
                if activate
                else ServiceOfferingStatus.ARCHIVED.value
            )
            offering.is_published = False
            offering.revision += 1
            after = service_offering_audit_state(offering, locations)
            action = "service.reactivated" if activate else "service.archived"
            await self._audit(session, principal, offering, action, before, after)
            await session.commit()
        return service_offering_response(offering, locations)

    async def _validate_policy(
        self,
        session: AsyncSession,
        repository: ServiceCatalogRepository,
        organization_id: str,
        request: ServiceOfferingCreateRequest | ServiceOfferingUpdateRequest,
    ) -> None:
        """Require company currency and every requested active location.

        Args:
            session: Current transaction session.
            repository: Catalog repository bound to the same transaction.
            organization_id: Tenant owning company policy and locations.
            request: Validated create or replacement fields.

        Returns:
            None: Successful return means cross-resource policy is valid.

        Raises:
            TenancyError: When company defaults are missing, currency differs,
                or any location is foreign, absent, or archived.
        """
        settings = await CompanySettingsRepository(session).get_settings(organization_id)
        if settings is None:
            raise TenancyError(
                409,
                "company_settings_not_initialized",
                "Company settings are not initialized",
                True,
            )
        if request.currency != settings.currency:
            raise TenancyError(
                422,
                "service_currency_mismatch",
                "Service currency must match company currency",
            )
        await self._require_active_locations(
            repository,
            organization_id,
            request.location_ids,
        )

    @staticmethod
    async def _require_active_locations(
        repository: ServiceCatalogRepository,
        organization_id: str,
        location_ids: tuple[str, ...],
    ) -> None:
        """Require every assigned location to be active in the same tenant.

        Args:
            repository: Catalog repository bound to the current transaction.
            organization_id: Tenant owning every expected location.
            location_ids: Complete requested assignment set.

        Returns:
            None: Successful return proves exact active-location membership.

        Raises:
            TenancyError: Field-specific 422 when any location is invalid.
        """
        active = await repository.active_location_ids(organization_id, location_ids)
        if active != frozenset(location_ids):
            raise TenancyError(
                422,
                "service_locations_invalid",
                "Every service location must be active in this organization",
            )

    @staticmethod
    def _apply_fields(
        offering: BookingServiceOffering,
        request: ServiceOfferingUpdateRequest,
    ) -> None:
        """Apply validated mutable fields without changing identity/lifecycle.

        Args:
            offering: Locked active service row.
            request: Complete validated replacement.

        Returns:
            None: The SQLAlchemy row is mutated in memory.
        """
        for field, value in request.model_dump(
            mode="python",
            exclude={"expected_revision", "location_ids"},
        ).items():
            setattr(offering, field, value)

    @classmethod
    def _require_mutable(
        cls,
        offering: BookingServiceOffering | None,
        expected_revision: int,
    ) -> BookingServiceOffering:
        """Require an existing active service at the expected revision.

        Args:
            offering: Tenant-scoped locked service or ``None``.
            expected_revision: Revision supplied by the caller.

        Returns:
            BookingServiceOffering: Existing active row.

        Raises:
            TenancyError: For safe not-found, archive, or revision failure.
        """
        offering = cls._require(offering, expected_revision)
        if offering.status != ServiceOfferingStatus.ACTIVE.value:
            raise TenancyError(409, "service_archived", "Service is archived")
        return offering

    @staticmethod
    def _require(
        offering: BookingServiceOffering | None,
        expected_revision: int,
    ) -> BookingServiceOffering:
        """Require one scoped service at the expected revision.

        Args:
            offering: Tenant-scoped locked service or ``None``.
            expected_revision: Revision supplied by the caller.

        Returns:
            BookingServiceOffering: Existing matching row.

        Raises:
            TenancyError: For safe not-found or retryable revision conflict.
        """
        if offering is None:
            raise TenancyError(404, "service_not_found", "Service was not found")
        if offering.revision != expected_revision:
            raise TenancyError(
                409,
                "service_revision_conflict",
                "Service configuration is stale",
                True,
            )
        return offering

    @staticmethod
    def _require_visible(
        offering: BookingServiceOffering | None,
        *,
        administrator: bool,
    ) -> None:
        """Hide archived or unpublished services from ordinary members.

        Args:
            offering: Tenant-scoped service row or ``None``.
            administrator: Whether the caller has organization-admin access.

        Returns:
            None: Successful return means the row may be projected.

        Raises:
            TenancyError: Uniform 404 for absent or role-hidden service state.
        """
        if offering is None or (
            not administrator
            and (
                offering.status != ServiceOfferingStatus.ACTIVE.value
                or not offering.is_published
            )
        ):
            raise TenancyError(404, "service_not_found", "Service was not found")

    @staticmethod
    async def _audit(
        session: AsyncSession,
        principal: BookingPrincipal,
        offering: BookingServiceOffering,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        """Stage one successful credential-free catalog audit event.

        Args:
            session: Current transaction session.
            principal: Verified mutation actor.
            offering: Mutated service identifying tenant and resource.
            action: Stable create/update/archive/reactivate event name.
            before: Sanitized prior state or ``None`` for creation.
            after: Sanitized resulting state.

        Returns:
            None: The event remains in the caller transaction.
        """
        await TenancyRepository(session).add_audit_event(
            actor_subject_id=principal.subject_id,
            organization_id=offering.organization_id,
            action=action,
            resource_type="service_offering",
            resource_id=offering.id,
            before_state=before,
            after_state=after,
        )
