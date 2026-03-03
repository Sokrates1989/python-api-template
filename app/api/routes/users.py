"""Database-agnostic user routes with JWT authentication."""
from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth_dependency import get_user_id_from_token, verify_auth_dependency
from backend.services.user_service import UserService
from api.schemas.users.requests import (
    UserCreateRequest,
    UserUpdateRequest,
    UsernameUpdateRequest,
)
from api.schemas.users.responses import UserMutationResponse, UserResponse

router = APIRouter(tags=["users"], prefix="/users")


def get_service() -> UserService:
    """Get a database-aware user service instance."""
    return UserService()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreateRequest,
    user_info: dict = Depends(verify_auth_dependency),
):
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

    if result["status"] == "error":
        if (
            "already exists" in result["message"]
            or "already registered" in result["message"]
            or "already in use" in result["message"]
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
        )

    return UserMutationResponse(**result)


@router.get("/{user_id}")
async def get_user(user_id: str, current_user_id: str = Depends(get_user_id_from_token)):
    """Get authenticated user's own profile."""
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user's information",
        )

    service = get_service()
    result = await service.get_user(user_id)

    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
        )

    return UserResponse(**result["data"])


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    user_update: UserUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
):
    """Update authenticated user's own profile."""
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

    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
        if "already in use" in result["message"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
        )

    return UserMutationResponse(**result)


@router.patch("/{user_id}/username")
async def update_username(
    user_id: str,
    username_update: UsernameUpdateRequest,
    current_user_id: str = Depends(get_user_id_from_token),
):
    """Update authenticated user's username."""
    if user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's username",
        )

    service = get_service()
    result = await service.update_username(
        user_id=user_id,
        username=username_update.username,
    )

    if result["status"] == "error":
        if "not found" in result["message"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
        )

    return UserMutationResponse(**result)
