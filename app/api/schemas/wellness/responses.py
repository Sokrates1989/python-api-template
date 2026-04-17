"""Response schemas for wellness endpoints."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class WellnessMetricSnapshotResponse(BaseModel):
    """Metric snapshot used by dashboard responses."""

    state_key: str
    score: int = Field(ge=0, le=10)

    model_config = ConfigDict(from_attributes=True)


class WellnessLatestCheckInResponse(BaseModel):
    """Latest wellness check-in payload."""

    recorded_at: str
    mood: WellnessMetricSnapshotResponse
    stress: WellnessMetricSnapshotResponse
    energy: WellnessMetricSnapshotResponse
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessTrendPointResponse(BaseModel):
    """Weekly trend point for dashboard charts."""

    day_key: str
    value: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessDashboardDataResponse(BaseModel):
    """Container for wellness dashboard content."""

    latest_checkin: Optional[WellnessLatestCheckInResponse] = None
    weekly_trend: List[WellnessTrendPointResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessDashboardResponse(BaseModel):
    """Envelope for dashboard responses."""

    status: str
    data: WellnessDashboardDataResponse


class WellnessActivityCategoryResponse(BaseModel):
    """Activity category metadata."""

    key: str
    title_key: str
    description_key: str
    item_count: int

    model_config = ConfigDict(from_attributes=True)


class WellnessActivityItemResponse(BaseModel):
    """Activity catalog item."""

    id: str
    icon_key: str
    title_key: Optional[str] = None
    title: Optional[str] = None
    summary_key: Optional[str] = None
    summary: Optional[str] = None
    duration_minutes: int
    favorite: bool = False
    category_keys: List[str] = []
    energy_impact: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessActivitiesDataResponse(BaseModel):
    """Container for activity catalog responses."""

    categories: List[WellnessActivityCategoryResponse] = []
    items: List[WellnessActivityItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessActivitiesResponse(BaseModel):
    """Envelope for activity catalog responses."""

    status: str
    data: WellnessActivitiesDataResponse


class WellnessDiaryEntryResponse(BaseModel):
    """Diary entry payload."""

    id: str
    title_key: Optional[str] = None
    title: Optional[str] = None
    summary_key: Optional[str] = None
    summary: Optional[str] = None
    mood_state_key: str
    mood_score: int = Field(ge=0, le=10)
    tag_keys: List[str] = []
    related_activity_id: Optional[str] = None
    related_activity_title_key: Optional[str] = None
    related_activity_title: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessDiaryDataResponse(BaseModel):
    """Container for diary responses."""

    items: List[WellnessDiaryEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessDiaryResponse(BaseModel):
    """Envelope for diary responses."""

    status: str
    data: WellnessDiaryDataResponse


class WellnessCheckInMutationResponse(BaseModel):
    """Envelope for check-in creation responses."""

    status: str
    message: str
    data: WellnessLatestCheckInResponse


class WellnessDiaryMutationResponse(BaseModel):
    """Envelope for diary creation responses."""

    status: str
    message: str
    data: WellnessDiaryEntryResponse


class WellnessActivityMutationResponse(BaseModel):
    """Envelope for activity mutation responses."""

    status: str
    message: str
    data: WellnessActivityItemResponse


class WellnessCheckInRecordResponse(BaseModel):
    """Raw check-in record for sync bootstrap payloads."""

    id: str
    recorded_at: str
    mood_score: int = Field(ge=0, le=10)
    stress_score: int = Field(ge=0, le=10)
    energy_score: int = Field(ge=0, le=10)
    note: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncBootstrapDataResponse(BaseModel):
    """Combined wellness payload for initial local bootstrap/sync."""

    server_timestamp: str
    activities: List[WellnessActivityItemResponse] = []
    diary_entries: List[WellnessDiaryEntryResponse] = []
    checkins: List[WellnessCheckInRecordResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncBootstrapResponse(BaseModel):
    """Envelope for sync bootstrap responses."""

    status: str
    data: WellnessSyncBootstrapDataResponse


class WellnessSyncChangeResponse(BaseModel):
    """Single incremental wellness change entry."""

    entity_type: Literal['wellness_activity', 'wellness_diary_entry', 'wellness_checkin']
    entity_id: str
    action: Literal['upsert', 'delete']
    updated_at: str
    payload: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncChangesDataResponse(BaseModel):
    """Incremental wellness pull payload."""

    server_timestamp: str
    changes: List[WellnessSyncChangeResponse] = []
    next_cursor: Optional[str] = None
    has_more: bool = False

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncChangesResponse(BaseModel):
    """Envelope for incremental wellness sync responses."""

    status: str
    data: WellnessSyncChangesDataResponse
