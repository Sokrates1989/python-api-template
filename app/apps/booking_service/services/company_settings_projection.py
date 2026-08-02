"""Sanitized response and audit projections for company configuration."""

from __future__ import annotations

from apps.booking_service.domain.company_settings import (
    LocationStatus,
    PaymentConfigurationStatus,
    WorkerSelectionMode,
)
from apps.booking_service.models.company_settings import (
    BookingCompanySettings,
    BookingLocation,
)
from apps.booking_service.schemas.company_settings import (
    CompanySettingsResponse,
    LocationResponse,
)


def location_response(location: BookingLocation) -> LocationResponse:
    """Convert one location row to its sanitized API representation.

    Args:
        location: Persisted tenant-owned location.

    Returns:
        LocationResponse: Public business fields and optimistic revision.
    """
    return LocationResponse(
        location_id=location.id,
        display_name=location.display_name,
        timezone=location.timezone,
        address_line_1=location.address_line_1,
        address_line_2=location.address_line_2,
        postal_code=location.postal_code,
        locality=location.locality,
        region=location.region,
        country_code=location.country_code,
        contact_email=location.contact_email,
        contact_phone=location.contact_phone,
        status=LocationStatus(location.status),
        revision=location.revision,
    )


def company_settings_response(
    settings: BookingCompanySettings,
    locations: tuple[BookingLocation, ...],
) -> CompanySettingsResponse:
    """Build one complete settings response with active locations only.

    Args:
        settings: Persisted company settings row.
        locations: Active locations already scoped to the same tenant.

    Returns:
        CompanySettingsResponse: Public profile, booking policy, and locations.
    """
    return CompanySettingsResponse(
        organization_id=settings.organization_id,
        public_name=settings.public_name,
        description=settings.description,
        contact_email=settings.contact_email,
        contact_phone=settings.contact_phone,
        website_url=settings.website_url,
        default_timezone=settings.default_timezone,
        default_locale=settings.default_locale,
        currency=settings.currency,
        booking_horizon_days=settings.booking_horizon_days,
        minimum_notice_minutes=settings.minimum_notice_minutes,
        cancellation_notice_minutes=settings.cancellation_notice_minutes,
        reschedule_notice_minutes=settings.reschedule_notice_minutes,
        worker_selection_mode=WorkerSelectionMode(settings.worker_selection_mode),
        payment_configuration_status=PaymentConfigurationStatus.NOT_CONFIGURED,
        revision=settings.revision,
        locations=tuple(location_response(location) for location in locations),
    )


def settings_audit_state(settings: BookingCompanySettings) -> dict[str, object]:
    """Build the complete credential-free settings audit snapshot.

    Args:
        settings: Persisted company settings row.

    Returns:
        dict[str, object]: JSON-compatible business configuration and revision.
    """
    response = company_settings_response(settings, ())
    state = response.model_dump(mode="json")
    state.pop("organization_id")
    state.pop("locations")
    return state


def location_audit_state(location: BookingLocation) -> dict[str, object]:
    """Build a credential-free location audit snapshot.

    Args:
        location: Persisted tenant-owned location.

    Returns:
        dict[str, object]: JSON-compatible location fields and revision.
    """
    return location_response(location).model_dump(mode="json")
