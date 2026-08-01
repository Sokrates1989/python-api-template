"""Durable Keycloak role delivery for Booking membership commands.

This coordinator owns the provider side effect and its transactional outbox
classification. The membership command service remains responsible for actor
authorization and app-owned role/lifecycle policy.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.tenancy import MembershipRole, MembershipStatus
from apps.booking_service.models.tenancy import (
    BookingIdentityRoleOutbox,
    OrganizationMembership,
)
from apps.booking_service.repositories import MembershipRepository, TenancyRepository
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.identity_administration import (
    IdentityAdministrationAdapter,
    IdentityAdministrationError,
    KeycloakIdentityAdministrationAdapter,
)


SessionFactory = Callable[[], AsyncSession]
"""Construct one caller-owned async database session."""

SessionFactoryResolver = Callable[[], SessionFactory]
"""Resolve the current injected or initialized session constructor."""


class MembershipIdentityDelivery:
    """Attempt and durably classify one narrow identity-role grant."""

    def __init__(
        self,
        session_factory_resolver: SessionFactoryResolver,
        identity_adapter: IdentityAdministrationAdapter | None = None,
    ) -> None:
        """Bind database and provider dependencies without side effects.

        Args:
            session_factory_resolver: Deferred session-constructor resolver.
            identity_adapter: Optional provider adapter override for tests.

        Returns:
            None: Network and database work remain deferred to ``deliver``.
        """
        self._sessions = session_factory_resolver
        self._identity_adapter = identity_adapter or KeycloakIdentityAdministrationAdapter()

    async def deliver(
        self,
        actor_subject_id: str,
        organization_id: str,
        membership_id: str,
        outbox_id: str,
    ) -> None:
        """Attempt provider delivery and persist success or safe failure.

        Args:
            actor_subject_id: Verified actor retained for audit identity only.
            organization_id: Tenant owning the durable work.
            membership_id: Membership receiving provider roles.
            outbox_id: Exact pending or failed outbox row.

        Returns:
            None: The provider outcome is committed to durable state.

        Raises:
            TenancyError: When the outbox becomes stale during delivery.
        """
        subject_id, roles = await self._delivery_payload(
            organization_id, membership_id, outbox_id
        )
        error: IdentityAdministrationError | None = None
        try:
            await self._identity_adapter.ensure_client_roles(subject_id, roles)
        except IdentityAdministrationError as caught:
            error = caught
        await self._finalize_delivery(
            actor_subject_id, organization_id, membership_id, outbox_id, error
        )

    async def _delivery_payload(
        self,
        organization_id: str,
        membership_id: str,
        outbox_id: str,
    ) -> tuple[str, frozenset[MembershipRole]]:
        """Read the opaque subject and allowlisted roles from durable work.

        Args:
            organization_id: Tenant owning the outbox.
            membership_id: Membership receiving roles.
            outbox_id: Exact delivery row.

        Returns:
            tuple[str, frozenset[MembershipRole]]: Immutable subject and roles.

        Raises:
            TenancyError: When the durable row is absent or stale.
        """
        async with self._sessions()() as session:
            repository = MembershipRepository(session)
            outbox = await repository.get_identity_outbox_for_update(
                organization_id, membership_id, outbox_id
            )
            if outbox is None or outbox.status not in {"pending", "failed"}:
                raise self._stale()
            roles = frozenset(MembershipRole(value) for value in outbox.roles)
            return str(outbox.subject_id), roles

    async def _finalize_delivery(
        self,
        actor_subject_id: str,
        organization_id: str,
        membership_id: str,
        outbox_id: str,
        error: IdentityAdministrationError | None,
    ) -> None:
        """Persist one provider attempt and activate a delivered invitation.

        Args:
            actor_subject_id: Verified actor for audit attribution.
            organization_id: Tenant owning membership and outbox.
            membership_id: Membership receiving the delivery result.
            outbox_id: Exact durable delivery row.
            error: Sanitized provider failure or ``None`` on success.

        Returns:
            None: Membership, outbox, and audit changes are committed atomically.

        Raises:
            TenancyError: When concurrent mutation makes delivery stale.
        """
        async with self._sessions()() as session:
            repository = MembershipRepository(session)
            membership = await repository.get_membership_for_update(
                organization_id, membership_id
            )
            outbox = await repository.get_identity_outbox_for_update(
                organization_id, membership_id, outbox_id
            )
            if membership is None or outbox is None:
                raise self._stale()
            if (
                outbox.status not in {"pending", "failed"}
                or outbox.membership_revision != membership.revision
            ):
                raise self._stale()
            self._record_delivery_result(outbox, error)
            if error is None and membership.status == MembershipStatus.INVITED.value:
                await self._activate_invitation(
                    session, actor_subject_id, membership
                )
            await session.commit()

    @staticmethod
    async def _activate_invitation(
        session: AsyncSession,
        actor_subject_id: str,
        membership: OrganizationMembership,
    ) -> None:
        """Activate one delivered invitation and stage its audit event.

        Args:
            session: Current transaction session.
            actor_subject_id: Verified actor for audit attribution.
            membership: Locked membership ORM row.

        Returns:
            None: State and audit remain staged in the current transaction.
        """
        membership.status = MembershipStatus.ACTIVE.value
        membership.revision += 1
        tenancy = TenancyRepository(session)
        await tenancy.add_audit_event(
            actor_subject_id=actor_subject_id,
            organization_id=membership.organization_id,
            action="membership.activated",
            resource_type="membership",
            resource_id=membership.id,
            before_state={"status": MembershipStatus.INVITED.value},
            after_state={"status": MembershipStatus.ACTIVE.value},
        )

    @staticmethod
    def _record_delivery_result(
        outbox: BookingIdentityRoleOutbox,
        error: IdentityAdministrationError | None,
    ) -> None:
        """Apply one sanitized provider outcome to a locked outbox row.

        Args:
            outbox: Locked durable delivery row.
            error: Sanitized provider failure or ``None`` on success.

        Returns:
            None: The ORM row is mutated in the caller's transaction.
        """
        outbox.attempt_count += 1
        outbox.revision += 1
        outbox.status = "failed" if error is not None else "succeeded"
        outbox.last_error_code = error.code if error is not None else None
        outbox.retryable = error.retryable if error is not None else False

    @staticmethod
    def _stale() -> TenancyError:
        """Build a uniform concurrent-delivery conflict.

        Returns:
            TenancyError: Retryable safe conflict without provider details.
        """
        return TenancyError(
            409,
            "identity_sync_stale",
            "Identity synchronization is stale",
            True,
        )
