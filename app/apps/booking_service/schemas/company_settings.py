"""Validated API contracts for company settings and reversible locations."""

from __future__ import annotations

from typing import Self
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from apps.booking_service.domain.company_settings import (
    MAXIMUM_BOOKING_HORIZON_DAYS,
    MAXIMUM_POLICY_NOTICE_MINUTES,
    MINIMUM_BOOKING_HORIZON_DAYS,
    LocationStatus,
    PaymentConfigurationStatus,
    WorkerSelectionMode,
    validate_company_currency,
    validate_company_locale,
    validate_iana_timezone,
    validate_notice_windows,
)


def _normalize_optional_text(value: object) -> object:
    """Trim optional strings and collapse blank values to ``None``.

    Args:
        value: Raw Pydantic field input.

    Returns:
        object: Trimmed string, ``None``, or untouched non-string input for
        normal Pydantic type validation.
    """
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


class CompanySettingsUpdateRequest(BaseModel):
    """Replace the complete tenant-owned company profile and booking policy.

    Attributes:
        expected_revision: Settings revision last observed by the caller.
        public_name: Customer-visible company name.
        description: Optional customer-visible company summary.
        contact_email: Optional public business email address.
        contact_phone: Optional public business telephone number.
        website_url: Optional HTTP(S) company website.
        default_timezone: Default IANA timezone for scheduling interpretation.
        default_locale: Locale supported by the generated Booking client.
        currency: Initially supported settlement currency.
        booking_horizon_days: Furthest day customers may book.
        minimum_notice_minutes: Required lead time for new bookings.
        cancellation_notice_minutes: Required lead time for cancellations.
        reschedule_notice_minutes: Required lead time for rescheduling.
        worker_selection_mode: Organization-wide worker-choice default.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    public_name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    website_url: str | None = Field(default=None, max_length=500)
    default_timezone: str = Field(min_length=1, max_length=64)
    default_locale: str = Field(min_length=2, max_length=16)
    currency: str = Field(min_length=3, max_length=3)
    booking_horizon_days: int = Field(
        ge=MINIMUM_BOOKING_HORIZON_DAYS,
        le=MAXIMUM_BOOKING_HORIZON_DAYS,
    )
    minimum_notice_minutes: int = Field(ge=0, le=MAXIMUM_POLICY_NOTICE_MINUTES)
    cancellation_notice_minutes: int = Field(ge=0, le=MAXIMUM_POLICY_NOTICE_MINUTES)
    reschedule_notice_minutes: int = Field(ge=0, le=MAXIMUM_POLICY_NOTICE_MINUTES)
    worker_selection_mode: WorkerSelectionMode

    @field_validator("public_name")
    @classmethod
    def validate_public_name(cls, value: str) -> str:
        """Trim and require visible company-name characters.

        Args:
            value: Pydantic length-checked company name.

        Returns:
            str: Trimmed visible company name.

        Raises:
            ValueError: When trimming leaves an empty value.
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("public_name must contain visible characters")
        return normalized

    @field_validator("description", "contact_phone", "website_url", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """Normalize optional presentation fields before type validation.

        Args:
            value: Raw optional presentation value.

        Returns:
            object: Normalized optional value.
        """
        return _normalize_optional_text(value)

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, value: str | None) -> str | None:
        """Accept only complete HTTP(S) public website URLs.

        Args:
            value: Optional normalized URL.

        Returns:
            str | None: Validated URL or ``None``.

        Raises:
            ValueError: When scheme or host is absent or unsupported.
        """
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("website_url must be a complete HTTP(S) URL")
        return value

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Validate a company default against the runtime IANA database.

        Args:
            value: Requested timezone identifier.

        Returns:
            str: Validated timezone identifier.
        """
        return validate_iana_timezone(value)

    @field_validator("default_locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        """Validate a locale against generated client translations.

        Args:
            value: Requested company locale.

        Returns:
            str: Normalized supported locale.
        """
        return validate_company_locale(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Validate an initially supported settlement currency.

        Args:
            value: Requested currency code.

        Returns:
            str: Normalized supported currency code.
        """
        return validate_company_currency(value)

    @model_validator(mode="after")
    def validate_policy_windows(self) -> Self:
        """Reject notice windows extending beyond the booking horizon.

        Returns:
            Self: This validated complete replacement request.

        Raises:
            ValueError: When one configured notice window exceeds the horizon.
        """
        validate_notice_windows(
            self.booking_horizon_days,
            self.minimum_notice_minutes,
            self.cancellation_notice_minutes,
            self.reschedule_notice_minutes,
        )
        return self


class LocationFields(BaseModel):
    """Validate the reusable mutable fields of one company location.

    Attributes:
        display_name: Customer-visible location label.
        timezone: IANA timezone overriding the company default at this place.
        address_line_1: Optional first physical address line.
        address_line_2: Optional second physical address line.
        postal_code: Optional postal or ZIP code.
        locality: Optional city or locality.
        region: Optional state, province, or region.
        country_code: Optional ISO-style two-letter country code.
        contact_email: Optional location-specific public email.
        contact_phone: Optional location-specific public telephone number.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(min_length=1, max_length=64)
    address_line_1: str | None = Field(default=None, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    postal_code: str | None = Field(default=None, max_length=32)
    locality: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        """Trim and require a visible location name.

        Args:
            value: Pydantic length-checked location name.

        Returns:
            str: Trimmed visible location name.

        Raises:
            ValueError: When trimming leaves no visible character.
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must contain visible characters")
        return normalized

    @field_validator(
        "address_line_1",
        "address_line_2",
        "postal_code",
        "locality",
        "region",
        "country_code",
        "contact_phone",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """Normalize optional location text before type validation.

        Args:
            value: Raw optional location value.

        Returns:
            object: Normalized optional value.
        """
        return _normalize_optional_text(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Validate the location timezone against the IANA database.

        Args:
            value: Requested timezone identifier.

        Returns:
            str: Validated timezone identifier.
        """
        return validate_iana_timezone(value)

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str | None) -> str | None:
        """Normalize an optional alphabetic country code.

        Args:
            value: Optional two-character country code.

        Returns:
            str | None: Uppercase code or ``None``.

        Raises:
            ValueError: When the code contains non-alphabetic characters.
        """
        if value is None:
            return None
        if not value.isalpha():
            raise ValueError("country_code must contain two letters")
        return value.upper()


class LocationCreateRequest(LocationFields):
    """Create one active location from validated mutable fields."""


class LocationUpdateRequest(LocationFields):
    """Replace one location using optimistic concurrency.

    Attributes:
        expected_revision: Location revision last observed by the caller.
    """

    expected_revision: int = Field(ge=1)


class LocationLifecycleRequest(BaseModel):
    """Carry the revision required for a location lifecycle transition.

    Attributes:
        expected_revision: Location revision last observed by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class LocationResponse(LocationFields):
    """Expose one tenant-owned location without provider or payment secrets.

    Attributes:
        location_id: Stable application-owned location identifier.
        status: Reversible active or archived state.
        revision: Monotonic optimistic-concurrency revision.
    """

    model_config = ConfigDict(frozen=True)

    location_id: str
    status: LocationStatus
    revision: int


class CompanySettingsResponse(BaseModel):
    """Expose one complete company profile, policy, and active locations.

    Attributes:
        organization_id: Tenant owning every returned value.
        public_name: Customer-visible company name.
        description: Optional customer-visible company summary.
        contact_email: Optional public business email address.
        contact_phone: Optional public business telephone number.
        website_url: Optional public company website.
        default_timezone: Default IANA scheduling timezone.
        default_locale: Generated-client locale used by default.
        currency: Initially supported settlement currency.
        booking_horizon_days: Furthest bookable day.
        minimum_notice_minutes: Required booking lead time.
        cancellation_notice_minutes: Required cancellation lead time.
        reschedule_notice_minutes: Required rescheduling lead time.
        worker_selection_mode: Organization-wide worker-choice default.
        payment_configuration_status: Explicit placeholder until BKG-700.
        revision: Monotonic settings revision.
        locations: Active locations for members; administrators also receive
            retained archived locations needed for lifecycle recovery.
    """

    model_config = ConfigDict(frozen=True)

    organization_id: str
    public_name: str
    description: str | None
    contact_email: EmailStr | None
    contact_phone: str | None
    website_url: str | None
    default_timezone: str
    default_locale: str
    currency: str
    booking_horizon_days: int
    minimum_notice_minutes: int
    cancellation_notice_minutes: int
    reschedule_notice_minutes: int
    worker_selection_mode: WorkerSelectionMode
    payment_configuration_status: PaymentConfigurationStatus
    revision: int
    locations: tuple[LocationResponse, ...]
