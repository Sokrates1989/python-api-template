"""Sanitized response contract for the Booking Service identity projection."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from apps.booking_service.dependencies.identity import BookingRole


class EffectiveIdentityResponse(BaseModel):
    """Expose only the stable subject and verified coarse booking roles.

    Attributes:
        subject_id: Immutable external identity-provider subject.
        roles: Independent coarse roles in deterministic contract order. An
            empty tuple is a valid identity with no booking capability.
    """

    model_config = ConfigDict(frozen=True)

    subject_id: str
    roles: tuple[BookingRole, ...]
