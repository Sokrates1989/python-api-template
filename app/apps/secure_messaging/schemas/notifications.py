"""
Request and response schemas for notification endpoints.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


NotificationLevel = Literal["info", "success", "warning", "error", "critical"]
NotificationProvider = Literal["telegram", "email", "all"]


class NotifyRequest(BaseModel):
    """
    Request schema for sending a notification.

    Attributes:
        app (str): Service identifier sending the notification (1-100 chars).
        level (NotificationLevel): Severity level of the notification.
        title (str): Short notification title (1-200 chars).
        message (str): Detailed notification message (1-4000 chars).
        tags (list[str]): Optional list of categorization tags.
        provider (NotificationProvider): Target provider(s) for delivery.
        sender (str | None): Specific sender name to use (from configured senders).
        to (str | None): Optional override recipient. Uses level-based target from sender config if not specified.

    Returns:
        None: Pydantic model for request validation.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "app": "test",
                "level": "info",
                "title": "Backup completed",
                "message": "The backup job completed successfully.",
                "tags": ["backup"],
                "provider": "telegram",
                "sender": "backup",
            }
        }
    )

    app: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Service identifier (e.g., 'wikijs-backup')",
    )
    level: NotificationLevel = Field(
        default="info",
        description="Severity level: info, success, warning, error, critical",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Notification title",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Detailed notification message",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional categorization tags",
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
        description="Optional recipient override (email or chat ID). Uses level-based target from sender config if not specified.",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags list length and individual tag length."""
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        for tag in v:
            if len(tag) > 50:
                raise ValueError(f"Tag too long (max 50 chars): {tag}")
        return v


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
