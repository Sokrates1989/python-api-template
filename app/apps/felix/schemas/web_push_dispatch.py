"""Felix authenticated scheduled Web Push request and response schemas.

Clients may submit only predefined product notification kinds, locale, stable
occurrence identity, and timezone-aware UTC delivery time. Visible copy and
routes remain backend-owned and cannot be supplied by callers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FelixWebPushScheduleKind = Literal[
    "checkin",
    "activity",
    "breathing",
    "mindfulness",
    "selfcare",
    "motivation",
    "gratitude",
]
FelixWebPushScheduleLocale = Literal["de", "en"]


class FelixWebPushScheduleOccurrenceRequest(BaseModel):
    """Describe one authenticated future Felix notification occurrence.

    Attributes:
        schedule_key (str): Stable owner-scoped idempotency key.
        kind (FelixWebPushScheduleKind): Predefined backend-rendered message.
        due_at (datetime): Timezone-aware future delivery time.
        locale (FelixWebPushScheduleLocale): Supported copy locale.
    """

    schedule_key: str = Field(
        alias="scheduleKey",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._:%-]+$",
    )
    kind: FelixWebPushScheduleKind
    due_at: datetime = Field(alias="dueAt")
    locale: FelixWebPushScheduleLocale = "de"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def require_timezone(self) -> "FelixWebPushScheduleOccurrenceRequest":
        """Reject timezone-naive delivery timestamps.

        Returns:
            FelixWebPushScheduleOccurrenceRequest: Validated occurrence.

        Raises:
            ValueError: When ``dueAt`` omits timezone information.

        Side Effects:
            None.
        """
        if self.due_at.tzinfo is None or self.due_at.utcoffset() is None:
            raise ValueError("dueAt must include timezone information")
        return self


class FelixWebPushScheduleReplaceRequest(BaseModel):
    """Replace the authenticated account's complete rolling schedule.

    Attributes:
        occurrences (list[FelixWebPushScheduleOccurrenceRequest]): Zero to 60
            predefined future occurrences. An empty list clears the horizon.
    """

    occurrences: list[FelixWebPushScheduleOccurrenceRequest] = Field(
        default_factory=list,
        max_length=60,
    )

    model_config = ConfigDict(extra="forbid")


class FelixWebPushScheduleData(BaseModel):
    """Return count-only durable schedule replacement metadata.

    Attributes:
        scheduled (int): Desired occurrences stored.
        removed (int): Obsolete unleased occurrences removed.
        dispatch_enabled (bool): Whether the deployed worker is enabled.
    """

    scheduled: int
    removed: int
    dispatch_enabled: bool = Field(alias="dispatchEnabled")

    model_config = ConfigDict(populate_by_name=True)


class FelixWebPushScheduleResponse(BaseModel):
    """Envelope one successful authenticated schedule replacement.

    Attributes:
        status (str): Stable success status.
        data (FelixWebPushScheduleData): Count-only replacement result.
    """

    status: str = "success"
    data: FelixWebPushScheduleData
