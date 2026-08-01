"""Transactional scoped membership administration for Booking Service.

Database membership intent is committed before Keycloak delivery. Provider
failure therefore leaves a durable invited or updated aggregate plus a safe
retry state instead of losing the administrator's command.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal, BookingRole
from apps.booking_service.domain.membership_policy import (
    MembershipManagementScope,
    MembershipPolicyError,
    validate_membership_roles,
    validate_membership_transition,
)
from apps.booking_service.domain.tenancy import (
    MEMBERSHIP_ROLE_ORDER,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    PlatformAccessStatus,
    SubjectStatus,
    compatible_membership_roles,
)
from apps.booking_service.models.tenancy import (
    BookingIdentityRoleOutbox,
    OrganizationMembership,
)
from apps.booking_service.repositories import MembershipRepository, TenancyRepository
from apps.booking_service.schemas.membership import (
    IdentitySyncStatus,
    MembershipIdentitySyncResponse,
    MembershipSummaryResponse,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.identity_administration import IdentityAdministrationAdapter
from apps.booking_service.services.membership_audit import (
    membership_audit_state,
    record_membership_command,
)
from apps.booking_service.services.membership_delivery import MembershipIdentityDelivery
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned async database session."""


class BookingMembershipService:
    """Enforce actor scope, lifecycle policy, audit, and provider recovery."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        identity_adapter: IdentityAdministrationAdapter | None = None,
    ) -> None:
        """Configure database and identity-administration dependencies.

        Args:
            session_factory: Optional async-session constructor for tests.
            identity_adapter: Optional narrow provider adapter override.

        Returns:
            None: External resources remain deferred until an operation begins.
        """
        self._session_factory = session_factory
        self._delivery = MembershipIdentityDelivery(self._sessions, identity_adapter)

    def _sessions(self) -> SessionFactory:
        """Resolve the injected or initialized runtime session factory.

        Returns:
            SessionFactory: Callable producing caller-owned async sessions.

        Raises:
            RuntimeError: When database startup has not completed.
        """
        if self._session_factory is not None:
            return self._session_factory
        handler = get_database_handler()
        return handler.AsyncSessionLocal  # type: ignore[attr-defined]

    async def list_memberships(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> tuple[MembershipSummaryResponse, ...]:
        """List memberships through platform or same-tenant admin authority.

        Args:
            principal: Verified request-scoped actor.
            organization_id: Explicit tenant whose memberships are requested.

        Returns:
            tuple[MembershipSummaryResponse, ...]: Sanitized scoped memberships.

        Raises:
            TenancyError: For inactive, foreign, or unauthorized scope.
        """
        async with self._sessions()() as session:
            await self._authorize_management(session, principal, organization_id)
            repository = MembershipRepository(session)
            rows = await repository.list_memberships(organization_id)
            summaries = [
                await self._summary(session, row)
                for row in rows
            ]
            await session.commit()
        return tuple(summaries)

    async def invite_membership(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        subject_id: str,
        roles: tuple[MembershipRole, ...],
    ) -> MembershipSummaryResponse:
        """Persist an invitation before attempting provider role delivery.

        Args:
            principal: Verified platform or same-tenant administrator.
            organization_id: Explicit tenant that owns the invitation.
            subject_id: Immutable provider subject, never username or email.
            roles: Complete initial role set.

        Returns:
            MembershipSummaryResponse: Active membership on delivery success,
            otherwise a durable invited membership with retry metadata.

        Raises:
            TenancyError: For authorization, duplicate membership, or policy failure.
        """
        role_set = frozenset(roles)
        async with self._sessions()() as session:
            scope = await self._authorize_management(session, principal, organization_id)
            self._apply_role_policy(scope, frozenset(), role_set)
            tenancy = TenancyRepository(session)
            if await tenancy.get_membership(organization_id, subject_id) is not None:
                raise TenancyError(409, "membership_exists", "Membership already exists", True)
            await tenancy.ensure_subject(subject_id)
            repository = MembershipRepository(session)
            membership = await repository.create_membership(organization_id, subject_id)
            await tenancy.replace_membership_roles(organization_id, membership.id, role_set)
            outbox = await repository.create_identity_outbox(membership, role_set)
            await record_membership_command(
                tenancy,
                principal.subject_id,
                membership,
                None,
                membership_audit_state(
                    membership.status, role_set, membership.revision
                ),
            )
            await session.commit()
        await self._delivery.deliver(
            principal.subject_id, organization_id, membership.id, outbox.id
        )
        return await self._read_summary(principal, organization_id, membership.id)

    async def update_membership(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        membership_id: str,
        expected_revision: int,
        target_status: MembershipStatus,
        roles: tuple[MembershipRole, ...],
    ) -> MembershipSummaryResponse:
        """Replace one scoped membership through optimistic policy checks.

        Args:
            principal: Verified platform or same-tenant administrator.
            organization_id: Tenant that must own the membership.
            membership_id: Membership identifier within that tenant.
            expected_revision: Revision last observed by the caller.
            target_status: Complete desired lifecycle state.
            roles: Complete desired app-owned role set.

        Returns:
            MembershipSummaryResponse: Updated membership and provider state.

        Raises:
            TenancyError: For foreign scope, stale revision, invalid transition,
                privilege escalation, or last-administrator lockout.
        """
        outbox_id = await self._persist_update(
            principal,
            organization_id,
            membership_id,
            expected_revision,
            target_status,
            frozenset(roles),
        )
        if outbox_id is not None:
            await self._delivery.deliver(
                principal.subject_id, organization_id, membership_id, outbox_id
            )
        return await self._read_summary(principal, organization_id, membership_id)

    async def retry_identity_sync(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        membership_id: str,
    ) -> MembershipSummaryResponse:
        """Retry the newest recoverable durable identity-role delivery.

        Args:
            principal: Verified platform or same-tenant administrator.
            organization_id: Tenant that must own the membership and outbox.
            membership_id: Membership with failed or pending provider work.

        Returns:
            MembershipSummaryResponse: Membership with refreshed sync state.

        Raises:
            TenancyError: For foreign scope or absent/non-retryable delivery work.
        """
        async with self._sessions()() as session:
            await self._authorize_management(session, principal, organization_id)
            repository = MembershipRepository(session)
            membership = await repository.get_membership_for_update(
                organization_id, membership_id
            )
            if membership is None:
                raise self._membership_not_found()
            outbox = await repository.latest_identity_outbox(organization_id, membership_id)
            if outbox is None or outbox.status not in {"pending", "failed"} or not outbox.retryable:
                raise TenancyError(
                    409,
                    "identity_sync_not_retryable",
                    "No recoverable identity synchronization is available",
                )
            await session.commit()
        await self._delivery.deliver(
            principal.subject_id, organization_id, membership_id, outbox.id
        )
        return await self._read_summary(principal, organization_id, membership_id)

    async def _persist_update(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        membership_id: str,
        expected_revision: int,
        target_status: MembershipStatus,
        target_roles: frozenset[MembershipRole],
    ) -> str | None:
        """Validate, persist, audit, and optionally enqueue one update.

        Args:
            principal: Verified administrative actor.
            organization_id: Explicit tenant scope.
            membership_id: Scoped membership identifier.
            expected_revision: Caller-observed revision.
            target_status: Complete desired lifecycle state.
            target_roles: Complete desired role set.

        Returns:
            str | None: New outbox ID when provider delivery is required.

        Raises:
            TenancyError: For authorization, stale state, or policy rejection.
        """
        async with self._sessions()() as session:
            scope = await self._authorize_management(session, principal, organization_id)
            repository = MembershipRepository(session)
            tenancy = TenancyRepository(session)
            membership = await repository.get_membership_for_update(organization_id, membership_id)
            if membership is None:
                raise self._membership_not_found()
            if membership.revision != expected_revision:
                raise TenancyError(409, "membership_revision_conflict", "Membership is stale", True)
            current_roles = frozenset(
                await tenancy.get_membership_roles(organization_id, membership.id)
            )
            before_state = membership_audit_state(
                membership.status, current_roles, membership.revision
            )
            admin_count = await repository.active_administrator_count(organization_id)
            self._apply_transition_policy(
                scope, membership, current_roles, target_status, target_roles, admin_count
            )
            outbox_id = await self._apply_update(
                repository, tenancy, membership, target_status, current_roles, target_roles
            )
            await record_membership_command(
                tenancy,
                principal.subject_id,
                membership,
                before_state,
                membership_audit_state(
                    membership.status, target_roles, membership.revision
                ),
            )
            await session.commit()
        return outbox_id

    async def _apply_update(
        self,
        repository: MembershipRepository,
        tenancy: TenancyRepository,
        membership: OrganizationMembership,
        target_status: MembershipStatus,
        current_roles: frozenset[MembershipRole],
        target_roles: frozenset[MembershipRole],
    ) -> str | None:
        """Stage one already-authorized membership mutation and outbox.

        Args:
            repository: Transaction-bound membership repository.
            tenancy: Transaction-bound role and audit repository.
            membership: Locked membership aggregate.
            target_status: Validated target lifecycle state.
            current_roles: Persisted role set before mutation.
            target_roles: Validated complete target role set.

        Returns:
            str | None: New outbox identifier when role delivery is needed.
        """
        await repository.cancel_open_identity_outboxes(
            membership.organization_id, membership.id
        )
        added_roles = target_roles - current_roles
        membership.status = target_status.value
        membership.revision += 1
        await tenancy.replace_membership_roles(
            membership.organization_id, membership.id, target_roles
        )
        requires_sync = target_status is MembershipStatus.INVITED or bool(added_roles)
        if target_status is MembershipStatus.REVOKED or not requires_sync:
            return None
        outbox = await repository.create_identity_outbox(
            membership,
            target_roles if target_status is MembershipStatus.INVITED else added_roles,
        )
        return outbox.id

    async def _read_summary(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        membership_id: str,
    ) -> MembershipSummaryResponse:
        """Reload one membership after a mutation not requiring delivery.

        Args:
            principal: Verified administrative actor.
            organization_id: Explicit tenant scope.
            membership_id: Scoped membership identifier.

        Returns:
            MembershipSummaryResponse: Current sanitized aggregate.

        Raises:
            TenancyError: When scope is lost or the membership disappears.
        """
        async with self._sessions()() as session:
            await self._authorize_management(session, principal, organization_id)
            repository = MembershipRepository(session)
            membership = await repository.get_membership_for_update(
                organization_id, membership_id
            )
            if membership is None:
                raise self._membership_not_found()
            summary = await self._summary(session, membership)
            await session.commit()
        return summary

    async def _authorize_management(
        self,
        session: AsyncSession,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> MembershipManagementScope:
        """Resolve platform or same-tenant organization administration.

        Args:
            session: Current transaction session.
            principal: Verified request-scoped actor.
            organization_id: Explicit tenant being managed.

        Returns:
            MembershipManagementScope: Highest valid server-derived authority.

        Raises:
            TenancyError: For inactive subject, absent tenant, or denied scope.
        """
        tenancy = TenancyRepository(session)
        subject = await tenancy.ensure_subject(principal.subject_id)
        if subject.status != SubjectStatus.ACTIVE.value:
            raise TenancyError(403, "subject_inactive", "Booking access is not active")
        organization = await tenancy.get_organization(organization_id)
        if organization is None:
            raise self._membership_not_found()
        access = await tenancy.get_platform_access(principal.subject_id)
        if (
            BookingRole.PLATFORM_ADMIN in principal.roles
            and access is not None
            and access.status == PlatformAccessStatus.ACTIVE.value
        ):
            return MembershipManagementScope.PLATFORM
        membership = await tenancy.get_membership(organization_id, principal.subject_id)
        if membership is None:
            raise self._membership_not_found()
        if organization.status != OrganizationStatus.ACTIVE.value:
            raise TenancyError(403, "organization_suspended", "Organization access is not active")
        if membership.status != MembershipStatus.ACTIVE.value:
            raise TenancyError(403, "membership_inactive", "Organization access is not active")
        roles = await tenancy.get_membership_roles(organization_id, membership.id)
        effective = compatible_membership_roles(principal.roles, roles)
        if MembershipRole.ORGANIZATION_ADMIN not in effective:
            raise TenancyError(403, "membership_management_denied", "Membership management is not allowed")
        return MembershipManagementScope.ORGANIZATION

    async def _summary(
        self,
        session: AsyncSession,
        membership: OrganizationMembership,
        outbox: BookingIdentityRoleOutbox | None = None,
    ) -> MembershipSummaryResponse:
        """Build one privacy-minimized membership response.

        Args:
            session: Current transaction session.
            membership: Persisted tenant-scoped membership.
            outbox: Optional already-loaded newest provider delivery row.

        Returns:
            MembershipSummaryResponse: Opaque identity, roles, state, and recovery.
        """
        tenancy = TenancyRepository(session)
        repository = MembershipRepository(session)
        roles = await tenancy.get_membership_roles(
            membership.organization_id, membership.id
        )
        latest = outbox or await repository.latest_identity_outbox(
            membership.organization_id, membership.id
        )
        ordered_roles = tuple(role for role in MEMBERSHIP_ROLE_ORDER if role in roles)
        return MembershipSummaryResponse(
            membership_id=membership.id,
            subject_id=membership.subject_id,
            status=MembershipStatus(membership.status),
            roles=ordered_roles,
            revision=membership.revision,
            identity_sync=self._sync_response(latest),
        )

    @staticmethod
    def _sync_response(
        outbox: BookingIdentityRoleOutbox | None,
    ) -> MembershipIdentitySyncResponse:
        """Map durable provider work to a safe response.

        Args:
            outbox: Latest provider delivery row, when any.

        Returns:
            MembershipIdentitySyncResponse: Safe status, retry flag, and code.
        """
        if outbox is None:
            return MembershipIdentitySyncResponse(
                status=IdentitySyncStatus.NOT_REQUIRED,
                retryable=False,
            )
        return MembershipIdentitySyncResponse(
            status=IdentitySyncStatus(outbox.status),
            retryable=bool(outbox.retryable),
            error_code=outbox.last_error_code,
        )

    @staticmethod
    def _apply_role_policy(
        scope: MembershipManagementScope,
        current_roles: frozenset[MembershipRole],
        target_roles: frozenset[MembershipRole],
    ) -> None:
        """Translate pure role-policy rejection into the safe service contract.

        Args:
            scope: Server-derived management authority.
            current_roles: Persisted roles before the command.
            target_roles: Requested complete role set.

        Returns:
            None: Successful return means the role set is authorized.

        Raises:
            TenancyError: With safe 403 or 422 policy detail.
        """
        try:
            validate_membership_roles(scope, current_roles, target_roles)
        except MembershipPolicyError as error:
            status = 403 if error.code.endswith("denied") else 422
            raise TenancyError(status, error.code, error.message) from error

    @staticmethod
    def _apply_transition_policy(
        scope: MembershipManagementScope,
        membership: OrganizationMembership,
        current_roles: frozenset[MembershipRole],
        target_status: MembershipStatus,
        target_roles: frozenset[MembershipRole],
        active_admin_count: int,
    ) -> None:
        """Translate lifecycle policy rejection into the safe service contract.

        Args:
            scope: Server-derived management authority.
            membership: Locked persisted membership.
            current_roles: Persisted roles before the command.
            target_status: Requested lifecycle state.
            target_roles: Requested complete role set.
            active_admin_count: Active administrators before the command.

        Returns:
            None: Successful return means the transition is valid.

        Raises:
            TenancyError: With safe 403, 409, or 422 policy detail.
        """
        try:
            validate_membership_transition(
                scope=scope,
                current_status=MembershipStatus(membership.status),
                current_roles=current_roles,
                target_status=target_status,
                target_roles=target_roles,
                active_admin_count=active_admin_count,
            )
        except MembershipPolicyError as error:
            status = 403 if error.code.endswith("denied") else 409
            raise TenancyError(status, error.code, error.message) from error

    @staticmethod
    def _membership_not_found() -> TenancyError:
        """Build the uniform private membership not-found response.

        Returns:
            TenancyError: Safe 404 without tenant or membership disclosure.
        """
        return TenancyError(404, "membership_not_found", "Membership was not found")
