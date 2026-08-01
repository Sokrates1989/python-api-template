"""Organization-scoped SQLAlchemy access for Booking Service tenancy.

Request-facing organization operations require an explicit organization ID.
Role replacement also includes the organization predicate, so a guessed
membership ID cannot mutate another tenant even before composite constraints
are evaluated by PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.tenancy import MembershipRole
from apps.booking_service.models.tenancy import (
    BookingAuditEvent,
    BookingOrganization,
    BookingPlatformAccess,
    BookingSubject,
    OrganizationMembership,
    OrganizationMembershipRole,
)


class TenancyRepository:
    """Provide explicit persistence operations within one async transaction.

    Attributes:
        session: Caller-owned SQLAlchemy session defining the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to a caller-owned transaction.

        Args:
            session: Async SQLAlchemy session used for every operation.

        Returns:
            None: The repository retains the session without committing it.
        """
        self._session = session

    async def ensure_subject(self, subject_id: str) -> BookingSubject:
        """Load or stage an active app-owned subject idempotently.

        Args:
            subject_id: Verified immutable Keycloak subject.

        Returns:
            BookingSubject: Existing or newly staged subject row.
        """
        subject = await self._session.get(BookingSubject, subject_id)
        if subject is None:
            subject = BookingSubject(subject_id=subject_id, status="active", revision=1)
            self._session.add(subject)
            await self._session.flush()
        return subject

    async def get_platform_access(self, subject_id: str) -> BookingPlatformAccess | None:
        """Load app-owned platform access for one subject.

        Args:
            subject_id: Verified immutable Keycloak subject.

        Returns:
            BookingPlatformAccess | None: Matching grant or ``None``.
        """
        return await self._session.get(BookingPlatformAccess, subject_id)

    async def list_organizations(self) -> tuple[BookingOrganization, ...]:
        """List all organizations for a previously authorized platform actor.

        Returns:
            tuple[BookingOrganization, ...]: Tenants ordered by name and ID.
        """
        result = await self._session.execute(
            select(BookingOrganization).order_by(
                BookingOrganization.display_name, BookingOrganization.id
            )
        )
        return tuple(result.scalars().all())

    async def get_organization(self, organization_id: str) -> BookingOrganization | None:
        """Load one organization by app-owned identifier.

        Args:
            organization_id: Exact tenant identifier.

        Returns:
            BookingOrganization | None: Matching tenant or ``None``.
        """
        return await self._session.get(BookingOrganization, organization_id)

    async def get_organization_for_update(
        self,
        organization_id: str,
    ) -> BookingOrganization | None:
        """Lock one organization for an optimistic lifecycle transition.

        Args:
            organization_id: Exact tenant identifier to lock.

        Returns:
            BookingOrganization | None: Locked tenant or ``None``. The lock is
            held until the caller commits or rolls back the transaction.
        """
        result = await self._session.execute(
            select(BookingOrganization)
            .where(BookingOrganization.id == organization_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create_organization(self, display_name: str) -> BookingOrganization:
        """Stage one active organization with a random identifier.

        Args:
            display_name: Validated human-readable tenant name.

        Returns:
            BookingOrganization: Newly staged tenant.
        """
        organization = BookingOrganization(
            id=str(uuid4()), display_name=display_name, status="active", revision=1
        )
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get_membership(
        self,
        organization_id: str,
        subject_id: str,
    ) -> OrganizationMembership | None:
        """Load one membership through mandatory tenant and subject predicates.

        Args:
            organization_id: Tenant scope that must own the membership.
            subject_id: Verified subject that must own the membership.

        Returns:
            OrganizationMembership | None: Scoped membership or ``None``.
        """
        result = await self._session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.subject_id == subject_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_subject_memberships(
        self,
        subject_id: str,
    ) -> tuple[tuple[OrganizationMembership, BookingOrganization], ...]:
        """List active memberships joined only to active organizations.

        Args:
            subject_id: Verified subject whose context is being projected.

        Returns:
            tuple[tuple[OrganizationMembership, BookingOrganization], ...]:
            Stable name/ID ordered active membership and tenant pairs.
        """
        statement = (
            select(OrganizationMembership, BookingOrganization)
            .join(
                BookingOrganization,
                BookingOrganization.id == OrganizationMembership.organization_id,
            )
            .where(
                OrganizationMembership.subject_id == subject_id,
                OrganizationMembership.status == "active",
                BookingOrganization.status == "active",
            )
            .order_by(BookingOrganization.display_name, BookingOrganization.id)
        )
        result = await self._session.execute(statement)
        return tuple(result.all())

    async def get_membership_roles(
        self,
        organization_id: str,
        membership_id: str,
    ) -> set[MembershipRole]:
        """Load roles through both organization and membership predicates.

        Args:
            organization_id: Tenant scope that must own every returned role.
            membership_id: Membership identifier within that tenant.

        Returns:
            set[MembershipRole]: Known app-owned roles for the membership.
        """
        result = await self._session.execute(
            select(OrganizationMembershipRole.role).where(
                OrganizationMembershipRole.organization_id == organization_id,
                OrganizationMembershipRole.membership_id == membership_id,
            )
        )
        return {MembershipRole(value) for value in result.scalars().all()}

    async def replace_membership_roles(
        self,
        organization_id: str,
        membership_id: str,
        roles: Iterable[MembershipRole],
    ) -> None:
        """Replace roles using a tenant-scoped delete and composite inserts.

        Args:
            organization_id: Tenant scope that owns the membership.
            membership_id: Membership whose roles are replaced.
            roles: Deduplicated roles to persist.

        Returns:
            None: Changes remain staged in the caller's transaction.
        """
        await self._session.execute(
            delete(OrganizationMembershipRole).where(
                OrganizationMembershipRole.organization_id == organization_id,
                OrganizationMembershipRole.membership_id == membership_id,
            )
        )
        for role in sorted(set(roles), key=lambda value: value.value):
            self._session.add(
                OrganizationMembershipRole(
                    organization_id=organization_id,
                    membership_id=membership_id,
                    role=role.value,
                )
            )
        await self._session.flush()

    async def add_audit_event(
        self,
        *,
        actor_subject_id: str,
        organization_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
        before_state: dict[str, object] | None,
        after_state: dict[str, object] | None,
    ) -> BookingAuditEvent:
        """Stage one successful lifecycle audit event without credentials.

        Args:
            actor_subject_id: Verified actor subject.
            organization_id: Optional affected tenant scope.
            action: Stable lifecycle action name.
            resource_type: Stable affected resource type.
            resource_id: Identifier of the affected resource.
            before_state: Sanitized pre-transition state or ``None``.
            after_state: Sanitized post-transition state or ``None``.

        Returns:
            BookingAuditEvent: Newly staged immutable event.
        """
        event = BookingAuditEvent(
            id=str(uuid4()),
            actor_subject_id=actor_subject_id,
            organization_id=organization_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome="succeeded",
            before_state=before_state,
            after_state=after_state,
        )
        self._session.add(event)
        await self._session.flush()
        return event
