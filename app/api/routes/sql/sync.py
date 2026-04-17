"""Hybrid sync routes for offline-first clients."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncPushRequest
from api.schemas.sync.responses import SyncOperationResult, SyncPullResponse, SyncPushResponse
from api.settings import settings
from backend.auth_dependency import get_user_id_from_token
from backend.services.sync_service import SyncService

router = APIRouter(tags=["sync"], prefix="/v1/sync")


def get_service() -> SyncService:
    """Get the backend-aware sync service."""
    return SyncService()


def ensure_sql_sync_supported() -> None:
    """Ensure SQL-only sync endpoints are not called for non-SQL backends."""
    if not settings.is_sql_database():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This sync endpoint is only supported for SQL backends. Active DB_TYPE={settings.DB_TYPE}",
        )


@router.post("/push", response_model=SyncPushResponse)
async def push_sync_operations(
    request: SyncPushRequest,
    current_user_id: str = Depends(get_user_id_from_token),
):
    """Push pending local operations and return per-operation outcomes."""
    service = get_service()
    results = await service.push_operations(
        user_id=current_user_id,
        operations=request.operations,
    )
    return SyncPushResponse(results=[SyncOperationResult(**item) for item in results])


@router.get("/pull", response_model=SyncPullResponse)
async def pull_sync_changes(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    entity_type: Optional[str] = Query(default=None),
    current_user_id: str = Depends(get_user_id_from_token),
):
    """Return incremental server changes after an opaque cursor."""
    ensure_sql_sync_supported()
    if entity_type and entity_type != SyncService.USER_PROFILE_ENTITY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported entity_type: {entity_type}",
        )

    service = get_service()
    response = await service.pull_changes(
        user_id=current_user_id,
        cursor=cursor,
        limit=limit,
        entity_type=entity_type,
    )
    return SyncPullResponse(**response)


@router.post("/conflicts/resolve", response_model=SyncOperationResult)
async def resolve_sync_conflict(
    request: SyncConflictResolveRequest,
    current_user_id: str = Depends(get_user_id_from_token),
):
    """Resolve a previously detected conflict for the authenticated user."""
    ensure_sql_sync_supported()
    service = get_service()
    result = await service.resolve_conflict(
        user_id=current_user_id,
        request=request,
    )
    return SyncOperationResult(**result)
