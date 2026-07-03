"""Protocol for modular wellness content repositories."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class WellnessRepository(Protocol):
    """Typed contract for wellness domain repositories."""

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        ...

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        ...

    async def get_sync_bootstrap(
        self,
        user_id: str,
        diary_limit: int = 50,
        checkin_limit: int = 50,
    ) -> Dict[str, Any]:
        ...

    async def get_sync_changes(
        self,
        user_id: str,
        cursor: Optional[str] = None,
        limit: int = 100,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    async def update_activity(
        self,
        user_id: str,
        activity_id: str,
        favorite: Optional[bool] = None,
    ) -> Dict[str, Any]:
        ...

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        ...

    async def create_diary_entry(
        self,
        user_id: str,
        title: str,
        summary: str,
        mood_score: int,
        tag_keys: List[str],
        related_activity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

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
        ...

    async def reset_user_data(
        self,
        user_id: str,
        *,
        keep_activity_catalog: bool = True,
    ) -> Dict[str, Any]:
        ...
