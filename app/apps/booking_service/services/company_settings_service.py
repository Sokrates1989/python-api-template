"""Transactional company-settings and location application service."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.company_settings import LocationStatus
from apps.booking_service.models.company_settings import (
    BookingCompanySettings,
    BookingLocation,
)
from apps.booking_service.repositories.company_settings_repository import (
    CompanySettingsRepository,
)
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.schemas.company_settings import (
    CompanySettingsResponse,
    CompanySettingsUpdateRequest,
    LocationCreateRequest,
    LocationLifecycleRequest,
    LocationResponse,
    LocationUpdateRequest,
)
from apps.booking_service.services.company_settings_projection import (
    company_settings_response,
    location_audit_state,
    location_response,
    settings_audit_state,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import (
    require_active_organization_access,
    require_organization_administrator,
)
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned asynchronous database session."""


class BookingCompanySettingsService:
    """Enforce tenant authorization, revisions, lifecycle, and audit policy.

    Attributes:
        session_factory: Optional injectable session constructor used by tests.
    """

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

    async def read_company_settings(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> CompanySettingsResponse:
        """Read company settings through any active compatible membership.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant selected by the caller.

        Returns:
            CompanySettingsResponse: Sanitized profile, policy, and locations.

        Raises:
            TenancyError: For absent, foreign, inactive, or uninitialized scope.
        """
        async with self._sessions()() as session:
            await require_active_organization_access(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            settings = await repository.get_settings(organization_id)
            if settings is None:
                raise self._settings_missing()
            locations = await repository.list_active_locations(organization_id)
            response = company_settings_response(settings, locations)
            await session.commit()
        return response

    async def update_company_settings(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        request: CompanySettingsUpdateRequest,
    ) -> CompanySettingsResponse:
        """Replace one tenant profile and booking policy atomically.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant being mutated.
            request: Complete validated representation and observed revision.

        Returns:
            CompanySettingsResponse: Updated settings and active locations.

        Raises:
            TenancyError: For denied scope, missing settings, or stale revision.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            settings = await repository.get_settings_for_update(organization_id)
            if settings is None:
                raise self._settings_missing()
            self._require_revision(settings.revision, request.expected_revision, "settings")
            before = settings_audit_state(settings)
            self._apply_settings(settings, request)
            await session.flush()
            after = settings_audit_state(settings)
            await self._audit_settings(session, principal, settings, before, after)
            locations = await repository.list_active_locations(organization_id)
            response = company_settings_response(settings, locations)
            await session.commit()
        return response

    async def create_location(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        request: LocationCreateRequest,
    ) -> LocationResponse:
        """Create and audit one active location as a tenant administrator.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant owning the new location.
            request: Validated complete location fields.

        Returns:
            LocationResponse: Newly created active location.

        Raises:
            TenancyError: When same-tenant administrator authority is absent.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            location = await repository.create_location(organization_id, request)
            response = location_response(location)
            await self._audit_location(
                session,
                principal,
                location,
                "location.created",
                None,
                response.model_dump(mode="json"),
            )
            await session.commit()
        return response

    async def update_location(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        location_id: str,
        request: LocationUpdateRequest,
    ) -> LocationResponse:
        """Replace an active scoped location using optimistic concurrency.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant owning the location.
            location_id: Exact location identifier within the tenant.
            request: Complete fields and revision last observed by the caller.

        Returns:
            LocationResponse: Updated active location.

        Raises:
            TenancyError: For denied scope, hidden foreign ID, archived row, or
                stale revision.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            location = await repository.get_location_for_update(organization_id, location_id)
            location = self._require_mutable_location(location, request.expected_revision)
            before = location_audit_state(location)
            self._apply_location(location, request)
            await session.flush()
            after = location_audit_state(location)
            await self._audit_location(
                session, principal, location, "location.updated", before, after
            )
            response = location_response(location)
            await session.commit()
        return response

    async def archive_location(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        location_id: str,
        expected_revision: int,
    ) -> LocationResponse:
        """Soft-archive a non-final location while retaining references.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant owning the location.
            location_id: Exact location identifier within the tenant.
            expected_revision: Revision last observed by the caller.

        Returns:
            LocationResponse: Archived retained location.

        Raises:
            TenancyError: For denied scope, foreign ID, stale revision, already
                archived state, or an attempt to remove the final active place.

        Note:
            No physical delete is performed, so current and future booking
            references remain intact by construction.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            location = await repository.get_location_for_update(organization_id, location_id)
            location = self._require_mutable_location(location, expected_revision)
            if await repository.count_active_locations(organization_id) <= 1:
                raise TenancyError(
                    409,
                    "last_active_location_required",
                    "At least one active location is required",
                )
            before = location_audit_state(location)
            location.status = LocationStatus.ARCHIVED.value
            location.revision += 1
            await session.flush()
            after = location_audit_state(location)
            await self._audit_location(
                session, principal, location, "location.archived", before, after
            )
            response = location_response(location)
            await session.commit()
        return response

    async def reactivate_location(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        location_id: str,
        request: LocationLifecycleRequest,
    ) -> LocationResponse:
        """Reactivate one archived location using optimistic concurrency.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit tenant owning the location.
            location_id: Exact location identifier within the tenant.
            request: Revision last observed by the caller.

        Returns:
            LocationResponse: Reactivated location with an incremented revision.

        Raises:
            TenancyError: For denied scope, foreign ID, stale revision, or an
                already-active location.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = CompanySettingsRepository(session)
            location = await repository.get_location_for_update(organization_id, location_id)
            location = self._require_location(location, request.expected_revision)
            if location.status == LocationStatus.ACTIVE.value:
                raise TenancyError(409, "location_already_active", "Location is already active")
            before = location_audit_state(location)
            location.status = LocationStatus.ACTIVE.value
            location.revision += 1
            await session.flush()
            after = location_audit_state(location)
            await self._audit_location(
                session, principal, location, "location.reactivated", before, after
            )
            response = location_response(location)
            await session.commit()
        return response

    @staticmethod
    def _apply_settings(
        settings: BookingCompanySettings,
        request: CompanySettingsUpdateRequest,
    ) -> None:
        """Apply one complete validated settings replacement.

        Args:
            settings: Locked settings row to mutate.
            request: Complete validated settings replacement.

        Returns:
            None: The row is changed in memory and its revision increments.
        """
        values = request.model_dump(exclude={"expected_revision"}, mode="python")
        for field, value in values.items():
            setattr(settings, field, value)
        settings.revision += 1

    @staticmethod
    def _apply_location(
        location: BookingLocation,
        request: LocationUpdateRequest,
    ) -> None:
        """Apply one complete validated location replacement.

        Args:
            location: Locked active location row to mutate.
            request: Complete validated location replacement.

        Returns:
            None: The row is changed in memory and its revision increments.
        """
        values = request.model_dump(exclude={"expected_revision"}, mode="python")
        for field, value in values.items():
            setattr(location, field, value)
        location.revision += 1

    @staticmethod
    def _require_revision(actual: int, expected: int, resource: str) -> None:
        """Reject a stale optimistic-concurrency revision.

        Args:
            actual: Current persisted revision.
            expected: Revision supplied by the caller.
            resource: Stable resource name used by the error code.

        Returns:
            None: Successful return means the revisions match.

        Raises:
            TenancyError: Retryable 409 when the caller must reload state.
        """
        if actual != expected:
            raise TenancyError(
                409,
                f"{resource}_revision_conflict",
                "Company configuration is stale",
                True,
            )

    @classmethod
    def _require_mutable_location(
        cls,
        location: BookingLocation | None,
        expected_revision: int,
    ) -> BookingLocation:
        """Require an existing active location at the expected revision.

        Args:
            location: Tenant-scoped locked location or ``None``.
            expected_revision: Revision supplied by the caller.

        Returns:
            BookingLocation: Existing active row at the expected revision.

        Raises:
            TenancyError: Safe 404, lifecycle 409, or retryable revision 409.
        """
        location = cls._require_location(location, expected_revision)
        if location.status != LocationStatus.ACTIVE.value:
            raise TenancyError(409, "location_archived", "Location is archived")
        return location

    @classmethod
    def _require_location(
        cls,
        location: BookingLocation | None,
        expected_revision: int,
    ) -> BookingLocation:
        """Require one scoped location at the expected revision.

        Args:
            location: Tenant-scoped locked location or ``None``.
            expected_revision: Revision supplied by the caller.

        Returns:
            BookingLocation: Existing row at the expected revision.

        Raises:
            TenancyError: Safe 404 or retryable revision conflict.
        """
        if location is None:
            raise TenancyError(404, "location_not_found", "Location was not found")
        cls._require_revision(location.revision, expected_revision, "location")
        return location

    @staticmethod
    async def _audit_settings(
        session: AsyncSession,
        principal: BookingPrincipal,
        settings: BookingCompanySettings,
        before: dict[str, object],
        after: dict[str, object],
    ) -> None:
        """Stage one successful settings replacement audit event.

        Args:
            session: Current transaction session.
            principal: Verified mutation actor.
            settings: Mutated settings row identifying the tenant.
            before: Sanitized prior settings state.
            after: Sanitized resulting settings state.

        Returns:
            None: The event remains in the caller transaction.
        """
        await TenancyRepository(session).add_audit_event(
            actor_subject_id=principal.subject_id,
            organization_id=settings.organization_id,
            action="company_settings.updated",
            resource_type="company_settings",
            resource_id=settings.organization_id,
            before_state=before,
            after_state=after,
        )

    @staticmethod
    async def _audit_location(
        session: AsyncSession,
        principal: BookingPrincipal,
        location: BookingLocation,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        """Stage one successful location lifecycle audit event.

        Args:
            session: Current transaction session.
            principal: Verified mutation actor.
            location: Mutated location identifying resource and tenant.
            action: Stable create, update, or archive event name.
            before: Sanitized previous state or ``None`` for creation.
            after: Sanitized resulting state.

        Returns:
            None: The event remains in the caller transaction.
        """
        await TenancyRepository(session).add_audit_event(
            actor_subject_id=principal.subject_id,
            organization_id=location.organization_id,
            action=action,
            resource_type="location",
            resource_id=location.id,
            before_state=before,
            after_state=after,
        )

    @staticmethod
    def _settings_missing() -> TenancyError:
        """Build the recoverable invariant error for missing migrated defaults.

        Returns:
            TenancyError: Retryable conflict without internal persistence detail.
        """
        return TenancyError(
            409,
            "company_settings_not_initialized",
            "Company settings are not initialized",
            True,
        )
