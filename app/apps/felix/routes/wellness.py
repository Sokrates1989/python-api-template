"""Wellness routes owned by the Felix backend app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.shared_dependencies.auth import get_user_id_from_token
from apps.felix.schemas.wellness import (
    FelixAccessReadinessMutationResponse,
    FelixAccessReadinessResponse,
    FelixAccessReadinessUpdateRequest,
    FelixRewardsMutationResponse,
    FelixRewardsResponse,
    FelixRewardsStateUpdateRequest,
    FelixWellnessCheckInRecordMutationResponse,
    FelixWellnessCheckInUpdateRequest,
    FelixWellnessDiaryEntryUpdateRequest,
    WellnessActivitiesResponse,
    WellnessActivityCategoryCreateRequest,
    WellnessActivityCategoryMutationResponse,
    WellnessActivityCategoryUpdateRequest,
    WellnessActivityCreateRequest,
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
from apps.felix.services.access_readiness_service import FelixAccessReadinessService
from apps.felix.services.rewards_service import FelixRewardsService
from apps.felix.services.wellness_service import FelixWellnessService

dashboard_router = APIRouter(tags=["dashboard"], prefix="/v1/dashboard")
activities_router = APIRouter(tags=["activities"], prefix="/v1/activities")
activity_categories_router = APIRouter(tags=["activity-categories"], prefix="/v1/activity-categories")
app_sync_router = APIRouter(tags=["sync"], prefix="/v1/sync")
rewards_router = APIRouter(tags=["rewards"], prefix="/v1/rewards")
setup_router = APIRouter(tags=["setup"], prefix="/v1/setup")
dev_router = APIRouter(tags=["dev"], prefix="/v1/dev")
recovery_router = APIRouter(tags=["recovery"], prefix="/v1/recovery")
diary_router = APIRouter(tags=["diary"], prefix="/v1/diary")
checkins_router = APIRouter(tags=["check-ins"], prefix="/v1/check-ins")
legacy_wellness_router = APIRouter(
    prefix="/v1/wellness",
    include_in_schema=False,
)
router = APIRouter()


def get_service() -> FelixWellnessService:
    """Return the Felix wellness service."""
    return FelixWellnessService()


def get_rewards_service() -> FelixRewardsService:
    """Return the Felix rewards service.

    Args:
        None.

    Returns:
        FelixRewardsService: App-owned service for reward persistence.

    Side Effects:
        Resolves the active database handler through the service constructor.
    """
    return FelixRewardsService()


def get_access_readiness_service() -> FelixAccessReadinessService:
    """Return the Felix access-readiness service.

    Args:
        None.

    Returns:
        FelixAccessReadinessService: App-owned service for setup readiness
        persistence.

    Side Effects:
        Resolves the active database handler through the service constructor.
    """
    return FelixAccessReadinessService()

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
    if any(token in lowered for token in ("unsupported", "required", "already exists", "still in use", "unknown activity categor")):
        raise HTTPException(status_code=400, detail=message)
    raise HTTPException(status_code=500, detail=message)


def _checkin_tag_keys(request: WellnessCheckInCreateRequest) -> list[str]:
    """Return normalized request tag candidates before service-level cleanup.

    Args:
        request (WellnessCheckInCreateRequest): Incoming check-in request that
            may use either the canonical ``tag_keys`` field or the legacy
            ``tags`` client alias.

    Returns:
        list[str]: Ordered tag candidates with duplicates removed. Provider
        services still apply their own storage normalization.
    """
    tags: list[str] = []
    for raw_tag in [*request.tag_keys, *request.tags]:
        tag = str(raw_tag).strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _checkin_patch_payload(request: FelixWellnessCheckInUpdateRequest) -> dict:
    """Return a normalized check-in patch payload for the service layer.

    Args:
        request (FelixWellnessCheckInUpdateRequest): Incoming Felix-owned
            check-in update request.

    Returns:
        dict: Patch fields with canonical ``tag_keys`` when either tag alias was
        supplied.
    """
    payload = request.model_dump(exclude_unset=True)
    if "tag_keys" in payload or "tags" in payload:
        tags: list[str] = []
        for raw_tag in [*(request.tag_keys or []), *(request.tags or [])]:
            tag = str(raw_tag).strip()
            if tag and tag not in tags:
                tags.append(tag)
        payload["tag_keys"] = tags
        payload.pop("tags", None)
    return payload


@legacy_wellness_router.get("/dashboard")
@dashboard_router.get("")
async def get_dashboard(current_user_id: str = Depends(get_user_id_from_token)) -> WellnessDashboardResponse:
    """Return the authenticated user's dashboard summary."""
    service = get_service()
    result = await service.get_dashboard(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessDashboardResponse(**result)


@legacy_wellness_router.get("/activities")
@activities_router.get("")
async def list_activities(current_user_id: str = Depends(get_user_id_from_token)) -> WellnessActivitiesResponse:
    """Return the authenticated user's activity catalog."""
    service = get_service()
    result = await service.list_activities(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivitiesResponse(**result)


@legacy_wellness_router.get("/sync-bootstrap")
@app_sync_router.get("/bootstrap")
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


@legacy_wellness_router.get("/sync-changes")
@app_sync_router.get("/changes")
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


@legacy_wellness_router.get("/rewards")
@rewards_router.get("")
async def get_rewards_state(
    current_user_id: str = Depends(get_user_id_from_token),
) -> FelixRewardsResponse:
    """Return the authenticated user's Felix rewards state.

    Args:
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        FelixRewardsResponse: Complete app-owned rewards state.

    Raises:
        HTTPException: When the configured database backend cannot serve the
        rewards state.
    """
    service = get_rewards_service()
    result = await service.get_rewards_state(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return FelixRewardsResponse(**result)


@legacy_wellness_router.patch("/rewards")
@rewards_router.patch("")
async def update_rewards_state(
    request: FelixRewardsStateUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> FelixRewardsMutationResponse:
    """Patch the authenticated user's Felix rewards state.

    Args:
        request (FelixRewardsStateUpdateRequest): Partial rewards-state patch.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        FelixRewardsMutationResponse: Updated app-owned rewards state.

    Raises:
        HTTPException: When the configured database backend rejects the update.
    """
    service = get_rewards_service()
    result = await service.update_rewards_state(
        current_user_id,
        request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return FelixRewardsMutationResponse(**result)



@legacy_wellness_router.get("/access-readiness")
@setup_router.get("/access-readiness")
async def get_access_readiness_state(
    current_user_id: str = Depends(get_user_id_from_token),
) -> FelixAccessReadinessResponse:
    """Return the authenticated user's Felix access-readiness state.

    Args:
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        FelixAccessReadinessResponse: Complete setup/legal readiness state.

    Raises:
        HTTPException: When the configured database backend cannot serve the
        readiness state.
    """
    service = get_access_readiness_service()
    result = await service.get_access_readiness_state(current_user_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return FelixAccessReadinessResponse(**result)


@legacy_wellness_router.patch("/access-readiness")
@setup_router.patch("/access-readiness")
async def update_access_readiness_state(
    request: FelixAccessReadinessUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> FelixAccessReadinessMutationResponse:
    """Patch the authenticated user's Felix access-readiness state.

    Args:
        request (FelixAccessReadinessUpdateRequest): Partial readiness patch in
            the PWA camelCase contract.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        FelixAccessReadinessMutationResponse: Updated setup/legal readiness
        state.

    Raises:
        HTTPException: When the configured database backend rejects the update.
    """
    service = get_access_readiness_service()
    result = await service.update_access_readiness_state(
        current_user_id,
        request.model_dump(exclude_unset=True, by_alias=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return FelixAccessReadinessMutationResponse(**result)


@legacy_wellness_router.post("/dev/reset")
@dev_router.post("/reset")
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


@legacy_wellness_router.post("/recovery/reset-backend-state")
@recovery_router.post("/reset-backend-state")
async def reset_backend_state_for_recovery(
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Reset the authenticated user's backend wellness state for recovery."""
    service = get_service()
    result = await service.reset_user_data(current_user_id, keep_activity_catalog=True)
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@legacy_wellness_router.patch("/activities/{activity_id}")
@activities_router.patch("/{activity_id}")
async def update_activity(
    activity_id: str,
    request: WellnessActivityUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessActivityMutationResponse:
    """Update mutable state for one activity."""
    service = get_service()
    result = await service.update_activity(
        user_id=current_user_id,
        activity_id=activity_id,
        patch=request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivityMutationResponse(**result)


@activities_router.post("", status_code=status.HTTP_201_CREATED)
async def create_activity(
    request: WellnessActivityCreateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessActivityMutationResponse:
    """Create one user-owned catalogue activity."""
    result = await get_service().create_activity(
        user_id=current_user_id,
        payload=request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivityMutationResponse(**result)


@activities_router.delete("/{activity_id}", status_code=status.HTTP_200_OK)
async def delete_activity(
    activity_id: str,
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Delete one user-owned catalogue activity idempotently."""
    result = await get_service().delete_activity(current_user_id, activity_id)
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@activity_categories_router.post("", status_code=status.HTTP_201_CREATED)
async def create_activity_category(
    request: WellnessActivityCategoryCreateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessActivityCategoryMutationResponse:
    """Create one user-owned catalogue category."""
    result = await get_service().create_activity_category(
        current_user_id,
        request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivityCategoryMutationResponse(**result)


@activity_categories_router.patch("/{category_key}")
async def update_activity_category(
    category_key: str,
    request: WellnessActivityCategoryUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessActivityCategoryMutationResponse:
    """Patch one user-owned catalogue category."""
    result = await get_service().update_activity_category(
        current_user_id,
        category_key,
        request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessActivityCategoryMutationResponse(**result)


@activity_categories_router.delete("/{category_key}", status_code=status.HTTP_200_OK)
async def delete_activity_category(
    category_key: str,
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Delete one unused user-owned catalogue category."""
    result = await get_service().delete_activity_category(current_user_id, category_key)
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@legacy_wellness_router.get("/diary")
@diary_router.get("/entries")
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


@legacy_wellness_router.post("/diary", status_code=status.HTTP_201_CREATED)
@diary_router.post("/entries", status_code=status.HTTP_201_CREATED)
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


@legacy_wellness_router.patch("/diary/{entry_id}")
@diary_router.patch("/entries/{entry_id}")
async def update_diary_entry(
    entry_id: str,
    request: FelixWellnessDiaryEntryUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> WellnessDiaryMutationResponse:
    """Update one authenticated Felix diary entry.

    Args:
        entry_id (str): Diary entry identifier scoped to the current user.
        request (FelixWellnessDiaryEntryUpdateRequest): Felix-owned partial
            diary update payload.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        WellnessDiaryMutationResponse: Updated diary entry envelope.

    Raises:
        HTTPException: When the provider rejects the update or the entry cannot
            be found.
    """
    service = get_service()
    result = await service.update_diary_entry(
        user_id=current_user_id,
        entry_id=entry_id,
        patch=request.model_dump(exclude_unset=True),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessDiaryMutationResponse(**result)


@legacy_wellness_router.delete("/diary/{entry_id}")
@diary_router.delete("/entries/{entry_id}")
async def delete_diary_entry(
    entry_id: str,
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Delete one authenticated Felix diary entry.

    Args:
        entry_id (str): Diary entry identifier scoped to the current user.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        dict: Provider-normalized deletion result with the removed id.

    Raises:
        HTTPException: When the provider rejects the deletion or the entry
            cannot be found.
    """
    service = get_service()
    result = await service.delete_diary_entry(
        user_id=current_user_id,
        entry_id=entry_id,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


@legacy_wellness_router.post("/check-ins", status_code=status.HTTP_201_CREATED)
@checkins_router.post("", status_code=status.HTTP_201_CREATED)
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
        recorded_at=request.recorded_at,
        tag_keys=_checkin_tag_keys(request),
        metrics=request.metrics,
        activity_id=request.activity_id,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return WellnessCheckInMutationResponse(**result)


@legacy_wellness_router.patch("/check-ins/{checkin_id}")
@checkins_router.patch("/{checkin_id}")
async def update_checkin(
    checkin_id: str,
    request: FelixWellnessCheckInUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> FelixWellnessCheckInRecordMutationResponse:
    """Update one authenticated Felix check-in.

    Args:
        checkin_id (str): Check-in identifier scoped to the current user.
        request (FelixWellnessCheckInUpdateRequest): Felix-owned partial
            check-in update payload.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        FelixWellnessCheckInRecordMutationResponse: Updated raw check-in record
        envelope used by the Flutter sync snapshot.

    Raises:
        HTTPException: When the provider rejects the update or the check-in
            cannot be found.
    """
    service = get_service()
    result = await service.update_checkin(
        user_id=current_user_id,
        checkin_id=checkin_id,
        patch=_checkin_patch_payload(request),
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return FelixWellnessCheckInRecordMutationResponse(**result)


@legacy_wellness_router.delete("/check-ins/{checkin_id}")
@checkins_router.delete("/{checkin_id}")
async def delete_checkin(
    checkin_id: str,
    current_user_id: str = Depends(get_user_id_from_token),
) -> dict:
    """Delete one authenticated Felix check-in.

    Args:
        checkin_id (str): Check-in identifier scoped to the current user.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        dict: Provider-normalized deletion result with the removed id.

    Raises:
        HTTPException: When the provider rejects the deletion or the check-in
            cannot be found.
    """
    service = get_service()
    result = await service.delete_checkin(
        user_id=current_user_id,
        checkin_id=checkin_id,
    )
    if result.get("status") != "success":
        _raise_result_error(result)
    return result


router.include_router(dashboard_router)
router.include_router(activities_router)
router.include_router(activity_categories_router)
router.include_router(app_sync_router)
router.include_router(rewards_router)
router.include_router(setup_router)
router.include_router(dev_router)
router.include_router(recovery_router)
router.include_router(diary_router)
router.include_router(checkins_router)
router.include_router(legacy_wellness_router)
