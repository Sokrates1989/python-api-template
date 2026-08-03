"""Validated API contracts for versioned timed service offerings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.booking_service.domain.company_settings import validate_company_currency
from apps.booking_service.domain.service_catalog import (
    MAXIMUM_SERVICE_BUFFER_MINUTES,
    MAXIMUM_SERVICE_DURATION_MINUTES,
    MAXIMUM_SERVICE_LOCATIONS,
    MAXIMUM_SERVICE_PRICE_MINOR_UNITS,
    MINIMUM_SERVICE_DURATION_MINUTES,
    ServiceOfferingStatus,
    validate_slot_step,
)


def _normalize_optional_text(value: object) -> object:
    """Trim optional catalog text and collapse blank values.

    Args:
        value: Raw Pydantic field input.

    Returns:
        object: Trimmed string, ``None``, or untouched non-string input.
    """
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


class ServiceOfferingFields(BaseModel):
    """Validate mutable fields shared by create and replacement commands.

    Attributes:
        name: Customer-visible service name.
        description: Optional customer-visible explanation.
        category: Optional customer-visible grouping label.
        duration_minutes: Customer-visible elapsed appointment duration.
        setup_buffer_minutes: Exclusive worker time before the appointment.
        cleanup_buffer_minutes: Exclusive worker time after the appointment.
        slot_step_minutes: Local scheduling-grid increment.
        price_minor_units: Non-negative price in integer minor currency units.
        currency: Supported ISO-style currency matching company policy.
        is_published: Whether an active service may appear in discovery.
        location_ids: One or more explicit active same-tenant locations.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    category: str | None = Field(default=None, max_length=120)
    duration_minutes: int = Field(
        ge=MINIMUM_SERVICE_DURATION_MINUTES,
        le=MAXIMUM_SERVICE_DURATION_MINUTES,
    )
    setup_buffer_minutes: int = Field(ge=0, le=MAXIMUM_SERVICE_BUFFER_MINUTES)
    cleanup_buffer_minutes: int = Field(ge=0, le=MAXIMUM_SERVICE_BUFFER_MINUTES)
    slot_step_minutes: int
    price_minor_units: int = Field(ge=0, le=MAXIMUM_SERVICE_PRICE_MINOR_UNITS)
    currency: str = Field(min_length=3, max_length=3)
    is_published: bool
    location_ids: tuple[str, ...] = Field(
        min_length=1,
        max_length=MAXIMUM_SERVICE_LOCATIONS,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Trim and require a visible service name.

        Args:
            value: Pydantic length-checked service name.

        Returns:
            str: Trimmed visible name.

        Raises:
            ValueError: When trimming removes every character.
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must contain visible characters")
        return normalized

    @field_validator("description", "category", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """Normalize optional presentation text before validation.

        Args:
            value: Raw optional catalog value.

        Returns:
            object: Normalized optional value.
        """
        return _normalize_optional_text(value)

    @field_validator("slot_step_minutes")
    @classmethod
    def validate_step(cls, value: int) -> int:
        """Require a supported five-minute scheduling step.

        Args:
            value: Requested step in minutes.

        Returns:
            int: Validated step.
        """
        return validate_slot_step(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Normalize and validate the service currency.

        Args:
            value: Requested service currency code.

        Returns:
            str: Normalized supported currency.
        """
        return validate_company_currency(value)

    @field_validator("location_ids")
    @classmethod
    def validate_locations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize, deduplicate, and deterministically order locations.

        Args:
            value: Requested location identifier sequence.

        Returns:
            tuple[str, ...]: Sorted unique visible identifiers.

        Raises:
            ValueError: When an identifier is blank or duplicated.
        """
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("location_ids must contain visible identifiers")
        if len(set(normalized)) != len(normalized):
            raise ValueError("location_ids must not contain duplicates")
        return tuple(sorted(normalized))


class ServiceOfferingCreateRequest(ServiceOfferingFields):
    """Create one active timed service at explicit locations."""


class ServiceOfferingUpdateRequest(ServiceOfferingFields):
    """Replace one active service through optimistic concurrency.

    Attributes:
        expected_revision: Service revision last observed by the caller.
    """

    expected_revision: int = Field(ge=1)


class ServiceOfferingLifecycleRequest(BaseModel):
    """Carry one observed revision for archive or reactivation.

    Attributes:
        expected_revision: Service revision last observed by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class ServiceOfferingResponse(ServiceOfferingFields):
    """Expose one sanitized tenant-owned service offering.

    Attributes:
        organization_id: Tenant owning the service and every location.
        service_offering_id: Stable app-owned service identifier.
        status: Reversible active or archived lifecycle.
        revision: Monotonic content/lifecycle version used for concurrency and
            future immutable appointment snapshots.
    """

    model_config = ConfigDict(frozen=True)

    organization_id: str
    service_offering_id: str
    status: ServiceOfferingStatus
    revision: int
