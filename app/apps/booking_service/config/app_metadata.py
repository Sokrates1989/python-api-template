"""Static non-secret metadata for the booking_service backend app."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendAppConfig:
    """Describes generated backend identity and selected data profile.

    Attributes:
        app_id: Stable backend package and deployment profile identifier.
        display_name: Human-readable application name for diagnostics.
        description: Product-neutral API description from the app blueprint.
        backend_data_profile: Selected database provider profile.
    """

    app_id: str = 'booking_service'
    display_name: str = 'Booking Service'
    description: str = 'A neutral multi-tenant foundation for general service booking.'
    backend_data_profile: str = 'postgresql'


BACKEND_APP_CONFIG = BackendAppConfig()
