"""Request schemas for wellness endpoints."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WellnessCheckInCreateRequest(BaseModel):
    """Schema for creating a new wellness check-in."""

    mood_score: int = Field(..., ge=1, le=10)
    stress_score: int = Field(..., ge=1, le=10)
    energy_score: int = Field(..., ge=1, le=10)
    note: Optional[str] = Field(None, max_length=2000)


class WellnessDiaryEntryCreateRequest(BaseModel):
    """Schema for creating a new diary entry."""

    title: str = Field(..., min_length=1, max_length=120)
    summary: str = Field(..., min_length=1, max_length=2000)
    mood_score: int = Field(..., ge=1, le=10)
    tag_keys: List[str] = Field(default_factory=list, max_length=6)
    related_activity_id: Optional[str] = Field(None, max_length=120)


class WellnessActivityUpdateRequest(BaseModel):
    """Schema for updating mutable activity state."""

    favorite: Optional[bool] = None
