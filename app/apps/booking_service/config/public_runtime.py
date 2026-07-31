"""Generated public API and OIDC metadata for booking_service.

This module contains no credentials and performs no runtime configuration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicRuntimeConfig:
    """Describes public client/API identity shared with generated Flutter code.

    Attributes:
        api_origin: Public API service origin without a route prefix.
        auth_provider: Selected authentication provider identity.
        issuer_url: Public OIDC issuer used for discovery/JWT validation.
        client_id: Public OIDC client/audience identifier.
        redirect_scheme: Public app callback scheme.
    """

    api_origin: str = 'https://api.booking-service.example'
    auth_provider: str = 'keycloak'
    issuer_url: str = 'https://keycloak.fe-wi.com/realms/booking-service-example'
    client_id: str = 'keycloak'
    redirect_scheme: str = 'bookingservice'


PUBLIC_RUNTIME_CONFIG = PublicRuntimeConfig()
