"""Transactional BKG-202 workforce administration and self-summary service."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal
from apps.booking_service.domain.tenancy import MembershipRole, MembershipStatus
from apps.booking_service.domain.workforce import WorkerProfileStatus
from apps.booking_service.models.workforce import BookingWorkerProfile
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.repositories.workforce_repository import WorkforceRepository
from apps.booking_service.schemas.workforce import (
    WorkerProfileCreateRequest,
    WorkerProfileLifecycleRequest,
    WorkerProfileResponse,
    WorkerProfileUpdateRequest,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.organization_access import (
    ActiveOrganizationAccess,
    require_active_organization_access,
    require_organization_administrator,
)
from apps.booking_service.services.workforce_projection import (
    worker_profile_audit_state,
)
from apps.booking_service.services.workforce_policy import (
    project_worker_profile,
    require_no_stranded_specific_services,
    require_worker_membership,
    validate_existing_worker_assignments,
    validate_worker_assignments,
)
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned asynchronous database session."""


class BookingWorkforceService:
    """Enforce worker membership, assignment, visibility, and lifecycle policy."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        """Configure an optional test/runtime session constructor.

        Args:
            session_factory: Optional injected asynchronous session factory.

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

    async def list_profiles(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> tuple[WorkerProfileResponse, ...]:
        """List administrator workforce state or the caller's worker summary.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit active tenant selected by the caller.

        Returns:
            tuple[WorkerProfileResponse, ...]: Full admin rows or zero/one self row.

        Raises:
            TenancyError: When tenant access exists without admin or worker role.
        """
        async with self._sessions()() as session:
            access = await require_active_organization_access(
                session,
                principal,
                organization_id,
            )
            administrator = MembershipRole.ORGANIZATION_ADMIN in access.roles
            if not administrator and MembershipRole.WORKER not in access.roles:
                raise self._read_denied()
            repository = WorkforceRepository(session)
            rows = await repository.list_profiles(
                organization_id,
                membership_id=None if administrator else access.membership_id,
                include_inactive=True,
            )
            response = tuple(
                [await project_worker_profile(session, repository, row) for row in rows]
            )
            await session.commit()
        return response

    async def read_profile(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        worker_profile_id: str,
    ) -> WorkerProfileResponse:
        """Read one worker through admin authority or exact self ownership.

        Args:
            principal: Verified request-scoped identity and coarse roles.
            organization_id: Explicit active tenant selected by the caller.
            worker_profile_id: Exact worker profile identifier.

        Returns:
            WorkerProfileResponse: Sanitized worker configuration.

        Raises:
            TenancyError: For absent, foreign, or non-self worker access.
        """
        async with self._sessions()() as session:
            access = await require_active_organization_access(
                session,
                principal,
                organization_id,
            )
            repository = WorkforceRepository(session)
            profile = await repository.get_profile(organization_id, worker_profile_id)
            self._require_visible_profile(profile, access)
            assert profile is not None
            response = await project_worker_profile(session, repository, profile)
            await session.commit()
        return response

    async def create_profile(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        request: WorkerProfileCreateRequest,
    ) -> WorkerProfileResponse:
        """Create a worker configuration for one valid worker membership.

        Args:
            principal: Verified organization-administrator identity.
            organization_id: Tenant owning the worker profile.
            request: Membership, presentation, and explicit assignments.

        Returns:
            WorkerProfileResponse: Newly persisted first revision.

        Raises:
            TenancyError: For invalid membership, duplicate, or assignments.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = WorkforceRepository(session)
            membership = await require_worker_membership(
                repository,
                organization_id,
                request.membership_id,
                allow_invited=True,
            )
            if await repository.get_profile_by_membership(
                organization_id,
                request.membership_id,
            ) is not None:
                raise TenancyError(
                    409,
                    "worker_membership_already_configured",
                    "Worker membership already has a profile",
                )
            await validate_worker_assignments(repository, organization_id, request)
            profile = await repository.create_profile(
                organization_id,
                request.membership_id,
                request,
            )
            if membership.status != MembershipStatus.ACTIVE.value:
                profile.status = WorkerProfileStatus.INACTIVE.value
            await repository.replace_locations(
                organization_id,
                profile.id,
                request.location_ids,
            )
            await repository.replace_qualifications(
                organization_id,
                profile.id,
                request.qualifications,
            )
            response = await project_worker_profile(session, repository, profile)
            await self._audit(
                session,
                principal,
                profile,
                "worker.created",
                None,
                worker_profile_audit_state(response),
            )
            await session.commit()
        return response

    async def update_profile(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        worker_profile_id: str,
        request: WorkerProfileUpdateRequest,
    ) -> WorkerProfileResponse:
        """Replace one worker's presentation and assignments atomically.

        Args:
            principal: Verified organization-administrator identity.
            organization_id: Tenant owning the worker profile.
            worker_profile_id: Exact profile being replaced.
            request: Complete state and observed revision.

        Returns:
            WorkerProfileResponse: Persisted next revision.

        Raises:
            TenancyError: For scope, validation, stale state, or stranded policy.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = WorkforceRepository(session)
            profile = self._require_profile(
                await repository.get_profile_for_update(
                    organization_id,
                    worker_profile_id,
                ),
                request.expected_revision,
            )
            before = worker_profile_audit_state(
                await project_worker_profile(session, repository, profile)
            )
            await validate_worker_assignments(repository, organization_id, request)
            self._apply_fields(profile, request)
            profile.revision += 1
            await repository.replace_locations(
                organization_id,
                profile.id,
                request.location_ids,
            )
            await repository.replace_qualifications(
                organization_id,
                profile.id,
                request.qualifications,
            )
            await require_no_stranded_specific_services(session, organization_id)
            response = await project_worker_profile(session, repository, profile)
            await self._audit(
                session,
                principal,
                profile,
                "worker.updated",
                before,
                worker_profile_audit_state(response),
            )
            await session.commit()
        return response

    async def deactivate_profile(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        worker_profile_id: str,
        expected_revision: int,
    ) -> WorkerProfileResponse:
        """Deactivate one worker without deleting qualifications or history.

        Args:
            principal: Verified organization-administrator identity.
            organization_id: Tenant owning the worker profile.
            worker_profile_id: Exact worker being deactivated.
            expected_revision: Revision last observed by the caller.

        Returns:
            WorkerProfileResponse: Inactive retained profile.

        Raises:
            TenancyError: For scope, lifecycle, revision, or stranded policy.
        """
        return await self._transition(
            principal,
            organization_id,
            worker_profile_id,
            expected_revision,
            activate=False,
        )

    async def reactivate_profile(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        worker_profile_id: str,
        request: WorkerProfileLifecycleRequest,
    ) -> WorkerProfileResponse:
        """Reactivate one worker after membership and assignment validation.

        Args:
            principal: Verified organization-administrator identity.
            organization_id: Tenant owning the worker profile.
            worker_profile_id: Exact worker being reactivated.
            request: Revision last observed by the caller.

        Returns:
            WorkerProfileResponse: Active retained profile.

        Raises:
            TenancyError: For invalid membership, assignment, lifecycle, or revision.
        """
        return await self._transition(
            principal,
            organization_id,
            worker_profile_id,
            request.expected_revision,
            activate=True,
        )

    async def _transition(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        worker_profile_id: str,
        expected_revision: int,
        *,
        activate: bool,
    ) -> WorkerProfileResponse:
        """Apply one audited reversible worker lifecycle transition.

        Args:
            principal: Verified tenant-administrator identity.
            organization_id: Tenant owning the worker profile.
            worker_profile_id: Exact worker being transitioned.
            expected_revision: Revision last observed by the caller.
            activate: Whether inactive state becomes active.

        Returns:
            WorkerProfileResponse: Resulting worker revision.

        Raises:
            TenancyError: For scope, lifecycle, validation, or stranded policy.
        """
        async with self._sessions()() as session:
            await require_organization_administrator(session, principal, organization_id)
            repository = WorkforceRepository(session)
            profile = self._require_profile(
                await repository.get_profile_for_update(
                    organization_id,
                    worker_profile_id,
                ),
                expected_revision,
            )
            self._require_transition_state(profile, activate=activate)
            before = worker_profile_audit_state(
                await project_worker_profile(session, repository, profile)
            )
            if activate:
                await self._validate_activation(repository, profile)
            profile.status = (
                WorkerProfileStatus.ACTIVE.value
                if activate
                else WorkerProfileStatus.INACTIVE.value
            )
            profile.revision += 1
            await session.flush()
            await require_no_stranded_specific_services(session, organization_id)
            response = await project_worker_profile(session, repository, profile)
            action = "worker.reactivated" if activate else "worker.deactivated"
            await self._audit(
                session,
                principal,
                profile,
                action,
                before,
                worker_profile_audit_state(response),
            )
            await session.commit()
        return response

    @staticmethod
    def _require_transition_state(
        profile: BookingWorkerProfile,
        *,
        activate: bool,
    ) -> None:
        """Require the worker lifecycle state expected by one transition.

        Args:
            profile: Locked worker profile being transitioned.
            activate: Whether inactive state is expected before mutation.

        Returns:
            None: Successful return permits the lifecycle transition.

        Raises:
            TenancyError: When another caller already changed lifecycle state.
        """
        expected = (
            WorkerProfileStatus.INACTIVE if activate else WorkerProfileStatus.ACTIVE
        )
        if profile.status != expected.value:
            raise TenancyError(
                409,
                "worker_lifecycle_conflict",
                "Worker lifecycle changed",
            )

    @staticmethod
    async def _validate_activation(
        repository: WorkforceRepository,
        profile: BookingWorkerProfile,
    ) -> None:
        """Revalidate worker membership and retained assignments for activation.

        Args:
            repository: Workforce repository bound to the transaction.
            profile: Inactive worker profile being reactivated.

        Returns:
            None: Successful return means activation prerequisites remain valid.

        Raises:
            TenancyError: When membership or retained assignments are invalid.
        """
        await require_worker_membership(
            repository,
            profile.organization_id,
            profile.membership_id,
            allow_invited=False,
        )
        await validate_existing_worker_assignments(
            repository,
            profile.organization_id,
            profile.id,
        )

    @staticmethod
    def _apply_fields(
        profile: BookingWorkerProfile,
        request: WorkerProfileUpdateRequest,
    ) -> None:
        """Apply validated mutable fields without changing identity/lifecycle.

        Args:
            profile: Locked worker profile to mutate in memory.
            request: Complete validated replacement.

        Returns:
            None: Mutable presentation fields are assigned to the row.
        """
        values = request.model_dump(
            mode="python",
            exclude={"expected_revision", "location_ids", "qualifications"},
        )
        for field, value in values.items():
            setattr(profile, field, value)

    @staticmethod
    def _require_profile(
        profile: BookingWorkerProfile | None,
        expected_revision: int,
    ) -> BookingWorkerProfile:
        """Require one tenant worker at the caller's observed revision.

        Args:
            profile: Tenant-scoped locked profile or ``None``.
            expected_revision: Revision last observed by the caller.

        Returns:
            BookingWorkerProfile: Existing matching worker profile.

        Raises:
            TenancyError: For safe not-found or retryable revision conflict.
        """
        if profile is None:
            raise TenancyError(404, "worker_not_found", "Worker was not found")
        if profile.revision != expected_revision:
            raise TenancyError(
                409,
                "worker_revision_conflict",
                "Worker configuration is stale",
                True,
            )
        return profile

    @staticmethod
    def _require_visible_profile(
        profile: BookingWorkerProfile | None,
        access: ActiveOrganizationAccess,
    ) -> None:
        """Require administrator authority or exact worker self ownership.

        Args:
            profile: Tenant-scoped worker profile or ``None``.
            access: Server-derived active membership and compatible roles.

        Returns:
            None: Successful return permits projection.

        Raises:
            TenancyError: Uniform 404 for absent, foreign, or colleague rows.
        """
        administrator = MembershipRole.ORGANIZATION_ADMIN in access.roles
        owns_profile = (
            profile is not None
            and MembershipRole.WORKER in access.roles
            and profile.membership_id == access.membership_id
        )
        if profile is None or (not administrator and not owns_profile):
            raise TenancyError(404, "worker_not_found", "Worker was not found")

    @staticmethod
    async def _audit(
        session: AsyncSession,
        principal: BookingPrincipal,
        profile: BookingWorkerProfile,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        """Stage one successful credential-free worker audit event.

        Args:
            session: Current transaction session.
            principal: Verified mutation actor.
            profile: Mutated worker identifying resource and tenant.
            action: Stable create, update, deactivate, or reactivate action.
            before: Sanitized previous state or ``None`` for creation.
            after: Sanitized resulting state.

        Returns:
            None: The event remains in the caller transaction.
        """
        await TenancyRepository(session).add_audit_event(
            actor_subject_id=principal.subject_id,
            organization_id=profile.organization_id,
            action=action,
            resource_type="worker_profile",
            resource_id=profile.id,
            before_state=before,
            after_state=after,
        )

    @staticmethod
    def _read_denied() -> TenancyError:
        """Build the safe error for active members without workforce access.

        Returns:
            TenancyError: Stable 403 capability denial.
        """
        return TenancyError(
            403,
            "worker_read_denied",
            "Workforce access is not allowed",
        )
