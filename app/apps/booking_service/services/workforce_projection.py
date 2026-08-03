"""Sanitized response and audit projections for BKG-202 worker profiles."""

from __future__ import annotations

from apps.booking_service.domain.workforce import WorkerProfileStatus
from apps.booking_service.models.workforce import (
    BookingWorkerProfile,
    BookingWorkerServiceQualification,
)
from apps.booking_service.schemas.workforce import (
    WorkerProfileResponse,
    WorkerQualificationResponse,
)


def worker_profile_response(
    profile: BookingWorkerProfile,
    location_ids: tuple[str, ...],
    qualifications: tuple[BookingWorkerServiceQualification, ...],
    individually_bookable_service_ids: frozenset[str],
) -> WorkerProfileResponse:
    """Build one privacy-minimized worker response.

    Args:
        profile: Persisted tenant-owned worker profile.
        location_ids: Explicit tenant-scoped worker locations.
        qualifications: Explicit tenant-scoped service qualifications.
        individually_bookable_service_ids: Services whose effective company,
            service, worker, membership, and location policy permits selection.

    Returns:
        WorkerProfileResponse: Sanitized versioned worker configuration.
    """
    projected = tuple(
        WorkerQualificationResponse(
            service_offering_id=item.service_offering_id,
            auto_eligible=item.auto_eligible,
            priority=item.priority,
            is_individually_bookable=(
                item.service_offering_id in individually_bookable_service_ids
            ),
        )
        for item in qualifications
    )
    return WorkerProfileResponse(
        organization_id=profile.organization_id,
        worker_profile_id=profile.id,
        membership_id=profile.membership_id,
        status=WorkerProfileStatus(profile.status),
        revision=profile.revision,
        public_name=profile.public_name,
        public_description=profile.public_description,
        is_publicly_bookable=profile.is_publicly_bookable,
        location_ids=location_ids,
        qualifications=projected,
    )


def worker_profile_audit_state(response: WorkerProfileResponse) -> dict[str, object]:
    """Remove tenant identity from one complete credential-free audit snapshot.

    Args:
        response: Sanitized worker projection before or after mutation.

    Returns:
        dict[str, object]: JSON-compatible worker state without tenant repetition.
    """
    state = response.model_dump(mode="json")
    state.pop("organization_id")
    return state
