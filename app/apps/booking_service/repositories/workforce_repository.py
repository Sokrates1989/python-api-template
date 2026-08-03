"""Tenant-scoped persistence and eligibility queries for BKG-202 workers."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from apps.booking_service.models.company_settings import BookingLocation
from apps.booking_service.models.service_catalog import (
    BookingServiceLocationOffering,
    BookingServiceOffering,
)
from apps.booking_service.models.tenancy import (
    OrganizationMembership,
    OrganizationMembershipRole,
)
from apps.booking_service.models.workforce import (
    BookingWorkerLocationAssignment,
    BookingWorkerProfile,
    BookingWorkerServiceQualification,
)
from apps.booking_service.schemas.workforce import (
    WorkerProfileFields,
    WorkerQualificationInput,
)


def _selectable_specific_services_query(
    organization_id: str,
    required: set[str],
) -> Select[tuple[str]]:
    """Build the tenant-safe query for services with a selectable worker.

    Args:
        organization_id: Tenant owning all joined records.
        required: Published specific-only services requiring coverage.

    Returns:
        Select[tuple[str]]: Distinct service-identifier statement.
    """
    return (
        select(distinct(BookingWorkerServiceQualification.service_offering_id))
        .join(
            BookingWorkerProfile,
            (BookingWorkerProfile.organization_id == organization_id)
            & (BookingWorkerProfile.id == BookingWorkerServiceQualification.worker_profile_id),
        )
        .join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == organization_id)
            & (OrganizationMembership.id == BookingWorkerProfile.membership_id),
        )
        .join(
            OrganizationMembershipRole,
            (OrganizationMembershipRole.organization_id == organization_id)
            & (OrganizationMembershipRole.membership_id == OrganizationMembership.id),
        )
        .join(
            BookingWorkerLocationAssignment,
            (BookingWorkerLocationAssignment.organization_id == organization_id)
            & (BookingWorkerLocationAssignment.worker_profile_id == BookingWorkerProfile.id),
        )
        .join(
            BookingServiceLocationOffering,
            (BookingServiceLocationOffering.organization_id == organization_id)
            & (
                BookingServiceLocationOffering.service_offering_id
                == BookingWorkerServiceQualification.service_offering_id
            )
            & (
                BookingServiceLocationOffering.location_id
                == BookingWorkerLocationAssignment.location_id
            ),
        )
        .where(
            BookingWorkerServiceQualification.organization_id == organization_id,
            BookingWorkerServiceQualification.service_offering_id.in_(required),
            BookingWorkerProfile.status == "active",
            BookingWorkerProfile.is_publicly_bookable.is_(True),
            OrganizationMembership.status == "active",
            OrganizationMembershipRole.role == "worker",
        )
    )


def _eligible_worker_conditions(
    organization_id: str,
    service_offering_id: str,
    location_id: str,
    *,
    automatic: bool,
) -> list[object]:
    """Build candidate predicates for automatic or specific assignment.

    Args:
        organization_id: Tenant owning every joined record.
        service_offering_id: Qualified service requested by availability.
        location_id: Location shared by service and worker.
        automatic: Whether auto eligibility replaces public visibility.

    Returns:
        list[object]: SQLAlchemy boolean predicates for the candidate query.
    """
    conditions: list[object] = [
        BookingWorkerProfile.organization_id == organization_id,
        BookingWorkerProfile.status == "active",
        OrganizationMembership.status == "active",
        OrganizationMembershipRole.role == "worker",
        BookingWorkerServiceQualification.service_offering_id == service_offering_id,
        BookingWorkerLocationAssignment.location_id == location_id,
        BookingServiceLocationOffering.location_id == location_id,
    ]
    eligibility = (
        BookingWorkerServiceQualification.auto_eligible.is_(True)
        if automatic
        else BookingWorkerProfile.is_publicly_bookable.is_(True)
    )
    return [*conditions, eligibility]


def _eligible_workers_query(
    organization_id: str,
    service_offering_id: str,
    location_id: str,
    *,
    automatic: bool,
) -> Select[tuple[str]]:
    """Build the deterministic same-tenant availability candidate query.

    Args:
        organization_id: Tenant owning every joined record.
        service_offering_id: Qualified service requested by availability.
        location_id: Location shared by service and worker.
        automatic: Whether the request is automatic or customer-selected.

    Returns:
        Select[tuple[str]]: Priority and identifier ordered worker statement.
    """
    conditions = _eligible_worker_conditions(
        organization_id,
        service_offering_id,
        location_id,
        automatic=automatic,
    )
    return (
        select(BookingWorkerProfile.id)
        .join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == organization_id)
            & (OrganizationMembership.id == BookingWorkerProfile.membership_id),
        )
        .join(
            OrganizationMembershipRole,
            (OrganizationMembershipRole.organization_id == organization_id)
            & (OrganizationMembershipRole.membership_id == OrganizationMembership.id),
        )
        .join(
            BookingWorkerServiceQualification,
            (BookingWorkerServiceQualification.organization_id == organization_id)
            & (BookingWorkerServiceQualification.worker_profile_id == BookingWorkerProfile.id),
        )
        .join(
            BookingWorkerLocationAssignment,
            (BookingWorkerLocationAssignment.organization_id == organization_id)
            & (BookingWorkerLocationAssignment.worker_profile_id == BookingWorkerProfile.id),
        )
        .join(
            BookingServiceLocationOffering,
            (BookingServiceLocationOffering.organization_id == organization_id)
            & (BookingServiceLocationOffering.service_offering_id == service_offering_id),
        )
        .where(*conditions)
        .order_by(
            BookingWorkerServiceQualification.priority,
            BookingWorkerProfile.id,
        )
    )


class WorkforceRepository:
    """Persist and query one tenant's explicit worker configuration."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind all operations to the caller-owned [session].

        Args:
            session: Transactional asynchronous SQLAlchemy session.

        Returns:
            None: The repository retains the session without committing.
        """
        self._session = session

    async def list_profiles(
        self,
        organization_id: str,
        *,
        membership_id: str | None = None,
        include_inactive: bool,
    ) -> tuple[BookingWorkerProfile, ...]:
        """List tenant workers, optionally restricted to one membership.

        Args:
            organization_id: Tenant that must own every returned profile.
            membership_id: Optional self-summary membership restriction.
            include_inactive: Whether lifecycle recovery rows remain visible.

        Returns:
            tuple[BookingWorkerProfile, ...]: Stable name/identifier ordered rows.
        """
        conditions = [BookingWorkerProfile.organization_id == organization_id]
        if membership_id is not None:
            conditions.append(BookingWorkerProfile.membership_id == membership_id)
        if not include_inactive:
            conditions.append(BookingWorkerProfile.status == "active")
        result = await self._session.execute(
            select(BookingWorkerProfile)
            .where(*conditions)
            .order_by(BookingWorkerProfile.public_name, BookingWorkerProfile.id)
        )
        return tuple(result.scalars().all())

    async def get_profile(
        self,
        organization_id: str,
        worker_profile_id: str,
    ) -> BookingWorkerProfile | None:
        """Load one worker through both tenant and resource identifiers.

        Args:
            organization_id: Tenant that must own the worker.
            worker_profile_id: Exact profile identifier.

        Returns:
            BookingWorkerProfile | None: Matching row or ``None``.
        """
        result = await self._session.execute(
            select(BookingWorkerProfile).where(
                BookingWorkerProfile.organization_id == organization_id,
                BookingWorkerProfile.id == worker_profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_profile_by_membership(
        self,
        organization_id: str,
        membership_id: str,
    ) -> BookingWorkerProfile | None:
        """Load the unique profile already attached to one membership.

        Args:
            organization_id: Tenant that must own the profile and membership.
            membership_id: Exact membership identifier.

        Returns:
            BookingWorkerProfile | None: Existing profile or ``None``.
        """
        result = await self._session.execute(
            select(BookingWorkerProfile).where(
                BookingWorkerProfile.organization_id == organization_id,
                BookingWorkerProfile.membership_id == membership_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_profile_for_update(
        self,
        organization_id: str,
        worker_profile_id: str,
    ) -> BookingWorkerProfile | None:
        """Lock one tenant worker for optimistic replacement or lifecycle work.

        Args:
            organization_id: Tenant that must own the worker.
            worker_profile_id: Exact profile identifier.

        Returns:
            BookingWorkerProfile | None: Locked row or ``None``.
        """
        result = await self._session.execute(
            select(BookingWorkerProfile)
            .where(
                BookingWorkerProfile.organization_id == organization_id,
                BookingWorkerProfile.id == worker_profile_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def create_profile(
        self,
        organization_id: str,
        membership_id: str,
        fields: WorkerProfileFields,
    ) -> BookingWorkerProfile:
        """Stage one active profile without implicit assignments.

        Args:
            organization_id: Tenant owning the worker.
            membership_id: Existing worker-role membership.
            fields: Validated presentation and explicit assignment state.

        Returns:
            BookingWorkerProfile: Newly staged first revision.
        """
        values = fields.model_dump(
            mode="python",
            exclude={"membership_id", "location_ids", "qualifications"},
        )
        profile = BookingWorkerProfile(
            id=str(uuid4()),
            organization_id=organization_id,
            membership_id=membership_id,
            status="active",
            revision=1,
            **values,
        )
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_membership(
        self,
        organization_id: str,
        membership_id: str,
    ) -> OrganizationMembership | None:
        """Load one membership through the worker's explicit tenant scope.

        Args:
            organization_id: Tenant that must own the membership.
            membership_id: Exact app-owned membership identifier.

        Returns:
            OrganizationMembership | None: Matching membership or ``None``.
        """
        result = await self._session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id == membership_id,
            )
        )
        return result.scalar_one_or_none()

    async def membership_has_worker_role(
        self,
        organization_id: str,
        membership_id: str,
    ) -> bool:
        """Return whether one tenant membership explicitly carries worker role.

        Args:
            organization_id: Tenant that must own the membership role.
            membership_id: Exact app-owned membership identifier.

        Returns:
            bool: True only for a same-tenant stored worker role.
        """
        result = await self._session.execute(
            select(OrganizationMembershipRole.role).where(
                OrganizationMembershipRole.organization_id == organization_id,
                OrganizationMembershipRole.membership_id == membership_id,
                OrganizationMembershipRole.role == "worker",
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_location_ids(
        self,
        organization_id: str,
        worker_profile_id: str,
    ) -> tuple[str, ...]:
        """List one worker's explicit same-tenant locations.

        Args:
            organization_id: Tenant owning the assignment.
            worker_profile_id: Worker owning the assignment.

        Returns:
            tuple[str, ...]: Sorted location identifiers.
        """
        result = await self._session.execute(
            select(BookingWorkerLocationAssignment.location_id)
            .where(
                BookingWorkerLocationAssignment.organization_id == organization_id,
                BookingWorkerLocationAssignment.worker_profile_id == worker_profile_id,
            )
            .order_by(BookingWorkerLocationAssignment.location_id)
        )
        return tuple(result.scalars().all())

    async def list_qualifications(
        self,
        organization_id: str,
        worker_profile_id: str,
    ) -> tuple[BookingWorkerServiceQualification, ...]:
        """List one worker's deterministic service qualifications.

        Args:
            organization_id: Tenant owning every qualification.
            worker_profile_id: Worker owning every qualification.

        Returns:
            tuple[BookingWorkerServiceQualification, ...]: Service-ordered rows.
        """
        result = await self._session.execute(
            select(BookingWorkerServiceQualification)
            .where(
                BookingWorkerServiceQualification.organization_id == organization_id,
                BookingWorkerServiceQualification.worker_profile_id == worker_profile_id,
            )
            .order_by(BookingWorkerServiceQualification.service_offering_id)
        )
        return tuple(result.scalars().all())

    async def replace_locations(
        self,
        organization_id: str,
        worker_profile_id: str,
        location_ids: tuple[str, ...],
    ) -> None:
        """Replace all explicit worker locations without implicit defaults.

        Args:
            organization_id: Tenant owning every association.
            worker_profile_id: Worker receiving the complete assignment set.
            location_ids: Validated active same-tenant locations; may be empty.

        Returns:
            None: Changes remain staged in the caller transaction.
        """
        await self._session.execute(
            delete(BookingWorkerLocationAssignment).where(
                BookingWorkerLocationAssignment.organization_id == organization_id,
                BookingWorkerLocationAssignment.worker_profile_id == worker_profile_id,
            )
        )
        self._session.add_all(
            [
                BookingWorkerLocationAssignment(
                    organization_id=organization_id,
                    worker_profile_id=worker_profile_id,
                    location_id=location_id,
                )
                for location_id in location_ids
            ]
        )
        await self._session.flush()

    async def replace_qualifications(
        self,
        organization_id: str,
        worker_profile_id: str,
        qualifications: tuple[WorkerQualificationInput, ...],
    ) -> None:
        """Replace all worker/service qualifications atomically.

        Args:
            organization_id: Tenant owning every association.
            worker_profile_id: Worker receiving the complete qualification set.
            qualifications: Validated service, auto, and priority values.

        Returns:
            None: Changes remain staged in the caller transaction.
        """
        await self._session.execute(
            delete(BookingWorkerServiceQualification).where(
                BookingWorkerServiceQualification.organization_id == organization_id,
                BookingWorkerServiceQualification.worker_profile_id == worker_profile_id,
            )
        )
        self._session.add_all(
            [
                BookingWorkerServiceQualification(
                    organization_id=organization_id,
                    worker_profile_id=worker_profile_id,
                    service_offering_id=item.service_offering_id,
                    auto_eligible=item.auto_eligible,
                    priority=item.priority,
                )
                for item in qualifications
            ]
        )
        await self._session.flush()

    async def active_location_ids(
        self,
        organization_id: str,
        requested_ids: tuple[str, ...],
    ) -> frozenset[str]:
        """Resolve exact requested identifiers against active tenant locations.

        Args:
            organization_id: Tenant that must own every location.
            requested_ids: Requested explicit identifiers.

        Returns:
            frozenset[str]: Matching active location identifiers.
        """
        if not requested_ids:
            return frozenset()
        result = await self._session.execute(
            select(BookingLocation.id).where(
                BookingLocation.organization_id == organization_id,
                BookingLocation.status == "active",
                BookingLocation.id.in_(requested_ids),
            )
        )
        return frozenset(result.scalars().all())

    async def active_service_ids(
        self,
        organization_id: str,
        requested_ids: tuple[str, ...],
    ) -> frozenset[str]:
        """Resolve exact requested identifiers against active tenant services.

        Args:
            organization_id: Tenant that must own every service.
            requested_ids: Requested qualification identifiers.

        Returns:
            frozenset[str]: Matching active service identifiers.
        """
        if not requested_ids:
            return frozenset()
        result = await self._session.execute(
            select(BookingServiceOffering.id).where(
                BookingServiceOffering.organization_id == organization_id,
                BookingServiceOffering.status == "active",
                BookingServiceOffering.id.in_(requested_ids),
            )
        )
        return frozenset(result.scalars().all())

    async def published_specific_only_service_ids(
        self,
        organization_id: str,
    ) -> tuple[str, ...]:
        """List published active services that require a specific worker.

        Args:
            organization_id: Tenant owning every service.

        Returns:
            tuple[str, ...]: Stable dependent service identifiers.
        """
        result = await self._session.execute(
            select(BookingServiceOffering.id)
            .where(
                BookingServiceOffering.organization_id == organization_id,
                BookingServiceOffering.status == "active",
                BookingServiceOffering.is_published.is_(True),
                BookingServiceOffering.worker_selection_mode == "specific_only",
            )
            .order_by(BookingServiceOffering.id)
        )
        return tuple(result.scalars().all())

    async def stranded_specific_service_ids(
        self,
        organization_id: str,
    ) -> tuple[str, ...]:
        """Find published specific-only services without one selectable worker.

        Args:
            organization_id: Tenant whose post-mutation state is validated.

        Returns:
            tuple[str, ...]: Stable service IDs that would become unbookable.
        """
        required = set(await self.published_specific_only_service_ids(organization_id))
        if not required:
            return ()
        result = await self._session.execute(
            _selectable_specific_services_query(organization_id, required)
        )
        selectable = set(result.scalars().all())
        return tuple(sorted(required - selectable))

    async def eligible_worker_ids(
        self,
        organization_id: str,
        service_offering_id: str,
        location_id: str,
        *,
        automatic: bool,
    ) -> tuple[str, ...]:
        """Resolve deterministic active candidates for later slot calculation.

        Args:
            organization_id: Tenant owning every joined resource.
            service_offering_id: Qualified service requested later by slots.
            location_id: Explicit location shared by service and worker.
            automatic: Require auto eligibility when true; otherwise require
                customer-visible worker presentation.

        Returns:
            tuple[str, ...]: Priority then worker-ID ordered candidate IDs.
        """
        result = await self._session.execute(
            _eligible_workers_query(
                organization_id,
                service_offering_id,
                location_id,
                automatic=automatic,
            )
        )
        return tuple(result.scalars().all())
