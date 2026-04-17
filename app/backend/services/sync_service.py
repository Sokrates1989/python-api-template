"""Backend-aware sync service facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.schemas.sync.requests import SyncConflictResolveRequest, SyncOperationRequest
from api.settings import settings
from backend.services.mongodb.sync_service import SyncService as MongoSyncService
from backend.services.sql.sync_service import SyncService as SQLSyncService


class SyncService:
    """Dispatch sync requests to the active backend-specific implementation."""

    USER_PROFILE_ENTITY = SQLSyncService.USER_PROFILE_ENTITY

    def __init__(self) -> None:
        if settings.is_sql_database():
            self._delegate = SQLSyncService()
        else:
            self._delegate = MongoSyncService()

    async def push_operations(
        self,
        *,
        user_id: str,
        operations: List[SyncOperationRequest],
    ) -> List[Dict[str, Any]]:
        return await self._delegate.push_operations(user_id=user_id, operations=operations)

    async def pull_changes(
        self,
        *,
        user_id: str,
        cursor: Optional[str],
        limit: int,
        entity_type: Optional[str],
    ) -> Dict[str, Any]:
        return await self._delegate.pull_changes(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            entity_type=entity_type,
        )

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        request: SyncConflictResolveRequest,
    ) -> Dict[str, Any]:
        return await self._delegate.resolve_conflict(user_id=user_id, request=request)
