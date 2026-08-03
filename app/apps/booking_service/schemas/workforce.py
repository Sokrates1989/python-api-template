"""Validated BKG-202 contracts for workforce administration and self-summary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.booking_service.domain.workforce import (
    MAXIMUM_WORKER_LOCATIONS,
    MAXIMUM_WORKER_PRIORITY,
    MAXIMUM_WORKER_QUALIFICATIONS,
    WorkerProfileStatus,
)


def _normalize_optional_text(value: object) -> object:
    """Trim optional public presentation text and collapse blank strings.

    Args:
        value: Unvalidated field input.

    Returns:
        object: Trimmed string, ``None`` for blank text, or the original value.
    """
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


class WorkerQualificationInput(BaseModel):
    """Configure organization-wide service qualification for one worker."""

    model_config = ConfigDict(extra="forbid")

    service_offering_id: str = Field(min_length=1, max_length=36)
    auto_eligible: bool = True
    priority: int = Field(default=100, ge=0, le=MAXIMUM_WORKER_PRIORITY)

    @field_validator("service_offering_id")
    @classmethod
    def normalize_service_id(cls, value: str) -> str:
        """Require one normalized visible service identifier.

        Args:
            value: Service identifier supplied by the caller.

        Returns:
            str: Unchanged normalized identifier.

        Raises:
            ValueError: When surrounding whitespace or blank input is present.
        """
        normalized = value.strip()
        if not normalized or normalized != value:
            raise ValueError("service_offering_id must be normalized")
        return normalized


class WorkerProfileFields(BaseModel):
    """Validate mutable worker presentation and explicit assignments."""

    model_config = ConfigDict(extra="forbid")

    public_name: str | None = Field(default=None, max_length=160)
    public_description: str | None = Field(default=None, max_length=1_000)
    is_publicly_bookable: bool = False
    location_ids: tuple[str, ...] = Field(max_length=MAXIMUM_WORKER_LOCATIONS)
    qualifications: tuple[WorkerQualificationInput, ...] = Field(
        max_length=MAXIMUM_WORKER_QUALIFICATIONS
    )

    @field_validator("public_name", "public_description", mode="before")
    @classmethod
    def normalize_public_text(cls, value: object) -> object:
        """Normalize optional public fields before their length checks.

        Args:
            value: Unvalidated presentation input.

        Returns:
            object: Normalized optional text value.
        """
        return _normalize_optional_text(value)

    @field_validator("location_ids")
    @classmethod
    def normalize_locations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique normalized location identifiers in stable order.

        Args:
            value: Explicit location identifiers supplied by the caller.

        Returns:
            tuple[str, ...]: Sorted unique normalized identifiers.

        Raises:
            ValueError: When any identifier is blank, padded, or duplicated.
        """
        normalized = tuple(item.strip() for item in value)
        if any(not item or item != original for item, original in zip(normalized, value)):
            raise ValueError("location_ids must contain normalized identifiers")
        if len(set(normalized)) != len(normalized):
            raise ValueError("location_ids must not contain duplicates")
        return tuple(sorted(normalized))

    @field_validator("qualifications")
    @classmethod
    def normalize_qualifications(
        cls,
        value: tuple[WorkerQualificationInput, ...],
    ) -> tuple[WorkerQualificationInput, ...]:
        """Reject duplicate services and sort qualifications deterministically.

        Args:
            value: Explicit worker/service qualification inputs.

        Returns:
            tuple[WorkerQualificationInput, ...]: Service-ID ordered inputs.

        Raises:
            ValueError: When one service appears more than once.
        """
        service_ids = [item.service_offering_id for item in value]
        if len(set(service_ids)) != len(service_ids):
            raise ValueError("qualifications must not contain duplicate services")
        return tuple(sorted(value, key=lambda item: item.service_offering_id))

    @model_validator(mode="after")
    def require_public_name(self) -> "WorkerProfileFields":
        """Require a customer-safe name whenever specific booking is enabled.

        Returns:
            WorkerProfileFields: Validated model instance.

        Raises:
            ValueError: When public booking is enabled without a public name.
        """
        if self.is_publicly_bookable and self.public_name is None:
            raise ValueError("public_name is required for public worker booking")
        return self


class WorkerProfileCreateRequest(WorkerProfileFields):
    """Create a worker profile for one existing worker membership."""

    membership_id: str = Field(min_length=1, max_length=36)

    @field_validator("membership_id")
    @classmethod
    def normalize_membership_id(cls, value: str) -> str:
        """Require one normalized same-tenant membership identifier.

        Args:
            value: Membership identifier supplied by the administrator.

        Returns:
            str: Unchanged normalized identifier.

        Raises:
            ValueError: When surrounding whitespace or blank input is present.
        """
        if not value.strip() or value.strip() != value:
            raise ValueError("membership_id must be normalized")
        return value


class WorkerProfileUpdateRequest(WorkerProfileFields):
    """Replace one worker profile using optimistic concurrency."""

    expected_revision: int = Field(ge=1)


class WorkerProfileLifecycleRequest(BaseModel):
    """Carry the observed revision for activation state transitions."""

    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class WorkerQualificationResponse(WorkerQualificationInput):
    """Expose qualification plus effective specific-booking visibility."""

    model_config = ConfigDict(frozen=True)
    is_individually_bookable: bool


class WorkerProfileResponse(BaseModel):
    """Expose one sanitized, versioned worker configuration."""

    model_config = ConfigDict(frozen=True)

    organization_id: str
    worker_profile_id: str
    membership_id: str
    status: WorkerProfileStatus
    revision: int
    public_name: str | None
    public_description: str | None
    is_publicly_bookable: bool
    location_ids: tuple[str, ...]
    qualifications: tuple[WorkerQualificationResponse, ...]
