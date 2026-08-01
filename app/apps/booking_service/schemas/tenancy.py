"""Validated request and response contracts for Booking Service tenancy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.booking_service.dependencies.identity import BookingRole
from apps.booking_service.domain.tenancy import (
    BookingCapability,
    MembershipRole,
    OrganizationStatus,
)


class OrganizationCreateRequest(BaseModel):
    """Validate the platform operation that creates one organization.

    Attributes:
        display_name: Human-readable tenant name after whitespace trimming.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=160)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        """Trim and reject a display name containing only whitespace.

        Args:
            value: Pydantic length-checked display name.

        Returns:
            str: Trimmed display name.

        Raises:
            ValueError: When trimming leaves an empty value.
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must contain visible characters")
        return normalized


class OrganizationLifecycleRequest(BaseModel):
    """Carry the revision required for an optimistic lifecycle transition.

    Attributes:
        expected_revision: Revision last observed by the caller.
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class OrganizationSummaryResponse(BaseModel):
    """Expose one tenant without membership or identity-provider secrets.

    Attributes:
        organization_id: Stable application-owned organization identifier.
        display_name: Human-readable tenant name.
        status: Current reversible organization lifecycle state.
        revision: Monotonic optimistic-concurrency revision.
    """

    model_config = ConfigDict(frozen=True)

    organization_id: str
    display_name: str
    status: OrganizationStatus
    revision: int


class OrganizationMembershipContextResponse(BaseModel):
    """Expose one active membership and its server-derived capabilities.

    Attributes:
        organization: Sanitized active organization summary.
        membership_roles: Roles surviving coarse/app-owned intersection.
        capabilities: Capabilities derived from effective membership roles.
        membership_revision: Current app-owned membership revision.
    """

    model_config = ConfigDict(frozen=True)

    organization: OrganizationSummaryResponse
    membership_roles: tuple[MembershipRole, ...]
    capabilities: tuple[BookingCapability, ...]
    membership_revision: int


class EffectiveContextResponse(BaseModel):
    """Expose the complete fail-closed request context for one subject.

    Attributes:
        subject_id: Immutable Keycloak subject matching the identity response.
        coarse_roles: Verified allowlisted Keycloak client roles.
        platform_capabilities: Capabilities requiring both coarse and app grant.
        organizations: Active compatible memberships only.
        context_revision: Opaque revision used to detect stale tenant state.
    """

    model_config = ConfigDict(frozen=True)

    subject_id: str
    coarse_roles: tuple[BookingRole, ...]
    platform_capabilities: tuple[BookingCapability, ...]
    organizations: tuple[OrganizationMembershipContextResponse, ...]
    context_revision: str
