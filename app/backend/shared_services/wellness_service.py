"""Shared database-agnostic wellness feature runtime.

This module is product-neutral shared feature code. Backend app slices opt into
it through their own route facades and own any SQL table creation through
``app/apps/<app_id>/migrations/versions``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.adapters.wellness_repository_factory import create_wellness_repository
from backend.database import get_database_handler
from backend.ports.wellness_repository import WellnessRepository


class WellnessService:
    """
    Dispatch wellness operations to the configured database backend adapter.

    Attributes:
        _repository (WellnessRepository): Provider-specific repository selected
            from the active database handler.
        _db_type (str): Normalized provider identifier used for diagnostics.

    Methods:
        get_dashboard: Return summary data for one user.
        list_activities: Return the activity catalog for one user.
        get_sync_bootstrap: Return initial offline-sync state.
        get_sync_changes: Return incremental offline-sync changes.
        update_activity: Persist mutable activity state.
        list_diary_entries: Return diary timeline entries.
        create_diary_entry: Persist one diary entry.
        create_checkin: Persist one check-in.
        reset_user_data: Reset user-owned wellness data.
    """

    def __init__(self) -> None:
        """
        Bind the service to the active provider-specific wellness repository.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Resolves the active database handler and wellness repository adapter.
        """
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._repository: WellnessRepository = create_wellness_repository(db_type)
        self._db_type = db_type

    @property
    def db_type(self) -> str:
        """
        Return the active backend type.

        Args:
            None.

        Returns:
            str: Active provider identifier.

        Side Effects:
            None.
        """
        return self._db_type

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """
        Return the dashboard payload for one user.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Provider-normalized dashboard payload.

        Side Effects:
            Reads from the configured wellness repository.
        """
        return await self._repository.get_dashboard(user_id=user_id)

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        """
        Return the activity catalog for one user.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Activity catalog payload.

        Side Effects:
            Reads from the configured wellness repository.
        """
        return await self._repository.list_activities(user_id=user_id)

    async def get_sync_bootstrap(
        self,
        user_id: str,
        diary_limit: int = 50,
        checkin_limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Return the initial sync bootstrap payload.

        Args:
            user_id (str): Authenticated user identifier.
            diary_limit (int): Maximum number of diary rows to include.
                Defaults to 50.
            checkin_limit (int): Maximum number of check-in rows to include.
                Defaults to 50.

        Returns:
            Dict[str, Any]: Bootstrap payload for local sync caches.

        Side Effects:
            Reads from the configured wellness repository.
        """
        return await self._repository.get_sync_bootstrap(
            user_id=user_id,
            diary_limit=diary_limit,
            checkin_limit=checkin_limit,
        )

    async def get_sync_changes(
        self,
        user_id: str,
        cursor: Optional[str] = None,
        limit: int = 100,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return incremental sync changes for one user.

        Args:
            user_id (str): Authenticated user identifier.
            cursor (Optional[str]): Opaque cursor from the previous sync read.
            limit (int): Maximum number of changes to return. Defaults to 100.
            entity_type (Optional[str]): Optional entity type filter.

        Returns:
            Dict[str, Any]: Incremental changes and next cursor.

        Side Effects:
            Reads from the configured wellness repository.
        """
        return await self._repository.get_sync_changes(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            entity_type=entity_type,
        )

    async def update_activity(
        self,
        user_id: str,
        activity_id: str,
        favorite: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Update mutable state on one activity record.

        Args:
            user_id (str): Authenticated user identifier.
            activity_id (str): Activity identifier scoped by user.
            favorite (Optional[bool]): Optional favorite state to persist.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.

        Side Effects:
            Writes to the configured wellness repository.
        """
        return await self._repository.update_activity(
            user_id=user_id,
            activity_id=activity_id,
            favorite=favorite,
        )

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """
        Return diary entries for one user.

        Args:
            user_id (str): Authenticated user identifier.
            limit (int): Maximum number of diary entries to return. Defaults
                to 20.

        Returns:
            Dict[str, Any]: Diary timeline payload.

        Side Effects:
            Reads from the configured wellness repository.
        """
        return await self._repository.list_diary_entries(user_id=user_id, limit=limit)

    async def create_diary_entry(
        self,
        user_id: str,
        title: str,
        summary: str,
        mood_score: int,
        tag_keys: List[str],
        related_activity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a diary entry for one user.

        Args:
            user_id (str): Authenticated user identifier.
            title (str): User-facing diary title.
            summary (str): User-facing diary summary/body.
            mood_score (int): Numeric mood score.
            tag_keys (List[str]): Tag identifiers attached to the entry.
            related_activity_id (Optional[str]): Optional related activity id.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.

        Side Effects:
            Writes to the configured wellness repository.
        """
        return await self._repository.create_diary_entry(
            user_id=user_id,
            title=title,
            summary=summary,
            mood_score=mood_score,
            tag_keys=tag_keys,
            related_activity_id=related_activity_id,
        )

    async def create_checkin(
        self,
        user_id: str,
        mood_score: int,
        stress_score: int,
        energy_score: int,
        note: Optional[str] = None,
        recorded_at: Optional[str] = None,
        tag_keys: Optional[List[str]] = None,
        metrics: Optional[Dict[str, int]] = None,
        activity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a check-in for one user.

        Args:
            user_id (str): Authenticated user identifier.
            mood_score (int): Numeric mood score.
            stress_score (int): Numeric stress score.
            energy_score (int): Numeric energy score.
            note (Optional[str]): Optional user note.
            recorded_at (Optional[str]): Optional ISO occurrence timestamp.
            tag_keys (Optional[List[str]]): Semantic tags for the check-in.
            metrics (Optional[Dict[str, int]]): Captured flexible metrics.
            activity_id (Optional[str]): Optional linked activity id.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.

        Side Effects:
            Writes to the configured wellness repository.
        """
        return await self._repository.create_checkin(
            user_id=user_id,
            mood_score=mood_score,
            stress_score=stress_score,
            energy_score=energy_score,
            note=note,
            recorded_at=recorded_at,
            tag_keys=tag_keys,
            metrics=metrics,
            activity_id=activity_id,
        )

    async def reset_user_data(
        self,
        user_id: str,
        *,
        keep_activity_catalog: bool = True,
    ) -> Dict[str, Any]:
        """
        Reset wellness data for one user.

        Args:
            user_id (str): Authenticated user identifier.
            keep_activity_catalog (bool): When True, preserves or reseeds the
                default activity catalog. Defaults to True.

        Returns:
            Dict[str, Any]: Provider-normalized reset summary.

        Side Effects:
            Deletes or rewrites user-owned wellness data in the configured
            repository.
        """
        return await self._repository.reset_user_data(
            user_id=user_id,
            keep_activity_catalog=keep_activity_catalog,
        )
