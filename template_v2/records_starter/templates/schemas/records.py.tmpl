"""Bounded request and response schemas for generated records routes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _RecordFields(BaseModel):
    """Validate the shared mutable fields of a neutral record."""

    title: str = Field(min_length=1, max_length=120)
    details: str | None = Field(default=None, max_length=4000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Trim and reject a whitespace-only record title.

        Args:
            cls: Pydantic model class performing validation.
            value: Length-bounded candidate title.

        Returns:
            Trimmed non-empty title.

        Raises:
            ValueError: If the title contains only whitespace.
        """

        normalized = value.strip()
        if not normalized:
            raise ValueError("title must contain a visible character")
        return normalized


class RecordCreateRequest(_RecordFields):
    """Validate creation fields for a neutral record."""


class RecordUpdateRequest(_RecordFields):
    """Validate a complete optimistic record update."""

    title: str = Field(min_length=1, max_length=120)
    details: str | None = Field(default=None, max_length=4000)
    expected_revision: int = Field(ge=1)


class RecordResponse(BaseModel):
    """Expose one owned record without its internal owner subject."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    details: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class RecordListResponse(BaseModel):
    """Expose a deterministic subject-scoped records page."""

    items: list[RecordResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class RecordDeleteResponse(BaseModel):
    """Report idempotent deletion without disclosing foreign records."""

    deleted: bool


class RecordErrorDetail(BaseModel):
    """Describe one stable application-level records error."""

    code: str
    message: str
    retryable: bool
    current_revision: int | None = Field(default=None, ge=1)
