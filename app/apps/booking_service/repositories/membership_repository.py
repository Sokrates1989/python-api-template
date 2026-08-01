"""Tenant-scoped persistence for membership commands and identity outbox.

Every request-facing lookup includes the organization predicate. Provider
delivery rows retain only opaque identifiers, allowlisted roles, safe error
codes, and retry metadata.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.tenancy import MembershipRole, MembershipStatus
from apps.booking_service.models.tenancy import (
    BookingIdentityRoleOutbox,
    OrganizationMembership,
    OrganizationMembershipRole,
)


class MembershipRepository:
    """Persist membership aggregates within one caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind all operations to [session] without committing it.

        Args:
            session: Async SQLAlchemy session defining transaction ownership.

        Returns:
            None: The repository retains the session reference.
        """
        self._session = session

    async def list_memberships(
        self,
        organization_id: str,
    ) -> tuple[OrganizationMembership, ...]:
        """List every membership in one explicit tenant scope.

        Args:
            organization_id: Organization that must own every returned row.

        Returns:
            tuple[OrganizationMembership, ...]: Memberships ordered by subject.
        """
        result = await self._session.execute(
            select(OrganizationMembership)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.subject_id, OrganizationMembership.id)
        )
        return tuple(result.scalars().all())

    async def get_membership_for_update(
        self,
        organization_id: str,
        membership_id: str,
    ) -> OrganizationMembership | None:
        """Lock one membership through tenant and membership predicates.

        Args:
            organization_id: Tenant that must own the membership.
            membership_id: App-owned membership identifier.

        Returns:
            OrganizationMembership | None: Locked row or ``None``.
        """
        result = await self._session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id == membership_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create_membership(
        self,
        organization_id: str,
        subject_id: str,
    ) -> OrganizationMembership:
        """Stage one invited membership for an existing app-owned subject.

        Args:
            organization_id: Tenant that owns the invitation.
            subject_id: Immutable provider subject identifier.

        Returns:
            OrganizationMembership: Newly staged invitation.
        """
        membership = OrganizationMembership(
            id=str(uuid4()),
            organization_id=organization_id,
            subject_id=subject_id,
            status=MembershipStatus.INVITED.value,
            revision=1,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def active_administrator_count(self, organization_id: str) -> int:
        """Count active memberships carrying the administrator role.

        Args:
            organization_id: Tenant whose required-admin invariant is checked.

        Returns:
            int: Number of distinct active administrator memberships.
        """
        result = await self._session.execute(
            select(func.count(func.distinct(OrganizationMembership.id)))
            .join(
                OrganizationMembershipRole,
                (
                    OrganizationMembershipRole.organization_id
                    == OrganizationMembership.organization_id
                )
                & (
                    OrganizationMembershipRole.membership_id
                    == OrganizationMembership.id
                ),
            )
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
                OrganizationMembershipRole.role
                == MembershipRole.ORGANIZATION_ADMIN.value,
            )
        )
        return int(result.scalar_one())

    async def create_identity_outbox(
        self,
        membership: OrganizationMembership,
        roles: Iterable[MembershipRole],
    ) -> BookingIdentityRoleOutbox:
        """Stage one durable provider-role grant intent.

        Args:
            membership: Tenant-scoped membership receiving coarse roles.
            roles: Newly required allowlisted client roles.

        Returns:
            BookingIdentityRoleOutbox: Pending outbox row.
        """
        row = BookingIdentityRoleOutbox(
            id=str(uuid4()),
            organization_id=membership.organization_id,
            membership_id=membership.id,
            subject_id=membership.subject_id,
            roles=sorted({role.value for role in roles}),
            membership_revision=membership.revision,
            status="pending",
            attempt_count=0,
            retryable=True,
            revision=1,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_identity_outbox(
        self,
        organization_id: str,
        membership_id: str,
    ) -> BookingIdentityRoleOutbox | None:
        """Load the newest identity delivery state for one scoped membership.

        Args:
            organization_id: Tenant that must own the outbox row.
            membership_id: Membership whose latest delivery is requested.

        Returns:
            BookingIdentityRoleOutbox | None: Latest row or ``None``.
        """
        result = await self._session.execute(
            select(BookingIdentityRoleOutbox)
            .where(
                BookingIdentityRoleOutbox.organization_id == organization_id,
                BookingIdentityRoleOutbox.membership_id == membership_id,
            )
            .order_by(
                BookingIdentityRoleOutbox.membership_revision.desc(),
                BookingIdentityRoleOutbox.created_at.desc(),
                BookingIdentityRoleOutbox.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_identity_outbox_for_update(
        self,
        organization_id: str,
        membership_id: str,
        outbox_id: str,
    ) -> BookingIdentityRoleOutbox | None:
        """Lock one exact outbox row through all tenant predicates.

        Args:
            organization_id: Tenant owning the delivery intent.
            membership_id: Membership receiving the role mapping.
            outbox_id: Exact durable delivery identifier.

        Returns:
            BookingIdentityRoleOutbox | None: Locked row or ``None``.
        """
        result = await self._session.execute(
            select(BookingIdentityRoleOutbox)
            .where(
                BookingIdentityRoleOutbox.organization_id == organization_id,
                BookingIdentityRoleOutbox.membership_id == membership_id,
                BookingIdentityRoleOutbox.id == outbox_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def cancel_open_identity_outboxes(
        self,
        organization_id: str,
        membership_id: str,
    ) -> None:
        """Cancel stale pending or failed deliveries for one membership.

        Args:
            organization_id: Tenant that must own affected rows.
            membership_id: Membership whose obsolete work is cancelled.

        Returns:
            None: Changes remain staged in the caller's transaction.
        """
        await self._session.execute(
            update(BookingIdentityRoleOutbox)
            .where(
                BookingIdentityRoleOutbox.organization_id == organization_id,
                BookingIdentityRoleOutbox.membership_id == membership_id,
                BookingIdentityRoleOutbox.status.in_(("pending", "failed")),
            )
            .values(status="cancelled", retryable=False, revision=BookingIdentityRoleOutbox.revision + 1)
        )
        await self._session.flush()
