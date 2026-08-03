"""Sanitized response and audit projections for timed service offerings."""

from __future__ import annotations

from apps.booking_service.domain.service_catalog import ServiceOfferingStatus
from apps.booking_service.models.service_catalog import BookingServiceOffering
from apps.booking_service.schemas.service_catalog import ServiceOfferingResponse


def service_offering_response(
    offering: BookingServiceOffering,
    location_ids: tuple[str, ...],
) -> ServiceOfferingResponse:
    """Convert one service row and assignments to the public API contract.

    Args:
        offering: Persisted tenant-owned timed service.
        location_ids: Already tenant-scoped explicit location identifiers.

    Returns:
        ServiceOfferingResponse: Sanitized versioned catalog representation.
    """
    return ServiceOfferingResponse(
        organization_id=offering.organization_id,
        service_offering_id=offering.id,
        name=offering.name,
        description=offering.description,
        category=offering.category,
        duration_minutes=offering.duration_minutes,
        setup_buffer_minutes=offering.setup_buffer_minutes,
        cleanup_buffer_minutes=offering.cleanup_buffer_minutes,
        slot_step_minutes=offering.slot_step_minutes,
        price_minor_units=offering.price_minor_units,
        currency=offering.currency,
        is_published=offering.is_published,
        location_ids=location_ids,
        status=ServiceOfferingStatus(offering.status),
        revision=offering.revision,
    )


def service_offering_audit_state(
    offering: BookingServiceOffering,
    location_ids: tuple[str, ...],
) -> dict[str, object]:
    """Build a credential-free complete service snapshot for audit/history.

    Args:
        offering: Persisted service revision.
        location_ids: Location assignments at that revision.

    Returns:
        dict[str, object]: JSON-compatible immutable catalog snapshot.
    """
    state = service_offering_response(offering, location_ids).model_dump(mode="json")
    state.pop("organization_id")
    return state
