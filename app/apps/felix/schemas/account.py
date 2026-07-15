"""Schemas for authenticated Felix account deletion responses.

The response exposes only boolean completion markers. It intentionally omits
record counts and provider identifiers so destructive operations do not leak
account structure into client-visible payloads.
"""

from pydantic import BaseModel, ConfigDict, Field


class FelixAccountDeletionData(BaseModel):
    """Describe completed deletion domains without exposing record counts.

    Attributes:
        backend_data_deleted (bool): Whether active provider-owned Felix data
            was permanently removed.
        identity_deleted (bool): Whether the authentication identity was
            deleted or no external provider was configured.
    """

    backend_data_deleted: bool = Field(
        description="Whether active backend account data was deleted."
    )
    identity_deleted: bool = Field(
        description="Whether the configured authentication identity was deleted."
    )

    model_config = ConfigDict(extra="forbid")


class FelixAccountDeletionResponse(BaseModel):
    """Return a stable success envelope for permanent account deletion.

    Attributes:
        status (str): Stable success status for the client envelope.
        message (str): Non-sensitive completion summary.
        data (FelixAccountDeletionData): Explicit completion markers.
    """

    status: str = Field(description="Stable response status.")
    message: str = Field(description="Non-sensitive completion summary.")
    data: FelixAccountDeletionData = Field(
        description="Completed backend and identity deletion markers."
    )

    model_config = ConfigDict(extra="forbid")
