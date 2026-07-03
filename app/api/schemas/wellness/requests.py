"""Request schemas for wellness endpoints."""
from __future__ import annotations

from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field

MetricScore = Annotated[int, Field(ge=0, le=10)]
"""Validated 0-10 wellness metric score used by flexible check-in payloads."""


class WellnessCheckInCreateRequest(BaseModel):
    """Schema for creating a new wellness check-in.

    Attributes:
        mood_score (int): Tracked mood score on the inclusive 0-10 Felix metric
            scale. Untracked frontend sentinels must be omitted before this schema.
        stress_score (int): Tracked stress score on the inclusive 0-10 Felix metric
            scale. Untracked frontend sentinels must be omitted before this schema.
        energy_score (int): Tracked energy score on the inclusive 0-10 Felix metric
            scale. Untracked frontend sentinels must be omitted before this schema.
        note (Optional[str]): Optional free-form check-in note.
        recorded_at (Optional[str]): Optional ISO timestamp for when the user
            performed the check-in or activity execution.
        tag_keys (List[str]): Semantic tags persisted with the check-in.
        tags (List[str]): Backward-compatible alias accepted from older clients.
        metrics (Dict[str, MetricScore]): Captured flexible metric values.
            Untracked frontend sentinels must be omitted before this schema.
        activity_id (Optional[str]): Optional linked activity identifier.
    """

    mood_score: int = Field(..., ge=0, le=10)
    stress_score: int = Field(..., ge=0, le=10)
    energy_score: int = Field(..., ge=0, le=10)
    note: Optional[str] = Field(None, max_length=2000)
    recorded_at: Optional[str] = None
    tag_keys: List[str] = Field(default_factory=list, max_length=24)
    tags: List[str] = Field(default_factory=list, max_length=24)
    metrics: Dict[str, MetricScore] = Field(default_factory=dict, max_length=32)
    activity_id: Optional[str] = Field(None, max_length=120)


class WellnessDiaryEntryCreateRequest(BaseModel):
    """Schema for creating a new diary entry.

    Attributes:
        title (str): User-authored diary title.
        summary (str): User-authored diary body or summary.
        mood_score (int): Tracked mood score on the inclusive 0-10 Felix metric
            scale. Untracked frontend sentinels must be omitted before this schema.
        tag_keys (List[str]): Optional semantic tags selected for the entry.
        related_activity_id (Optional[str]): Optional related activity id.
    """

    title: str = Field(..., min_length=1, max_length=120)
    summary: str = Field(..., min_length=1, max_length=2000)
    mood_score: int = Field(..., ge=0, le=10)
    tag_keys: List[str] = Field(default_factory=list, max_length=6)
    related_activity_id: Optional[str] = Field(None, max_length=120)


class WellnessActivityUpdateRequest(BaseModel):
    """Schema for updating mutable activity state."""

    favorite: Optional[bool] = None
