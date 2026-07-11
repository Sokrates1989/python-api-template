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
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...

    async def create_activity(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one user-owned activity from a validated catalogue payload."""
        ...

    async def delete_activity(self, user_id: str, activity_id: str) -> Dict[str, Any]:
        """Delete one user-owned activity and return an idempotent result."""
        ...

    async def create_activity_category(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one user-owned activity category."""
        ...

    async def update_activity_category(self, user_id: str, category_key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch one user-owned activity category."""
        ...

    async def delete_activity_category(self, user_id: str, category_key: str) -> Dict[str, Any]:
        """Delete an unused category or return a validation error."""
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

    async def update_diary_entry(
        self,
        user_id: str,
        entry_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one diary entry for a user.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.
            patch (Dict[str, Any]): Mutable fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        ...

    async def delete_diary_entry(self, user_id: str, entry_id: str) -> Dict[str, Any]:
        """Delete one diary entry for a user.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
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

    async def update_checkin(
        self,
        user_id: str,
        checkin_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one check-in for a user.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.
            patch (Dict[str, Any]): Mutable fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        ...

    async def delete_checkin(self, user_id: str, checkin_id: str) -> Dict[str, Any]:
        """Delete one check-in for a user.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
        ...

    async def reset_user_data(
        self,
        user_id: str,
        *,
        keep_activity_catalog: bool = True,
    ) -> Dict[str, Any]:
        ...
