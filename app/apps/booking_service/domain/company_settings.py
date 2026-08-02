"""Pure company-settings policy for the Booking Service.

The module owns stable wire enums, initial supported locale/currency sets, and
cross-field booking-policy validation. It has no database or web dependency so
later catalog, availability, and booking slices can reuse the same rules.
"""

from __future__ import annotations

from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class WorkerSelectionMode(StrEnum):
    """Describe how customers may choose a worker for an appointment."""

    NEXT_AVAILABLE_ONLY = "next_available_only"
    SPECIFIC_WORKER_ONLY = "specific_worker_only"
    NEXT_AVAILABLE_OR_SPECIFIC = "next_available_or_specific"


class LocationStatus(StrEnum):
    """Describe the reversible lifecycle of one company location."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class PaymentConfigurationStatus(StrEnum):
    """Expose the deliberately deferred payment-configuration state."""

    NOT_CONFIGURED = "not_configured"


SUPPORTED_COMPANY_LOCALES = frozenset({"de", "en"})
"""Locale tags currently rendered by the generated Booking client."""

SUPPORTED_COMPANY_CURRENCIES = frozenset({"CHF", "EUR", "GBP", "USD"})
"""Initial settlement currencies accepted before the payment phase."""

DEFAULT_COMPANY_TIMEZONE = "Europe/Berlin"
"""Initial IANA timezone for the German-first demo deployment."""

DEFAULT_COMPANY_LOCALE = "de"
"""Initial locale aligned with the generated Booking client."""

DEFAULT_COMPANY_CURRENCY = "EUR"
"""Initial currency for the German-first demo deployment."""

MINIMUM_BOOKING_HORIZON_DAYS = 1
MAXIMUM_BOOKING_HORIZON_DAYS = 730
MAXIMUM_POLICY_NOTICE_MINUTES = 43_200
"""Bounds preventing unusable or computationally unbounded booking policies."""


def validate_iana_timezone(value: str) -> str:
    """Validate and return one canonical-looking IANA timezone identifier.

    Args:
        value: Whitespace-trimmed timezone identifier supplied by a caller.

    Returns:
        str: The validated timezone identifier unchanged.

    Raises:
        ValueError: When the identifier is blank, uses an unsupported alias, or
            is absent from the runtime IANA timezone database.
    """
    normalized = value.strip()
    if not normalized or normalized in {"localtime", "Factory"}:
        raise ValueError("timezone must be a supported IANA identifier")
    try:
        ZoneInfo(normalized)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("timezone must be a supported IANA identifier") from error
    return normalized


def validate_company_locale(value: str) -> str:
    """Normalize and validate a client-supported company locale.

    Args:
        value: Locale tag supplied by an organization administrator.

    Returns:
        str: Lowercase supported locale tag.

    Raises:
        ValueError: When the generated client cannot render the locale.
    """
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_COMPANY_LOCALES:
        raise ValueError("default_locale is not supported by this Booking client")
    return normalized


def validate_company_currency(value: str) -> str:
    """Normalize and validate an initially supported settlement currency.

    Args:
        value: Currency code supplied by an organization administrator.

    Returns:
        str: Uppercase supported currency code.

    Raises:
        ValueError: When the currency is outside the current payment contract.
    """
    normalized = value.strip().upper()
    if normalized not in SUPPORTED_COMPANY_CURRENCIES:
        raise ValueError("currency is not supported by this Booking deployment")
    return normalized


def validate_notice_windows(
    booking_horizon_days: int,
    minimum_notice_minutes: int,
    cancellation_notice_minutes: int,
    reschedule_notice_minutes: int,
) -> None:
    """Require every notice window to fit inside the booking horizon.

    Args:
        booking_horizon_days: Furthest day a customer may book.
        minimum_notice_minutes: Lead time required for a new booking.
        cancellation_notice_minutes: Lead time required for cancellation.
        reschedule_notice_minutes: Lead time required for rescheduling.

    Returns:
        None: Successful return means the policy is internally consistent.

    Raises:
        ValueError: When any notice window is longer than the booking horizon.
    """
    horizon_minutes = booking_horizon_days * 24 * 60
    windows = (
        minimum_notice_minutes,
        cancellation_notice_minutes,
        reschedule_notice_minutes,
    )
    if any(window > horizon_minutes for window in windows):
        raise ValueError("notice windows must fit inside the booking horizon")
