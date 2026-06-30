"""Wellness schemas owned by the Felix backend app.

The file reuses the shared wellness baseline where Felix still mirrors the
template wellness slice, and defines Felix-specific reward persistence schemas
locally so reward contracts do not leak into other backend app slices.
"""
from __future__ import annotations

from typing import List, Optional

from api.schemas.wellness.requests import (
    WellnessActivityUpdateRequest,
    WellnessCheckInCreateRequest,
    WellnessDiaryEntryCreateRequest,
)
from api.schemas.wellness.responses import (
    WellnessActivitiesResponse,
    WellnessActivityMutationResponse,
    WellnessCheckInMutationResponse,
    WellnessDashboardResponse,
    WellnessDiaryMutationResponse,
    WellnessDiaryResponse,
    WellnessSyncBootstrapResponse,
    WellnessSyncChangesResponse,
)
from pydantic import BaseModel, ConfigDict, Field


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
    "FelixRewardMediaPreferencesRequest",
    "FelixRewardMediaPreferencesResponse",
    "FelixRewardsMutationResponse",
    "FelixRewardsResponse",
    "FelixRewardsStateResponse",
    "FelixRewardsStateUpdateRequest",
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
