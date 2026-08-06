"""Pure user-preference policy for the Booking Service.

The module keeps account presentation preferences separate from Keycloak
identity attributes and organization defaults. It has no persistence or web
dependency, allowing additional clients to reuse the same wire policy.
"""

from __future__ import annotations


SUPPORTED_USER_LOCALES = frozenset({"de", "en"})
"""Locale tags rendered by every generated Booking Service client."""

DEFAULT_USER_LOCALE = "de"
"""Initial account locale for the German-first demonstration deployment."""


def validate_user_locale(value: str) -> str:
    """Normalize and validate one persisted account locale.

    Args:
        value: Locale tag supplied by an authenticated Booking client.

    Returns:
        Lowercase locale tag supported by the generated clients.

    Raises:
        ValueError: When the locale has no matching generated translations.
    """

    normalized = value.strip().lower()
    if normalized not in SUPPORTED_USER_LOCALES:
        raise ValueError("preferred_locale is not supported by this Booking client")
    return normalized
