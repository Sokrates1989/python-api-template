"""Wellness routes owned by the template backend app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.shared_dependencies.auth import get_user_id_from_token
from apps.template_app.schemas.wellness import (
    WellnessActivitiesResponse,
    WellnessActivityMutationResponse,
    WellnessActivityUpdateRequest,
    WellnessCheckInCreateRequest,
    WellnessCheckInMutationResponse,
    WellnessDashboardResponse,
    WellnessDiaryEntryCreateRequest,
    WellnessDiaryMutationResponse,
    WellnessDiaryResponse,
    WellnessSyncBootstrapResponse,
    WellnessSyncChangesResponse,
)
from apps.template_app.services.wellness_service import TemplateAppWellnessService

router = APIRouter(tags=["wellness"], prefix="/v1/wellness")


def get_service() -> TemplateAppWellnessService:
    """Return the template app wellness service."""
    return TemplateAppWellnessService()


def get_runtime_settings():
    """Return settings lazily to avoid import cycles during route registration."""
    from api.settings import settings

    return settings


def _raise_result_error(result: dict) -> None:
    """Convert provider error payloads into HTTP exceptions."""
    message = str(result.get("message", "Database error"))
    lowered = message.lower()
    if "not found" in lowered:
        raise HTTPException(status_code=404, detail=message)
    if "unsupported" in lowered or "requires mongodb" in lowered:
        raise HTTPException(status_code=400, detail=message)
    raise HTTPException(status_code=500, detail=message)


@router.get("/dashboard")
async def get_dashboard(current_user_id: str = Depends(get_user_id_from_token)) -> WellnessDashboardResponse:
    """Return the authenticated user's dashboard summary."""
    service = get_service()
    result = await service.get_dashboard(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessDashboardResponse(**result)


@router.get("/activities")
async def list_activities(current_user_id: str = Depends(get_user_id_from_token)) -> WellnessActivitiesResponse:
    """Return the authenticated user's activity catalog."""
    service = get_service()
    result = await service.list_activities(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivitiesResponse(**result)


@router.get("/sync-bootstrap")
async def get_sync_bootstrap(
    diary_limit: int = Query(50, ge=1, le=200, description="Maximum number of diary entries"),
    checkin_limit: int = Query(50, ge=1, le=200, description="Maximum number of check-ins"),
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessSyncBootstrapResponse:
    """Return the combined wellness bootstrap payload."""
    service = get_service()
    result = await service.get_sync_bootstrap(
        current_user_id,
        diary_limit=diary_limit,
        checkin_limit=checkin_limit,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessSyncBootstrapResponse(**result)


@router.get("/sync-changes")
async def get_sync_changes(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    entity_type: str | None = Query(default=None),
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessSyncChangesResponse:
    """Return incremental wellness entity changes."""
    service = get_service()
    result = await service.get_sync_changes(
        user_id=current_user_id,
        cursor=cursor,
        limit=limit,
        entity_type=entity_type,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessSyncChangesResponse(**result)


@router.post("/dev/reset")
async def reset_current_user_wellness_data(
    user_id: str = Query(..., min_length=1, description="User id to reset in local DEBUG mode"),
) -> dict:
    """Reset one user's wellness data for deterministic local testing."""
    if not get_runtime_settings().DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    service = get_service()
    result = await service.reset_user_data(user_id, keep_activity_catalog=True)
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@router.post("/recovery/reset-backend-state")
async def reset_backend_state_for_recovery(
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Reset the authenticated user's backend wellness state for recovery."""
    service = get_service()
    result = await service.reset_user_data(current_user_id, keep_activity_catalog=True)
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@router.patch("/activities/{activity_id}")
async def update_activity(
    activity_id: str,
    request: WellnessActivityUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessActivityMutationResponse:
    """Update mutable state for one activity."""
    if request.favorite is None:
        raise HTTPException(status_code=400, detail="At least one mutable activity field must be provided")

    service = get_service()
    result = await service.update_activity(
        user_id=current_user_id,
        activity_id=activity_id,
        favorite=request.favorite,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivityMutationResponse(**result)


@router.get("/diary")
async def list_diary_entries(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of diary entries"),
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessDiaryResponse:
    """Return the authenticated user's diary timeline."""
    service = get_service()
    result = await service.list_diary_entries(current_user_id, limit=limit)
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessDiaryResponse(**result)


@router.post("/diary", status_code=status.HTTP_201_CREATED)
async def create_diary_entry(
    request: WellnessDiaryEntryCreateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessDiaryMutationResponse:
    """Create a new authenticated diary entry."""
    service = get_service()
    result = await service.create_diary_entry(
        user_id=current_user_id,
        title=request.title,
        summary=request.summary,
        mood_score=request.mood_score,
        tag_keys=request.tag_keys,
        related_activity_id=request.related_activity_id,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessDiaryMutationResponse(**result)


@router.post("/check-ins", status_code=status.HTTP_201_CREATED)
async def create_checkin(
    request: WellnessCheckInCreateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessCheckInMutationResponse:
    """Create a new authenticated wellness check-in."""
    service = get_service()
    result = await service.create_checkin(
        user_id=current_user_id,
        mood_score=request.mood_score,
        stress_score=request.stress_score,
        energy_score=request.energy_score,
        note=request.note,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessCheckInMutationResponse(**result)
