"""Privacy-minimized contracts for authenticated Booking catalog discovery.

The projections deliberately omit memberships, subjects, revisions, audit
state, private contact fields, scheduling buffers, and worker priorities.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from apps.booking_service.domain.workforce import ServiceWorkerSelectionMode


class DiscoveryLocationResponse(BaseModel):
    """Expose one active place used by at least one published service.

    Attributes:
        location_id: Stable app-owned location identifier.
        display_name: Customer-visible location label.
        timezone: IANA timezone used to interpret later availability.
        address_line_1: Optional first public address line.
        address_line_2: Optional second public address line.
        postal_code: Optional public postal code.
        locality: Optional public city or locality.
        region: Optional public state, province, or region.
        country_code: Optional two-letter country code.
    """

    model_config = ConfigDict(frozen=True)

    location_id: str
    display_name: str
    timezone: str
    address_line_1: str | None
    address_line_2: str | None
    postal_code: str | None
    locality: str | None
    region: str | None
    country_code: str | None


class DiscoveryWorkerResponse(BaseModel):
    """Expose one worker who can currently be selected for one service.

    Attributes:
        worker_profile_id: Stable public worker-profile identifier.
        public_name: Customer-visible worker name.
        public_description: Optional customer-visible biography.
        location_ids: Published service locations shared with the worker.
    """

    model_config = ConfigDict(frozen=True)

    worker_profile_id: str
    public_name: str
    public_description: str | None
    location_ids: tuple[str, ...]


class DiscoveryServiceResponse(BaseModel):
    """Expose one active published timed service and selectable workers.

    Attributes:
        service_offering_id: Stable app-owned offering identifier.
        name: Customer-visible service name.
        description: Optional customer-visible service explanation.
        category: Optional public grouping label.
        duration_minutes: Appointment duration shown to customers.
        price_minor_units: Price in integer minor currency units.
        currency: Currency code for the displayed price.
        worker_selection_mode: Service-specific automatic/specific policy.
        location_ids: Active locations explicitly offering the service.
        workers: Currently selectable public workers; empty when policy hides
            individual selection or no worker satisfies effective eligibility.
    """

    model_config = ConfigDict(frozen=True)

    service_offering_id: str
    name: str
    description: str | None
    category: str | None
    duration_minutes: int
    price_minor_units: int
    currency: str
    worker_selection_mode: ServiceWorkerSelectionMode
    location_ids: tuple[str, ...]
    workers: tuple[DiscoveryWorkerResponse, ...]


class DiscoveryOrganizationResponse(BaseModel):
    """Expose one authenticated customer's complete published tenant catalog.

    Attributes:
        organization_id: Stable app-owned company identifier.
        public_name: Customer-visible company name.
        description: Optional public company summary.
        default_locale: Locale preferred by the company.
        currency: Default catalog currency.
        locations: Active locations referenced by published services.
        services: Active published service projections.
    """

    model_config = ConfigDict(frozen=True)

    organization_id: str
    public_name: str
    description: str | None
    default_locale: str
    currency: str
    locations: tuple[DiscoveryLocationResponse, ...]
    services: tuple[DiscoveryServiceResponse, ...]
