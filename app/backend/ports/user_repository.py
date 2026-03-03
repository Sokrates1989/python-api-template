"""User domain repository contract."""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

UserOperationResult = Dict[str, Any]


@runtime_checkable
class UserRepository(Protocol):
    """Port for user persistence operations across database providers."""

    async def create_user(
        self,
        user_id: str,
        email: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> UserOperationResult:
        ...

    async def get_user(self, user_id: str) -> UserOperationResult:
        ...

    async def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> UserOperationResult:
        ...

    async def update_username(self, user_id: str, username: str) -> UserOperationResult:
        ...
