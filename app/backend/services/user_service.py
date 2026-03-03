"""Database-agnostic user service facade."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.adapters.user_repository_factory import create_user_repository
from backend.database import get_database_handler
from backend.ports.user_repository import UserRepository


class UserService:
    """Dispatch user operations to the configured database backend service."""

    def __init__(self):
        handler = get_database_handler()
        db_type = getattr(handler, "db_type", "").strip().lower()
        self._repository: UserRepository = create_user_repository(db_type)

    async def create_user(
        self,
        user_id: str,
        email: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._repository.create_user(
            user_id=user_id,
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        return await self._repository.get_user(user_id)

    async def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self._repository.update_user(
            user_id=user_id,
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

    async def update_username(self, user_id: str, username: str) -> Dict[str, Any]:
        return await self._repository.update_username(user_id=user_id, username=username)
