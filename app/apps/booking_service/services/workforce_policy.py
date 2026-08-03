"""Cross-resource BKG-202 worker eligibility and mutation safeguards.

The policy module is shared by workforce, catalog, and company-settings
services. It deliberately owns no transaction lifecycle; callers flush before
checking post-mutation state and decide whether to commit or roll back.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.booking_service.domain.company_settings import WorkerSelectionMode
from apps.booking_service.domain.tenancy import MembershipStatus
from apps.booking_service.domain.workforce import (
    ServiceWorkerSelectionMode,
    WorkerProfileStatus,
)
from apps.booking_service.models.company_settings import BookingCompanySettings
from apps.booking_service.models.service_catalog import BookingServiceOffering
from apps.booking_service.models.tenancy import OrganizationMembership
from apps.booking_service.models.workforce import (
    BookingWorkerProfile,
    BookingWorkerServiceQualification,
)
from apps.booking_service.repositories.company_settings_repository import (
    CompanySettingsRepository,
)
from apps.booking_service.repositories.service_catalog_repository import (
    ServiceCatalogRepository,
)
from apps.booking_service.repositories.workforce_repository import WorkforceRepository
from apps.booking_service.schemas.workforce import (
    WorkerProfileCreateRequest,
    WorkerProfileResponse,
    WorkerProfileUpdateRequest,
    WorkerQualificationInput,
)
from apps.booking_service.services.errors import TenancyError
from apps.booking_service.services.workforce_projection import worker_profile_response


async def project_worker_profile(
    session: AsyncSession,
    repository: WorkforceRepository,
    profile: BookingWorkerProfile,
) -> WorkerProfileResponse:
    """Project one worker with server-derived individual-booking flags.

    Args:
        session: Current transaction session.
        repository: Workforce repository bound to the same transaction.
        profile: Tenant-owned worker profile being serialized.

    Returns:
        WorkerProfileResponse: Sanitized worker and effective policy state.
    """
    locations = await repository.list_location_ids(profile.organization_id, profile.id)
    qualifications = await repository.list_qualifications(
        profile.organization_id,
        profile.id,
    )
    individual = await _individual_service_ids(
        session,
        repository,
        profile,
        locations,
        qualifications,
    )
    return worker_profile_response(profile, locations, qualifications, individual)


async def _individual_service_ids(
    session: AsyncSession,
    repository: WorkforceRepository,
    profile: BookingWorkerProfile,
    worker_locations: tuple[str, ...],
    qualifications: tuple[BookingWorkerServiceQualification, ...],
) -> frozenset[str]:
    """Resolve services for which one worker is currently selectable.

    Args:
        session: Current transaction session.
        repository: Workforce repository bound to the transaction.
        profile: Worker whose effective visibility is evaluated.
        worker_locations: Explicit worker location assignments.
        qualifications: Explicit service qualification rows.

    Returns:
        frozenset[str]: Service IDs currently permitting specific booking.
    """
    membership = await repository.get_membership(
        profile.organization_id,
        profile.membership_id,
    )
    settings = await CompanySettingsRepository(session).get_settings(
        profile.organization_id
    )
    if not await _can_present_worker(repository, profile, membership, settings):
        return frozenset()
    return await _visible_service_ids(
        session,
        profile.organization_id,
        worker_locations,
        qualifications,
    )


async def _can_present_worker(
    repository: WorkforceRepository,
    profile: BookingWorkerProfile,
    membership: OrganizationMembership | None,
    settings: BookingCompanySettings | None,
) -> bool:
    """Return whether company, membership, and worker state permit visibility.

    Args:
        repository: Workforce repository used to verify the worker role.
        profile: Worker profile being evaluated.
        membership: Same-tenant membership or ``None`` when it disappeared.
        settings: Company settings row or ``None`` when not initialized.

    Returns:
        bool: True only when the worker may be individually presented.
    """
    if (
        profile.status != WorkerProfileStatus.ACTIVE.value
        or not profile.is_publicly_bookable
        or membership is None
        or membership.status != MembershipStatus.ACTIVE.value
        or settings is None
        or settings.worker_selection_mode
        == WorkerSelectionMode.NEXT_AVAILABLE_ONLY.value
    ):
        return False
    return await repository.membership_has_worker_role(
        profile.organization_id,
        profile.membership_id,
    )


async def _visible_service_ids(
    session: AsyncSession,
    organization_id: str,
    worker_locations: tuple[str, ...],
    qualifications: tuple[BookingWorkerServiceQualification, ...],
) -> frozenset[str]:
    """Resolve published compatible services sharing a worker location.

    Args:
        session: Current transaction session.
        organization_id: Tenant owning every inspected record.
        worker_locations: Explicit worker location assignments.
        qualifications: Explicit service qualification rows.

    Returns:
        frozenset[str]: Service identifiers supporting worker selection.
    """
    catalog = ServiceCatalogRepository(session)
    visible: set[str] = set()
    for qualification in qualifications:
        offering = await catalog.get_offering(
            organization_id,
            qualification.service_offering_id,
        )
        if not _is_visible_specific_service(offering):
            continue
        service_locations = await catalog.list_location_ids(
            organization_id,
            qualification.service_offering_id,
        )
        if set(worker_locations).intersection(service_locations):
            visible.add(qualification.service_offering_id)
    return frozenset(visible)


def _is_visible_specific_service(
    offering: BookingServiceOffering | None,
) -> bool:
    """Return whether one offering currently permits specific-worker booking.

    Args:
        offering: Tenant-scoped service model or ``None``.

    Returns:
        bool: True for active, published, specific-capable services.
    """
    return bool(
        offering is not None
        and offering.status == "active"
        and offering.is_published
        and ServiceWorkerSelectionMode(offering.worker_selection_mode).allows_specific
    )


async def require_worker_membership(
    repository: WorkforceRepository,
    organization_id: str,
    membership_id: str,
    *,
    allow_invited: bool,
) -> OrganizationMembership:
    """Require a same-tenant worker-role membership in allowed lifecycle.

    Args:
        repository: Workforce repository bound to the transaction.
        organization_id: Tenant that must own the membership.
        membership_id: Membership selected by the administrator.
        allow_invited: Whether pre-activation configuration is accepted.

    Returns:
        OrganizationMembership: Matching membership with a worker role.

    Raises:
        TenancyError: When membership, role, or lifecycle is invalid.
    """
    membership = await repository.get_membership(organization_id, membership_id)
    accepted = {MembershipStatus.ACTIVE.value}
    if allow_invited:
        accepted.add(MembershipStatus.INVITED.value)
    if (
        membership is None
        or membership.status not in accepted
        or not await repository.membership_has_worker_role(
            organization_id,
            membership_id,
        )
    ):
        raise TenancyError(
            422,
            "worker_membership_invalid",
            "Worker profile requires a valid worker membership",
        )
    return membership


async def validate_worker_assignments(
    repository: WorkforceRepository,
    organization_id: str,
    request: WorkerProfileCreateRequest | WorkerProfileUpdateRequest,
) -> None:
    """Require every explicit location and service to be active and local.

    Args:
        repository: Workforce repository bound to the transaction.
        organization_id: Tenant owning every requested association.
        request: Validated complete worker configuration.

    Returns:
        None: Successful return proves exact tenant-safe assignments.

    Raises:
        TenancyError: With field-specific detail on any invalid identifier.
    """
    locations = await repository.active_location_ids(
        organization_id,
        request.location_ids,
    )
    if locations != frozenset(request.location_ids):
        raise TenancyError(
            422,
            "worker_locations_invalid",
            "Every worker location must be active in this organization",
        )
    service_ids = tuple(item.service_offering_id for item in request.qualifications)
    services = await repository.active_service_ids(organization_id, service_ids)
    if services != frozenset(service_ids):
        raise TenancyError(
            422,
            "worker_qualifications_invalid",
            "Every worker qualification must use an active organization service",
        )


async def validate_existing_worker_assignments(
    repository: WorkforceRepository,
    organization_id: str,
    worker_profile_id: str,
) -> None:
    """Revalidate retained assignments before worker reactivation.

    Args:
        repository: Workforce repository bound to the transaction.
        organization_id: Tenant owning the worker.
        worker_profile_id: Worker whose retained assignments are checked.

    Returns:
        None: Successful return means retained IDs remain valid.

    Raises:
        TenancyError: When a retained location or service is no longer active.
    """
    locations = await repository.list_location_ids(organization_id, worker_profile_id)
    rows = await repository.list_qualifications(organization_id, worker_profile_id)
    qualifications = tuple(
        WorkerQualificationInput(
            service_offering_id=item.service_offering_id,
            auto_eligible=item.auto_eligible,
            priority=item.priority,
        )
        for item in rows
    )
    request = WorkerProfileUpdateRequest(
        expected_revision=1,
        public_name=None,
        public_description=None,
        is_publicly_bookable=False,
        location_ids=locations,
        qualifications=qualifications,
    )
    await validate_worker_assignments(repository, organization_id, request)


async def require_no_stranded_specific_services(
    session: AsyncSession,
    organization_id: str,
) -> None:
    """Reject state that leaves a published specific-only service empty.

    Args:
        session: Transaction containing the pending cross-resource mutation.
        organization_id: Tenant whose published services are protected.

    Returns:
        None: Successful return means required services remain selectable.

    Raises:
        TenancyError: Actionable conflict naming dependent service identifiers.
    """
    await session.flush()
    stranded = await WorkforceRepository(session).stranded_specific_service_ids(
        organization_id
    )
    if stranded:
        raise TenancyError(
            409,
            "specific_services_would_be_stranded",
            "Published specific-only services require a selectable worker: "
            + ", ".join(stranded),
        )


async def require_company_specific_disable_safe(
    session: AsyncSession,
    organization_id: str,
) -> None:
    """Reject disabling worker choice while specific-only services are public.

    Args:
        session: Current transaction session.
        organization_id: Tenant whose company selection mode is changing.

    Returns:
        None: Successful return means no public service requires worker choice.

    Raises:
        TenancyError: Conflict naming services that must first be changed.
    """
    dependent = await WorkforceRepository(
        session
    ).published_specific_only_service_ids(organization_id)
    if dependent:
        raise TenancyError(
            409,
            "specific_services_require_company_visibility",
            "Change these published specific-only services before disabling worker choice: "
            + ", ".join(dependent),
        )
