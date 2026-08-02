"""Transactional authorization and lifecycle service for Booking tenancy.

The service treats Keycloak roles as coarse input only. Platform operations
also require active app-owned platform access; organization operations also
require active organization membership and a compatible membership role.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.dependencies.identity import BookingPrincipal, BookingRole
from apps.booking_service.domain.tenancy import (
    BookingCapability,
    MembershipStatus,
    OrganizationStatus,
    PlatformAccessStatus,
    SubjectStatus,
    capabilities_for_membership_roles,
    compatible_membership_roles,
)
from apps.booking_service.models.tenancy import BookingOrganization
from apps.booking_service.repositories.company_settings_repository import (
    CompanySettingsRepository,
)
from apps.booking_service.repositories.tenancy_repository import TenancyRepository
from apps.booking_service.schemas.tenancy import (
    EffectiveContextResponse,
    OrganizationMembershipContextResponse,
    OrganizationSummaryResponse,
)
from apps.booking_service.services.errors import TenancyError
from backend.database import get_database_handler


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned async database session."""


class BookingTenancyService:
    """Enforce organization authorization and audited platform lifecycle.

    Attributes:
        session_factory: Optional injectable async-session constructor used by
            tests and runtime composition.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        """Configure the service with an optional session factory.

        Args:
            session_factory: Constructor for async sessions. When omitted, the
                initialized selected-app SQL handler is resolved per operation.

        Returns:
            None: The service retains only the optional factory.
        """
        self._session_factory = session_factory

    def _sessions(self) -> SessionFactory:
        """Resolve the injected or initialized runtime session factory.

        Returns:
            SessionFactory: Callable producing async SQLAlchemy sessions.

        Raises:
            RuntimeError: When application database startup has not completed.
        """
        if self._session_factory is not None:
            return self._session_factory
        handler = get_database_handler()
        return handler.AsyncSessionLocal  # type: ignore[attr-defined]

    async def effective_context(
        self,
        principal: BookingPrincipal,
    ) -> EffectiveContextResponse:
        """Project fail-closed active platform and organization context.

        Args:
            principal: Verified request-scoped Keycloak subject and coarse roles.

        Returns:
            EffectiveContextResponse: Active compatible memberships and
            server-derived capabilities in deterministic order.

        Raises:
            TenancyError: With 403 when the app-owned subject is suspended or
                pending deletion.
        """
        async with self._sessions()() as session:
            repository = TenancyRepository(session)
            subject = await repository.ensure_subject(principal.subject_id)
            self._require_active_subject(subject.status)
            platform_access = await repository.get_platform_access(principal.subject_id)
            organizations = await self._build_organization_contexts(repository, principal)
            await session.commit()
        platform_capabilities = self._platform_capabilities(principal, platform_access)
        revision = self._context_revision(subject.revision, platform_access, organizations)
        return EffectiveContextResponse(
            subject_id=principal.subject_id,
            coarse_roles=principal.roles,
            platform_capabilities=platform_capabilities,
            organizations=organizations,
            context_revision=revision,
        )

    async def _build_organization_contexts(
        self,
        repository: TenancyRepository,
        principal: BookingPrincipal,
    ) -> tuple[OrganizationMembershipContextResponse, ...]:
        """Build active organization contexts using compatible roles only.

        Args:
            repository: Transaction-bound tenancy repository.
            principal: Verified subject and coarse roles.

        Returns:
            tuple[OrganizationMembershipContextResponse, ...]: Active contexts
            ordered by organization name and identifier.
        """
        contexts: list[OrganizationMembershipContextResponse] = []
        memberships = await repository.list_subject_memberships(principal.subject_id)
        for membership, organization in memberships:
            stored_roles = await repository.get_membership_roles(
                organization.id, membership.id
            )
            effective_roles = compatible_membership_roles(principal.roles, stored_roles)
            if not effective_roles:
                continue
            contexts.append(
                OrganizationMembershipContextResponse(
                    organization=self._summary(organization),
                    membership_roles=effective_roles,
                    capabilities=capabilities_for_membership_roles(effective_roles),
                    membership_revision=membership.revision,
                )
            )
        return tuple(contexts)

    async def list_organizations(
        self,
        principal: BookingPrincipal,
    ) -> tuple[OrganizationSummaryResponse, ...]:
        """List all organizations for a dual-authorized platform actor.

        Args:
            principal: Verified request-scoped principal.

        Returns:
            tuple[OrganizationSummaryResponse, ...]: All tenant summaries.

        Raises:
            TenancyError: With 403 when either platform authorization gate is
                absent or the subject is inactive.
        """
        async with self._sessions()() as session:
            repository = TenancyRepository(session)
            await self._require_platform_access(repository, principal)
            organizations = await repository.list_organizations()
        return tuple(self._summary(organization) for organization in organizations)

    async def create_organization(
        self,
        principal: BookingPrincipal,
        display_name: str,
    ) -> OrganizationSummaryResponse:
        """Create and audit one active organization as a platform actor.

        Args:
            principal: Verified request-scoped principal.
            display_name: Validated human-readable organization name.

        Returns:
            OrganizationSummaryResponse: Newly created tenant.

        Raises:
            TenancyError: With 403 when dual platform authorization fails.
        """
        async with self._sessions()() as session:
            repository = TenancyRepository(session)
            await self._require_platform_access(repository, principal)
            organization = await repository.create_organization(display_name)
            await CompanySettingsRepository(session).ensure_defaults(
                organization.id,
                organization.display_name,
            )
            summary = self._summary(organization)
            await repository.add_audit_event(
                actor_subject_id=principal.subject_id,
                organization_id=organization.id,
                action="organization.created",
                resource_type="organization",
                resource_id=organization.id,
                before_state=None,
                after_state=summary.model_dump(mode="json"),
            )
            await session.commit()
        return summary

    async def suspend_organization(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        expected_revision: int,
    ) -> OrganizationSummaryResponse:
        """Suspend one tenant while retaining all history.

        Args:
            principal: Verified request-scoped platform principal.
            organization_id: Tenant to suspend.
            expected_revision: Revision last observed by the caller.

        Returns:
            OrganizationSummaryResponse: Updated suspended tenant.

        Raises:
            TenancyError: With 403, 404, or 409 for authorization, absence, or
                stale revision respectively.
        """
        return await self._transition_organization(
            principal,
            organization_id,
            expected_revision,
            OrganizationStatus.SUSPENDED,
        )

    async def reactivate_organization(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        expected_revision: int,
    ) -> OrganizationSummaryResponse:
        """Reactivate one suspended tenant with optimistic concurrency.

        Args:
            principal: Verified request-scoped platform principal.
            organization_id: Tenant to reactivate.
            expected_revision: Revision last observed by the caller.

        Returns:
            OrganizationSummaryResponse: Updated active tenant.

        Raises:
            TenancyError: With 403, 404, or 409 for authorization, absence, or
                stale revision respectively.
        """
        return await self._transition_organization(
            principal,
            organization_id,
            expected_revision,
            OrganizationStatus.ACTIVE,
        )

    async def _transition_organization(
        self,
        principal: BookingPrincipal,
        organization_id: str,
        expected_revision: int,
        target_status: OrganizationStatus,
    ) -> OrganizationSummaryResponse:
        """Lock, validate, transition, and audit one organization atomically.

        Args:
            principal: Verified request-scoped platform principal.
            organization_id: Tenant to transition.
            expected_revision: Revision last observed by the caller.
            target_status: Desired active or suspended lifecycle state.

        Returns:
            OrganizationSummaryResponse: Updated tenant summary.

        Raises:
            TenancyError: With safe 403, 404, or retryable 409 semantics.
        """
        async with self._sessions()() as session:
            repository = TenancyRepository(session)
            await self._require_platform_access(repository, principal)
            organization = await repository.get_organization_for_update(organization_id)
            if organization is None:
                raise self._not_found()
            if organization.revision != expected_revision:
                raise TenancyError(409, "organization_revision_conflict", "Organization context is stale", True)
            before = self._summary(organization)
            organization.status = target_status.value
            organization.revision += 1
            await session.flush()
            after = self._summary(organization)
            await repository.add_audit_event(
                actor_subject_id=principal.subject_id,
                organization_id=organization.id,
                action=f"organization.{target_status.value}",
                resource_type="organization",
                resource_id=organization.id,
                before_state=before.model_dump(mode="json"),
                after_state=after.model_dump(mode="json"),
            )
            await session.commit()
        return after

    async def read_member_organization(
        self,
        principal: BookingPrincipal,
        organization_id: str,
    ) -> OrganizationSummaryResponse:
        """Read one tenant through active compatible membership authorization.

        Args:
            principal: Verified request-scoped principal.
            organization_id: Explicit tenant scope requested by the client.

        Returns:
            OrganizationSummaryResponse: Active authorized organization.

        Raises:
            TenancyError: With 404 for absent/foreign scope and 403 for known
                suspended scope, inactive membership, or mismatched roles.
        """
        async with self._sessions()() as session:
            repository = TenancyRepository(session)
            subject = await repository.ensure_subject(principal.subject_id)
            self._require_active_subject(subject.status)
            membership = await repository.get_membership(organization_id, principal.subject_id)
            if membership is None:
                raise self._not_found()
            organization = await repository.get_organization(organization_id)
            if organization is None:
                raise self._not_found()
            self._require_active_scope(organization.status, membership.status)
            roles = await repository.get_membership_roles(organization_id, membership.id)
            if not compatible_membership_roles(principal.roles, roles):
                raise TenancyError(403, "organization_access_denied", "Organization access is not active")
            await session.commit()
        return self._summary(organization)

    async def _require_platform_access(
        self,
        repository: TenancyRepository,
        principal: BookingPrincipal,
    ) -> None:
        """Require active subject, coarse role, and app-owned platform grant.

        Args:
            repository: Transaction-bound tenancy repository.
            principal: Verified request-scoped principal.

        Returns:
            None: Successful return means both authorization gates are active.

        Raises:
            TenancyError: With 403 when any required gate is absent.
        """
        subject = await repository.ensure_subject(principal.subject_id)
        self._require_active_subject(subject.status)
        access = await repository.get_platform_access(principal.subject_id)
        if BookingRole.PLATFORM_ADMIN not in principal.roles or access is None:
            raise TenancyError(403, "platform_access_denied", "Platform access is not active")
        if access.status != PlatformAccessStatus.ACTIVE.value:
            raise TenancyError(403, "platform_access_denied", "Platform access is not active")

    @staticmethod
    def _platform_capabilities(
        principal: BookingPrincipal,
        access: object | None,
    ) -> tuple[BookingCapability, ...]:
        """Derive platform capabilities from both authorization gates.

        Args:
            principal: Verified subject and coarse roles.
            access: Optional app-owned platform-access ORM row.

        Returns:
            tuple[BookingCapability, ...]: One management capability or empty.
        """
        is_active = getattr(access, "status", None) == PlatformAccessStatus.ACTIVE.value
        if BookingRole.PLATFORM_ADMIN in principal.roles and is_active:
            return (BookingCapability.MANAGE_PLATFORM_ORGANIZATIONS,)
        return ()

    @staticmethod
    def _context_revision(
        subject_revision: int,
        platform_access: object | None,
        organizations: tuple[OrganizationMembershipContextResponse, ...],
    ) -> str:
        """Build an opaque deterministic digest from non-secret revisions.

        Args:
            subject_revision: Current app-owned subject revision.
            platform_access: Optional app-owned platform grant.
            organizations: Effective active organization contexts.

        Returns:
            str: SHA-256 digest suitable only for stale-state detection.
        """
        payload = {
            "subject": subject_revision,
            "platform": getattr(platform_access, "revision", 0),
            "organizations": [
                [item.organization.organization_id, item.organization.revision, item.membership_revision]
                for item in organizations
            ],
        }
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _summary(organization: BookingOrganization) -> OrganizationSummaryResponse:
        """Convert an ORM tenant to its sanitized response shape.

        Args:
            organization: Persisted tenant row.

        Returns:
            OrganizationSummaryResponse: Safe public tenant fields.
        """
        return OrganizationSummaryResponse(
            organization_id=organization.id,
            display_name=organization.display_name,
            status=OrganizationStatus(organization.status),
            revision=organization.revision,
        )

    @staticmethod
    def _require_active_subject(subject_status: str) -> None:
        """Reject a non-active app-owned subject.

        Args:
            subject_status: Persisted subject lifecycle value.

        Returns:
            None: Successful return means the subject is active.

        Raises:
            TenancyError: With 403 when the subject cannot operate.
        """
        if subject_status != SubjectStatus.ACTIVE.value:
            raise TenancyError(403, "subject_inactive", "Booking access is not active")

    @staticmethod
    def _require_active_scope(organization_status: str, membership_status: str) -> None:
        """Reject known organization scope that cannot accept operations.

        Args:
            organization_status: Persisted tenant lifecycle value.
            membership_status: Persisted membership lifecycle value.

        Returns:
            None: Successful return means both scope gates are active.

        Raises:
            TenancyError: With 403 when either lifecycle gate is inactive.
        """
        if organization_status != OrganizationStatus.ACTIVE.value:
            raise TenancyError(403, "organization_suspended", "Organization access is not active")
        if membership_status != MembershipStatus.ACTIVE.value:
            raise TenancyError(403, "membership_inactive", "Organization access is not active")

    @staticmethod
    def _not_found() -> TenancyError:
        """Build the uniform private-resource not-found response.

        Returns:
            TenancyError: Safe 404 that does not reveal tenant existence.
        """
        return TenancyError(404, "organization_not_found", "Organization was not found")
