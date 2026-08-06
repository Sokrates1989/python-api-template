"""Validated contracts for authenticated Booking Service user preferences."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.booking_service.domain.preferences import validate_user_locale


class UserPreferencesUpdateRequest(BaseModel):
    """Replace the complete current user preference representation.

    Attributes:
        expected_revision: Revision last observed by the authenticated client.
        preferred_locale: Generated-client locale selected by the account.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    preferred_locale: str = Field(min_length=2, max_length=16)

    @field_validator("preferred_locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        """Normalize and allowlist the requested account locale.

        Args:
            value: Locale tag supplied by the authenticated client.

        Returns:
            Normalized locale supported by generated Booking clients.
        """

        return validate_user_locale(value)


class UserPreferencesResponse(BaseModel):
    """Expose one authenticated account's safe preferences.

    Attributes:
        preferred_locale: Generated-client locale selected by the account.
        revision: Monotonic optimistic-concurrency revision.
    """

    model_config = ConfigDict(frozen=True)

    preferred_locale: str
    revision: int
