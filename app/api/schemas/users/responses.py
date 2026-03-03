"""Response schemas for user endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Schema for user response."""

    id: str
    email: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserMutationResponse(BaseModel):
    """Schema for user creation/update responses."""

    status: str
    message: str
    data: Optional[UserResponse] = None
