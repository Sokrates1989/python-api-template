"""Shared database-agnostic wellness service facade."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.adapters.wellness_repository_factory import create_wellness_repository
from backend.database import get_database_handler
from backend.ports.wellness_repository import WellnessRepository


class WellnessService:
    """Dispatch wellness operations to the configured database backend adapter."""

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
        """Return the dashboard payload for one user."""
        return await self._repository.get_dashboard(user_id=user_id)

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        """Return the activity catalog for one user."""
        return await self._repository.list_activities(user_id=user_id)

    async def get_sync_bootstrap(
        self,
        user_id: str,
        diary_limit: int = 50,
        checkin_limit: int = 50,
    ) -> Dict[str, Any]:
        """Return the initial sync bootstrap payload."""
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
        """Return incremental sync changes for one user."""
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
        """Update one activity record for the user."""
        return await self._repository.update_activity(
            user_id=user_id,
            activity_id=activity_id,
            favorite=favorite,
        )

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """Return diary entries for one user."""
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
        """Create a diary entry for one user."""
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
    ) -> Dict[str, Any]:
        """Create a check-in for one user."""
        return await self._repository.create_checkin(
            user_id=user_id,
            mood_score=mood_score,
            stress_score=stress_score,
            energy_score=energy_score,
            note=note,
        )

    async def reset_user_data(
        self,
        user_id: str,
        *,
        keep_activity_catalog: bool = True,
    ) -> Dict[str, Any]:
        """Reset wellness data for one user."""
        return await self._repository.reset_user_data(
            user_id=user_id,
            keep_activity_catalog=keep_activity_catalog,
        )
