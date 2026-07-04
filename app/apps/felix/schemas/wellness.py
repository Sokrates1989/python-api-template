"""Wellness schemas owned by the Felix backend app.

Felix route request and response contracts live here so product-specific
wellness fields, metric semantics, reward persistence, and diary/check-in
mutation envelopes do not leak into the Python API template's global layer.
"""
from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

FelixMetricScore = Annotated[int, Field(ge=0, le=10)]
"""Validated Felix wellness metric score used by app-owned update payloads."""


class WellnessCheckInCreateRequest(BaseModel):
    """Request model for creating a Felix check-in or activity execution.

    Attributes:
        mood_score (int): Required dashboard-compatible mood score.
        stress_score (int): Required dashboard-compatible stress score.
        energy_score (int): Required dashboard-compatible energy score.
        note (Optional[str]): Optional user-authored note.
        recorded_at (Optional[str]): Optional ISO occurrence timestamp.
        tag_keys (List[str]): Canonical semantic tags.
        tags (List[str]): Backward-compatible tag alias.
        metrics (Dict[str, FelixMetricScore]): Flexible captured metrics.
        activity_id (Optional[str]): Optional linked activity identifier.
    """

    mood_score: int = Field(..., ge=0, le=10)
    stress_score: int = Field(..., ge=0, le=10)
    energy_score: int = Field(..., ge=0, le=10)
    note: Optional[str] = Field(None, max_length=2000)
    recorded_at: Optional[str] = None
    tag_keys: List[str] = Field(default_factory=list, max_length=24)
    tags: List[str] = Field(default_factory=list, max_length=24)
    metrics: Dict[str, FelixMetricScore] = Field(default_factory=dict, max_length=32)
    activity_id: Optional[str] = Field(None, max_length=120)


class WellnessDiaryEntryCreateRequest(BaseModel):
    """Request model for creating a Felix diary entry.

    Attributes:
        title (str): User-authored diary title.
        summary (str): User-authored diary body.
        mood_score (int): User-selected mood score.
        tag_keys (List[str]): Optional semantic tags.
        related_activity_id (Optional[str]): Optional linked activity id.
    """

    title: str = Field(..., min_length=1, max_length=120)
    summary: str = Field(..., min_length=1, max_length=2000)
    mood_score: int = Field(..., ge=0, le=10)
    tag_keys: List[str] = Field(default_factory=list, max_length=6)
    related_activity_id: Optional[str] = Field(None, max_length=120)


class WellnessActivityUpdateRequest(BaseModel):
    """Request model for updating mutable Felix activity state.

    Attributes:
        favorite (Optional[bool]): Optional favorite-state replacement.
    """

    favorite: Optional[bool] = None


class FelixWellnessCheckInUpdateRequest(BaseModel):
    """Request model for updating an existing Felix check-in row.

    Attributes:
        mood_score (Optional[int]): Optional mood score replacement.
        stress_score (Optional[int]): Optional stress score replacement.
        energy_score (Optional[int]): Optional energy score replacement.
        note (Optional[str]): Optional user-authored note replacement.
        recorded_at (Optional[str]): Optional ISO occurrence timestamp.
        tag_keys (Optional[List[str]]): Optional semantic tag replacement.
        tags (Optional[List[str]]): Backward-compatible tag alias.
        metrics (Optional[Dict[str, FelixMetricScore]]): Optional flexible
            metric replacement.
        activity_id (Optional[str]): Optional linked activity replacement.
    """

    mood_score: Optional[int] = Field(None, ge=0, le=10)
    stress_score: Optional[int] = Field(None, ge=0, le=10)
    energy_score: Optional[int] = Field(None, ge=0, le=10)
    note: Optional[str] = Field(None, max_length=2000)
    recorded_at: Optional[str] = None
    tag_keys: Optional[List[str]] = Field(None, max_length=24)
    tags: Optional[List[str]] = Field(None, max_length=24)
    metrics: Optional[Dict[str, FelixMetricScore]] = Field(None, max_length=32)
    activity_id: Optional[str] = Field(None, max_length=120)

    @model_validator(mode="after")
    def require_mutable_field(self) -> "FelixWellnessCheckInUpdateRequest":
        """Ensure the request contains at least one mutable check-in field.

        Returns:
            FelixWellnessCheckInUpdateRequest: The validated request.

        Raises:
            ValueError: When no mutable field was supplied.
        """
        if not self.model_fields_set:
            raise ValueError("At least one check-in field must be provided")
        return self


class FelixWellnessDiaryEntryUpdateRequest(BaseModel):
    """Request model for updating an existing Felix diary entry.

    Attributes:
        title (Optional[str]): Optional user-authored title replacement.
        summary (Optional[str]): Optional user-authored summary replacement.
        mood_score (Optional[int]): Optional mood score replacement.
        tag_keys (Optional[List[str]]): Optional tag replacement.
        related_activity_id (Optional[str]): Optional related activity
            replacement.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=120)
    summary: Optional[str] = Field(None, min_length=1, max_length=2000)
    mood_score: Optional[int] = Field(None, ge=0, le=10)
    tag_keys: Optional[List[str]] = Field(None, max_length=6)
    related_activity_id: Optional[str] = Field(None, max_length=120)

    @model_validator(mode="after")
    def require_mutable_field(self) -> "FelixWellnessDiaryEntryUpdateRequest":
        """Ensure the request contains at least one mutable diary field.

        Returns:
            FelixWellnessDiaryEntryUpdateRequest: The validated request.

        Raises:
            ValueError: When no mutable field was supplied.
        """
        if not self.model_fields_set:
            raise ValueError("At least one diary field must be provided")
        return self


class WellnessMetricSnapshotResponse(BaseModel):
    """Felix metric snapshot used by dashboard responses.

    Attributes:
        state_key (str): User-facing state suffix.
        score (int): Metric score on the inclusive 0-10 scale.
    """

    state_key: str
    score: int = Field(ge=0, le=10)

    model_config = ConfigDict(from_attributes=True)


class WellnessLatestCheckInResponse(BaseModel):
    """Latest Felix check-in payload for dashboard widgets.

    Attributes:
        recorded_at (str): ISO timestamp for the check-in.
        mood (WellnessMetricSnapshotResponse): Mood snapshot.
        stress (WellnessMetricSnapshotResponse): Stress snapshot.
        energy (WellnessMetricSnapshotResponse): Energy snapshot.
        note (Optional[str]): Optional user-authored note.
    """

    recorded_at: str
    mood: WellnessMetricSnapshotResponse
    stress: WellnessMetricSnapshotResponse
    energy: WellnessMetricSnapshotResponse
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessTrendPointResponse(BaseModel):
    """One Felix dashboard trend point.

    Attributes:
        day_key (str): Weekday localization suffix.
        value (Optional[float]): Average score or ``None`` for missing data.
    """

    day_key: str
    value: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessDashboardDataResponse(BaseModel):
    """Container for Felix dashboard content.

    Attributes:
        latest_checkin (Optional[WellnessLatestCheckInResponse]): Latest
            check-in snapshot when one exists.
        weekly_trend (List[WellnessTrendPointResponse]): Seven-day trend.
    """

    latest_checkin: Optional[WellnessLatestCheckInResponse] = None
    weekly_trend: List[WellnessTrendPointResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessDashboardResponse(BaseModel):
    """Envelope for Felix dashboard responses.

    Attributes:
        status (str): Provider-normalized status.
        data (WellnessDashboardDataResponse): Dashboard payload.
    """

    status: str
    data: WellnessDashboardDataResponse


class WellnessActivityCategoryResponse(BaseModel):
    """Felix activity category metadata.

    Attributes:
        key (str): Stable category key.
        title_key (str): Localization key for the title.
        description_key (str): Localization key for the description.
        item_count (int): Number of matching activities.
    """

    key: str
    title_key: str
    description_key: str
    item_count: int

    model_config = ConfigDict(from_attributes=True)


class WellnessActivityItemResponse(BaseModel):
    """Felix activity catalog item.

    Attributes:
        id (str): Stable activity identifier.
        icon_key (str): Material/icon registry key.
        title_key (Optional[str]): Optional title localization key.
        title (Optional[str]): Optional raw title fallback.
        summary_key (Optional[str]): Optional summary localization key.
        summary (Optional[str]): Optional raw summary fallback.
        duration_minutes (int): Suggested activity duration.
        favorite (bool): Whether the user marked this activity as favorite.
        category_keys (List[str]): Activity categories.
        energy_impact (Optional[str]): Stable impact descriptor.
        created_at (Optional[str]): Creation timestamp.
        updated_at (Optional[str]): Update timestamp.
    """

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
    """Container for Felix activity catalog responses.

    Attributes:
        categories (List[WellnessActivityCategoryResponse]): Category metadata.
        items (List[WellnessActivityItemResponse]): Activity rows.
    """

    categories: List[WellnessActivityCategoryResponse] = []
    items: List[WellnessActivityItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessActivitiesResponse(BaseModel):
    """Envelope for Felix activity catalog responses.

    Attributes:
        status (str): Provider-normalized status.
        data (WellnessActivitiesDataResponse): Activity catalog payload.
    """

    status: str
    data: WellnessActivitiesDataResponse


class WellnessDiaryEntryResponse(BaseModel):
    """Felix diary entry payload.

    Attributes:
        id (str): Stable diary entry identifier.
        title_key (Optional[str]): Optional title localization key.
        title (Optional[str]): Optional raw title fallback.
        summary_key (Optional[str]): Optional summary localization key.
        summary (Optional[str]): Optional raw summary fallback.
        mood_state_key (str): Mood state suffix.
        mood_score (int): Mood score.
        tag_keys (List[str]): Semantic tags.
        related_activity_id (Optional[str]): Optional linked activity id.
        related_activity_title_key (Optional[str]): Optional linked title key.
        related_activity_title (Optional[str]): Optional linked raw title.
        created_at (str): Creation timestamp.
        updated_at (Optional[str]): Update timestamp.
    """

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
    """Container for Felix diary list responses.

    Attributes:
        items (List[WellnessDiaryEntryResponse]): Diary entries.
    """

    items: List[WellnessDiaryEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessDiaryResponse(BaseModel):
    """Envelope for Felix diary list responses.

    Attributes:
        status (str): Provider-normalized status.
        data (WellnessDiaryDataResponse): Diary payload.
    """

    status: str
    data: WellnessDiaryDataResponse


class WellnessCheckInMutationResponse(BaseModel):
    """Envelope for Felix check-in creation responses.

    Attributes:
        status (str): Provider-normalized status.
        message (str): User-safe mutation summary.
        data (WellnessLatestCheckInResponse): Dashboard-compatible snapshot.
    """

    status: str
    message: str
    data: WellnessLatestCheckInResponse


class WellnessDiaryMutationResponse(BaseModel):
    """Envelope for Felix diary mutations.

    Attributes:
        status (str): Provider-normalized status.
        message (str): User-safe mutation summary.
        data (WellnessDiaryEntryResponse): Mutated diary entry.
    """

    status: str
    message: str
    data: WellnessDiaryEntryResponse


class WellnessActivityMutationResponse(BaseModel):
    """Envelope for Felix activity mutations.

    Attributes:
        status (str): Provider-normalized status.
        message (str): User-safe mutation summary.
        data (WellnessActivityItemResponse): Mutated activity item.
    """

    status: str
    message: str
    data: WellnessActivityItemResponse


class WellnessCheckInRecordResponse(BaseModel):
    """Raw Felix check-in record used by sync snapshots.

    Attributes:
        id (str): Stable check-in identifier.
        recorded_at (str): Occurrence timestamp.
        mood_score (int): Dashboard-compatible mood score.
        stress_score (int): Dashboard-compatible stress score.
        energy_score (int): Dashboard-compatible energy score.
        tag_keys (List[str]): Persisted semantic tags.
        metrics (Dict[str, int]): Flexible captured metrics.
        activity_id (Optional[str]): Optional linked activity identifier.
        note (Optional[str]): Optional user-authored note.
        created_at (Optional[str]): Creation timestamp.
        updated_at (Optional[str]): Update timestamp.
    """

    id: str
    recorded_at: str
    mood_score: int = Field(ge=0, le=10)
    stress_score: int = Field(ge=0, le=10)
    energy_score: int = Field(ge=0, le=10)
    tag_keys: List[str] = Field(default_factory=list)
    metrics: Dict[str, int] = Field(default_factory=dict)
    activity_id: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncBootstrapDataResponse(BaseModel):
    """Combined Felix bootstrap payload for local sync.

    Attributes:
        server_timestamp (str): Backend timestamp for the snapshot.
        activities (List[WellnessActivityItemResponse]): Activity rows.
        diary_entries (List[WellnessDiaryEntryResponse]): Diary rows.
        checkins (List[WellnessCheckInRecordResponse]): Check-in rows.
    """

    server_timestamp: str
    activities: List[WellnessActivityItemResponse] = []
    diary_entries: List[WellnessDiaryEntryResponse] = []
    checkins: List[WellnessCheckInRecordResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncBootstrapResponse(BaseModel):
    """Envelope for Felix sync bootstrap responses.

    Attributes:
        status (str): Provider-normalized status.
        data (WellnessSyncBootstrapDataResponse): Bootstrap payload.
    """

    status: str
    data: WellnessSyncBootstrapDataResponse


class WellnessSyncChangeResponse(BaseModel):
    """Single Felix incremental sync change entry.

    Attributes:
        entity_type (Literal): Changed wellness entity family.
        entity_id (str): Changed entity identifier.
        action (Literal): Upsert or delete action.
        updated_at (str): Change timestamp.
        payload (dict): Serialized entity payload.
    """

    entity_type: Literal[
        "wellness_activity",
        "wellness_diary_entry",
        "wellness_checkin",
    ]
    entity_id: str
    action: Literal["upsert", "delete"]
    updated_at: str
    payload: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncChangesDataResponse(BaseModel):
    """Incremental Felix sync pull payload.

    Attributes:
        server_timestamp (str): Backend timestamp for this response.
        changes (List[WellnessSyncChangeResponse]): Ordered changes.
        next_cursor (Optional[str]): Cursor for the next pull.
        has_more (bool): Whether more changes are available.
    """

    server_timestamp: str
    changes: List[WellnessSyncChangeResponse] = []
    next_cursor: Optional[str] = None
    has_more: bool = False

    model_config = ConfigDict(from_attributes=True)


class WellnessSyncChangesResponse(BaseModel):
    """Envelope for Felix incremental sync responses.

    Attributes:
        status (str): Provider-normalized status.
        data (WellnessSyncChangesDataResponse): Incremental change payload.
    """

    status: str
    data: WellnessSyncChangesDataResponse


class FelixWellnessCheckInRecordMutationResponse(BaseModel):
    """Response envelope for Felix check-in update operations.

    Attributes:
        status (str): Provider-normalized mutation status.
        message (str): User-safe mutation summary.
        data (WellnessCheckInRecordResponse): Updated raw check-in row used by
            local sync snapshots and diary timeline rendering.
    """

    status: str
    message: str
    data: WellnessCheckInRecordResponse

class FelixAccessReadinessUpdateRequest(BaseModel):
    """Request model for partial Felix access-readiness updates.

    Attributes:
        setup_completed (Optional[bool]): Whether setup has been completed.
        setup_completed_at (Optional[str]): ISO timestamp for setup
            completion.
        legal_accepted_version (Optional[str]): Accepted legal content version.
        legal_accepted_at (Optional[str]): ISO timestamp for legal acceptance.
        setup_payload (Optional[Dict[str, Any]]): PWA-compatible setupPayload
            patch for privacy, metrics, notifications, and later slices.
    """

    setup_completed: Optional[bool] = Field(None, alias="setupCompleted")
    setup_completed_at: Optional[str] = Field(None, alias="setupCompletedAt")
    legal_accepted_version: Optional[str] = Field(None, alias="legalAcceptedVersion", max_length=128)
    legal_accepted_at: Optional[str] = Field(None, alias="legalAcceptedAt")
    setup_payload: Optional[Dict[str, Any]] = Field(None, alias="setupPayload")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def require_mutable_field(self) -> "FelixAccessReadinessUpdateRequest":
        """Ensure the request contains at least one readiness field.

        Returns:
            FelixAccessReadinessUpdateRequest: The validated request.

        Raises:
            ValueError: When no mutable field was supplied.
        """
        if not self.model_fields_set:
            raise ValueError("At least one access-readiness field must be provided")
        return self


class FelixAccessReadinessStateResponse(BaseModel):
    """Response model for a complete Felix access-readiness record.

    Attributes:
        setup_completed (bool): Whether setup has been completed.
        setup_completed_at (Optional[str]): ISO timestamp for setup
            completion.
        legal_accepted_version (Optional[str]): Accepted legal content version.
        legal_accepted_at (Optional[str]): ISO timestamp for legal acceptance.
        setup_payload (Optional[Dict[str, Any]]): PWA-compatible setupPayload
            state shared across devices.
    """

    setup_completed: bool = Field(alias="setupCompleted")
    setup_completed_at: Optional[str] = Field(None, alias="setupCompletedAt")
    legal_accepted_version: Optional[str] = Field(None, alias="legalAcceptedVersion")
    legal_accepted_at: Optional[str] = Field(None, alias="legalAcceptedAt")
    setup_payload: Optional[Dict[str, Any]] = Field(None, alias="setupPayload")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class FelixAccessReadinessResponse(BaseModel):
    """Envelope for Felix access-readiness reads.

    Attributes:
        status (str): Operation status.
        data (FelixAccessReadinessStateResponse): Complete readiness state.
    """

    status: str
    data: FelixAccessReadinessStateResponse


class FelixAccessReadinessMutationResponse(BaseModel):
    """Envelope for Felix access-readiness mutations.

    Attributes:
        status (str): Operation status.
        message (str): Human-readable mutation result.
        data (FelixAccessReadinessStateResponse): Updated readiness state.
    """

    status: str
    message: str
    data: FelixAccessReadinessStateResponse

class FelixRewardMediaPreferencesRequest(BaseModel):
    """Request model for reward media preference patches.

    Attributes:
        format_order (Optional[List[str]]): Preferred media formats in priority
            order.
        language (Optional[str]): Preferred reward media language key.
        speaker (Optional[str]): Preferred reward speaker key.
        subtitles_enabled (Optional[bool]): Whether subtitles are shown when
            available.
    """

    format_order: Optional[List[str]] = None
    language: Optional[str] = None
    speaker: Optional[str] = None
    subtitles_enabled: Optional[bool] = None


class FelixRewardsStateUpdateRequest(BaseModel):
    """Request model for partial Felix rewards-state updates.

    Attributes:
        purchases (Optional[List[str]]): Unlocked reward identifiers.
        spent_suns (Optional[int]): Lifetime spent suns.
        last_seen_earned_suns (Optional[int]): Last earned total acknowledged
            by the UI.
        last_celebrated_earned_suns (Optional[int]): Last earned total shown in
            celebration UI.
        streak_savers_available (Optional[int]): Stocked streak savers.
        streak_savers_max (Optional[int]): Maximum streak savers that can be
            stocked.
        streak_saver_used_day_keys (Optional[List[str]]): Day keys protected by
            streak savers.
        last_streak_saver_grant_day_key (Optional[str]): Last day that granted
            a streak saver.
        media_preferences (Optional[FelixRewardMediaPreferencesRequest]):
            Reward media preference patch.
    """

    purchases: Optional[List[str]] = None
    spent_suns: Optional[int] = Field(None, ge=0)
    last_seen_earned_suns: Optional[int] = Field(None, ge=0)
    last_celebrated_earned_suns: Optional[int] = Field(None, ge=0)
    streak_savers_available: Optional[int] = Field(None, ge=0)
    streak_savers_max: Optional[int] = Field(None, ge=1)
    streak_saver_used_day_keys: Optional[List[str]] = None
    last_streak_saver_grant_day_key: Optional[str] = None
    media_preferences: Optional[FelixRewardMediaPreferencesRequest] = None


class FelixRewardMediaPreferencesResponse(BaseModel):
    """Response model for complete reward media preferences.

    Attributes:
        format_order (List[str]): Preferred media formats in priority order.
        language (str): Preferred reward media language key.
        speaker (str): Preferred reward speaker key.
        subtitles_enabled (bool): Whether subtitles are shown when available.
    """

    format_order: List[str] = Field(default_factory=list)
    language: str = "app"
    speaker: str = "any"
    subtitles_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class FelixRewardsStateResponse(BaseModel):
    """Response model for complete Felix rewards state.

    Attributes:
        purchases (List[str]): Unlocked reward identifiers.
        spent_suns (int): Lifetime spent suns.
        last_seen_earned_suns (int): Last earned total acknowledged by the UI.
        last_celebrated_earned_suns (int): Last earned total shown in
            celebration UI.
        streak_savers_available (int): Stocked streak savers.
        streak_savers_max (int): Maximum streak savers that can be stocked.
        streak_saver_used_day_keys (List[str]): Day keys protected by streak
            savers.
        last_streak_saver_grant_day_key (Optional[str]): Last day that granted a
            streak saver.
        media_preferences (FelixRewardMediaPreferencesResponse): Reward media
            preference state.
    """

    purchases: List[str] = Field(default_factory=list)
    spent_suns: int = Field(ge=0)
    last_seen_earned_suns: int = Field(ge=0)
    last_celebrated_earned_suns: int = Field(ge=0)
    streak_savers_available: int = Field(ge=0)
    streak_savers_max: int = Field(ge=1)
    streak_saver_used_day_keys: List[str] = Field(default_factory=list)
    last_streak_saver_grant_day_key: Optional[str] = None
    media_preferences: FelixRewardMediaPreferencesResponse

    model_config = ConfigDict(from_attributes=True)


class FelixRewardsResponse(BaseModel):
    """Envelope for Felix rewards-state reads.

    Attributes:
        status (str): Operation status.
        data (FelixRewardsStateResponse): Complete rewards state.
    """

    status: str
    data: FelixRewardsStateResponse


class FelixRewardsMutationResponse(BaseModel):
    """Envelope for Felix rewards-state mutations.

    Attributes:
        status (str): Operation status.
        message (str): Human-readable mutation result.
        data (FelixRewardsStateResponse): Updated rewards state.
    """

    status: str
    message: str
    data: FelixRewardsStateResponse


__all__ = [
    "FelixAccessReadinessMutationResponse",
    "FelixAccessReadinessResponse",
    "FelixAccessReadinessStateResponse",
    "FelixAccessReadinessUpdateRequest",
    "FelixRewardMediaPreferencesRequest",
    "FelixRewardMediaPreferencesResponse",
    "FelixRewardsMutationResponse",
    "FelixRewardsResponse",
    "FelixRewardsStateResponse",
    "FelixRewardsStateUpdateRequest",
    "FelixWellnessCheckInRecordMutationResponse",
    "FelixWellnessCheckInUpdateRequest",
    "FelixWellnessDiaryEntryUpdateRequest",
    "WellnessActivitiesResponse",
    "WellnessActivityMutationResponse",
    "WellnessActivityUpdateRequest",
    "WellnessCheckInCreateRequest",
    "WellnessCheckInMutationResponse",
    "WellnessDashboardResponse",
    "WellnessDiaryEntryCreateRequest",
    "WellnessDiaryMutationResponse",
    "WellnessDiaryResponse",
    "WellnessSyncBootstrapResponse",
    "WellnessSyncChangesResponse",
]
