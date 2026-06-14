"""
Request and response schemas for notification endpoints.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


NotificationProvider = Literal["telegram", "email", "all"]


class NotifyRequest(BaseModel):
    """
    Request schema for sending a notification.

    Attributes:
        app (str): Service identifier for internal logging only (1-100 chars).
            Not included in the delivered message content.
        title (str | None): Optional notification title (1-200 chars).
            If provided, rendered bold/larger. For email, becomes the subject.
            If omitted, only the message is sent.
        message (str): Required message content (1-4000 chars).
            Supports markdown formatting. Auto-converted between formats:
            Telegram receives native markdown, email receives HTML.
        provider (NotificationProvider): Target provider(s) for delivery.
        sender (str | None): Specific sender name to use (from configured senders).
            Uses first available sender if not specified.
        to (str | None): Recipient key or direct address.
            If key exists in sender's receivers config, uses that value.
            If not found, used as direct address (email or chat ID).
            Supports comma-separated list for multiple recipients.

    Returns:
        None: Pydantic model for request validation.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "app": "test",
                "title": "Backup completed",
                "message": "The backup job completed successfully.",
                "provider": "all",
                "sender": "backup",
                "to": "info",
            }
        }
    )

    app: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Service identifier for internal logging (not sent in message)",
    )
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Optional title. Bold/larger in output. Becomes email subject.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Required message content (supports markdown)",
    )
    provider: NotificationProvider = Field(
        default="all",
        description="Target provider: telegram, email, all",
    )
    sender: str | None = Field(
        default=None,
        description="Sender name to use (from configured senders). Uses default if not specified.",
    )
    to: str | None = Field(
        default=None,
        description="Recipient key (from sender config) or direct address. Comma-separated for multiple.",
    )


class ProviderResult(BaseModel):
    """
    Result of a single provider delivery attempt.

    Attributes:
        status (str): Delivery status: sent, failed, disabled, skipped.
        sender (str | None): Sender name that was used (if applicable).
        error (str | None): Optional error message (sanitized, no secrets).

    Returns:
        None: Pydantic model for response serialization.
    """

    status: Literal["sent", "failed", "disabled", "skipped"] = Field(
        ...,
        description="Delivery result status",
    )
    sender: str | None = Field(
        default=None,
        description="Sender name used for this delivery",
    )
    error: str | None = Field(
        default=None,
        description="Optional sanitized error message",
    )


class NotifyResponse(BaseModel):
    """
    Response schema for notification endpoint.

    Attributes:
        status (str): Overall status: sent, partial_failure, failed.
        providers (dict[str, ProviderResult]): Per-provider results.

    Returns:
        None: Pydantic model for response serialization.
    """

    status: Literal["sent", "partial_failure", "failed"] = Field(
        ...,
        description="Overall delivery status",
    )
    providers: dict[str, ProviderResult] = Field(
        ...,
        description="Per-provider delivery results",
    )
