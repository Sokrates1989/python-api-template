"""Wellness schemas owned by the MongoDB Template backend app."""
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

__all__ = [
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
