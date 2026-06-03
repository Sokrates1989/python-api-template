"""Shared user routes with authentication dependencies."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from api.shared_dependencies.auth import get_user_id_from_token, verify_auth_dependency
from api.shared_schemas.users import (
    UsernameUpdateRequest,
    UserCreateRequest,
    UserMutationResponse,
    UserResponse,
    UserUpdateRequest,
)
from backend.shared_services.user_service import UserService

router = APIRouter(tags=["users"], prefix="/users")


def get_service() -> UserService:
    """
    Return the shared user service instance.

    Args:
        None.

    Returns:
        UserService: Shared user service facade.

    Side Effects:
        Instantiates the service lazily for the current request.
    """
    return UserService()


def _raise_user_result_error(result: Dict[str, Any]) -> None:
    """
    Convert provider result payloads into HTTP exceptions.

    Args:
        result (Dict[str, Any]): Provider result payload.

    Returns:
        None.

    Raises:
        HTTPException: Raised when the provider returned an error payload.

    Side Effects:
        None.
    """
    message = str(result.get("message", "Database error"))
    lowered = message.lower()
    if "not found" in lowered:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if "already exists" in lowered or "already registered" in lowered or "already in use" in lowered:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreateRequest,
    user_info: dict = Depends(verify_auth_dependency),
) -> UserMutationResponse:
    """Create a new authenticated user profile."""
    token_user_id = user_info.get("user_id") or user_info.get("sub")
    if user.id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create user account for another user",
        )

    service = get_service()
    result = await service.create_user(
        user_id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    if result.get("status") == "error":
        _raise_user_result_error(result)
    return UserMutationResponse(**result)


@router.get("/{user_id}")
async def get_user(user_id: str, current_user_id: str = Depends(get_user_id_from_token)) -> UserResponse:
    """Return the authenticated user's own profile."""
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user's information",
        )

    service = get_service()
    result = await service.get_user(user_id)
    if result.get("status") == "error":
        _raise_user_result_error(result)
    return UserResponse(**result["data"])


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    user_update: UserUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> UserMutationResponse:
    """Update the authenticated user's own profile."""
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's information",
        )

    if all(
        value is None
        for value in [
            user_update.email,
            user_update.username,
            user_update.first_name,
            user_update.last_name,
        ]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided for update",
        )

    service = get_service()
    result = await service.update_user(
        user_id=user_id,
        email=user_update.email,
        username=user_update.username,
        first_name=user_update.first_name,
        last_name=user_update.last_name,
    )
    if result.get("status") == "error":
        _raise_user_result_error(result)
    return UserMutationResponse(**result)


@router.patch("/{user_id}/username")
async def update_username(
    user_id: str,
    username_update: UsernameUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
) -> UserMutationResponse:
    """Update the authenticated user's username."""
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's username",
        )

    service = get_service()
    result = await service.update_username(user_id=user_id, username=username_update.username)
    if result.get("status") == "error":
        _raise_user_result_error(result)
    return UserMutationResponse(**result)
