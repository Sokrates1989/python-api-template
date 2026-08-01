"""Validated contracts for scoped membership administration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.booking_service.domain.tenancy import (
    MEMBERSHIP_ROLE_ORDER,
    MembershipRole,
    MembershipStatus,
)


class IdentitySyncStatus(StrEnum):
    """Expose durable provider synchronization without provider payloads."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MembershipInvitationRequest(BaseModel):
    """Create an app-owned invitation for an immutable provider subject.

    Attributes:
        subject_id: Immutable provider subject; usernames and emails are not accepted.
        roles: Complete initial organization role set.
    """

    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=255)
    roles: tuple[MembershipRole, ...] = Field(min_length=1)

    @field_validator("subject_id")
    @classmethod
    def validate_subject_id(cls, value: str) -> str:
        """Trim and reject whitespace-bearing identity keys.

        Args:
            value: Pydantic length-checked subject identifier.

        Returns:
            str: Trimmed immutable subject identifier.

        Raises:
            ValueError: When the value is blank or contains whitespace.
        """
        normalized = value.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("subject_id must be one opaque identifier")
        return normalized

    @field_validator("roles")
    @classmethod
    def validate_roles(
        cls,
        value: tuple[MembershipRole, ...],
    ) -> tuple[MembershipRole, ...]:
        """Deduplicate and order an initial role set.

        Args:
            value: Parsed non-empty membership roles.

        Returns:
            tuple[MembershipRole, ...]: Unique roles in canonical order.
        """
        selected = set(value)
        return tuple(role for role in MEMBERSHIP_ROLE_ORDER if role in selected)


class MembershipUpdateRequest(BaseModel):
    """Replace roles and lifecycle state using optimistic concurrency.

    Attributes:
        expected_revision: Membership revision last observed by the caller.
        status: Complete desired membership lifecycle state.
        roles: Complete desired app-owned organization role set.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    status: MembershipStatus
    roles: tuple[MembershipRole, ...] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def validate_roles(
        cls,
        value: tuple[MembershipRole, ...],
    ) -> tuple[MembershipRole, ...]:
        """Deduplicate and order a replacement role set.

        Args:
            value: Parsed non-empty membership roles.

        Returns:
            tuple[MembershipRole, ...]: Unique roles in canonical order.
        """
        selected = set(value)
        return tuple(role for role in MEMBERSHIP_ROLE_ORDER if role in selected)


class MembershipIdentitySyncResponse(BaseModel):
    """Describe durable identity synchronization with safe recovery metadata.

    Attributes:
        status: Current outbox delivery state or ``not_required``.
        retryable: Whether another explicit retry can succeed.
        error_code: Optional sanitized provider failure code.
    """

    model_config = ConfigDict(frozen=True)

    status: IdentitySyncStatus
    retryable: bool
    error_code: str | None = None


class MembershipSummaryResponse(BaseModel):
    """Expose one tenant-scoped membership without profile or token payloads.

    Attributes:
        membership_id: App-owned membership identifier.
        subject_id: Immutable provider subject identifier.
        status: App-owned membership lifecycle state.
        roles: Complete stored organization role set.
        revision: Monotonic optimistic-concurrency revision.
        identity_sync: Latest provider-delivery recovery state.
    """

    model_config = ConfigDict(frozen=True)

    membership_id: str
    subject_id: str
    status: MembershipStatus
    roles: tuple[MembershipRole, ...]
    revision: int
    identity_sync: MembershipIdentitySyncResponse
