"""
Legacy SQL sync routes for offline-first clients.

Selected backend apps now expose sync through app-owned route facades under
``app/apps/<app_id>/routes``. This module remains only for compatibility
imports and should not be used as the registration point for new apps.
"""
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
    """
    Return the backend-aware sync service.

    Args:
        None.

    Returns:
        SyncService: Shared legacy sync service facade.

    Side Effects:
        Instantiates the sync service for the current request.
    """
    return SyncService()


def ensure_sql_sync_supported() -> None:
    """
    Ensure SQL-only sync endpoints are not called for non-SQL backends.

    Args:
        None.

    Returns:
        None.

    Raises:
        HTTPException: HTTP 400 when the active database is not SQL-backed.

    Side Effects:
        None.
    """
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
    """
    Push pending local operations and return per-operation outcomes.

    Args:
        request (SyncPushRequest): Client operations to replay.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        SyncPushResponse: Per-operation sync results.

    Side Effects:
        Persists accepted operations through the legacy sync service.
    """
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
    """
    Return incremental server changes after an opaque cursor.

    Args:
        cursor (Optional[str]): Opaque sync cursor from the previous pull.
        limit (int): Maximum number of changes to return.
        entity_type (Optional[str]): Optional entity type filter.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        SyncPullResponse: Incremental server changes and next cursor.

    Raises:
        HTTPException: HTTP 400 when SQL sync is unsupported or the entity type
            is not supported by this legacy route.

    Side Effects:
        Reads sync state through the legacy sync service.
    """
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
    """
    Resolve a previously detected conflict for the authenticated user.

    Args:
        request (SyncConflictResolveRequest): Conflict resolution payload.
        current_user_id (str): Authenticated user id from the bearer token.

    Returns:
        SyncOperationResult: Conflict resolution result.

    Raises:
        HTTPException: HTTP 400 when SQL sync is unsupported.

    Side Effects:
        Persists the conflict resolution through the legacy sync service.
    """
    ensure_sql_sync_supported()
    service = get_service()
    result = await service.resolve_conflict(
        user_id=current_user_id,
        request=request,
    )
    return SyncOperationResult(**result)
