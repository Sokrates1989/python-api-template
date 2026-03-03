"""User service for handling user-related business logic."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.database import get_database_handler
from backend.database.sql_handler import SQLHandler
from models.sql.user import User


class UserService:
    """Service for user-related operations."""

    def __init__(self):
        """Initialize the user service."""
        self.handler = get_database_handler()
        if not isinstance(self.handler, SQLHandler):
            raise ValueError("UserService requires SQL database")

    async def create_user(
        self,
        user_id: str,
        email: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new user record."""
        session = None
        try:
            if not username:
                username = email.split("@")[0]

            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                existing_user = result.scalar_one_or_none()
                if existing_user:
                    return {
                        "status": "error",
                        "message": f"User with ID {user_id} already exists",
                        "data": None,
                    }

                result = await session.execute(select(User).where(User.email == email))
                existing_email = result.scalar_one_or_none()
                if existing_email:
                    return {
                        "status": "error",
                        "message": f"Email {email} already registered",
                        "data": None,
                    }

                new_user = User(
                    id=user_id,
                    email=email,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True,
                    version=1,
                )

                session.add(new_user)
                await session.commit()
                await session.refresh(new_user)

                return {
                    "status": "success",
                    "message": "User created successfully",
                    "data": new_user.to_dict(),
                }

        except IntegrityError as exc:
            if session is not None:
                await session.rollback()
            return {
                "status": "error",
                "message": f"Database integrity error: {str(exc)}",
                "data": None,
            }
        except Exception as exc:
            if session is not None:
                await session.rollback()
            return {
                "status": "error",
                "message": f"Error creating user: {str(exc)}",
                "data": None,
            }

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get a user by ID."""
        try:
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

                if not user:
                    return {
                        "status": "error",
                        "message": f"User with ID {user_id} not found",
                        "data": None,
                    }

                return {
                    "status": "success",
                    "message": "User retrieved successfully",
                    "data": user.to_dict(),
                }

        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error retrieving user: {str(exc)}",
                "data": None,
            }

    async def update_user(
        self,
        user_id: str,
        email: Optional[str] = None,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update user profile fields and increment version on change."""
        payload = {
            "email": email,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        }
        return await self.apply_profile_patch(user_id=user_id, payload=payload)

    async def update_username(self, user_id: str, username: str) -> Dict[str, Any]:
        """Update only the user's username."""
        return await self.apply_profile_patch(
            user_id=user_id,
            payload={"username": username},
        )

    async def apply_profile_patch(
        self,
        user_id: str,
        payload: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply profile field updates with optional optimistic version checks."""
        session = None
        try:
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()

                if not user:
                    return {
                        "status": "error",
                        "message": f"User with ID {user_id} not found",
                        "data": None,
                    }

                if expected_version is not None and user.version != expected_version:
                    return {
                        "status": "conflict",
                        "message": "Version conflict",
                        "data": user.to_dict(),
                    }

                changed = False

                email = payload.get("email")
                if email is not None and email != user.email:
                    result = await session.execute(
                        select(User).where(User.email == email, User.id != user_id)
                    )
                    existing_email = result.scalar_one_or_none()
                    if existing_email:
                        return {
                            "status": "error",
                            "message": "Email already in use",
                            "data": None,
                        }
                    user.email = email
                    changed = True

                username = payload.get("username")
                if username is not None and username != user.username:
                    result = await session.execute(
                        select(User).where(User.username == username, User.id != user_id)
                    )
                    existing_username = result.scalar_one_or_none()
                    if existing_username:
                        return {
                            "status": "error",
                            "message": "Username already in use",
                            "data": None,
                        }
                    user.username = username
                    changed = True

                first_name = payload.get("first_name")
                if first_name is not None and first_name != user.first_name:
                    user.first_name = first_name
                    changed = True

                last_name = payload.get("last_name")
                if last_name is not None and last_name != user.last_name:
                    user.last_name = last_name
                    changed = True

                if not changed:
                    return {
                        "status": "success",
                        "message": "No changes applied",
                        "data": user.to_dict(),
                    }

                user.version = (user.version or 1) + 1

                await session.commit()
                await session.refresh(user)

                return {
                    "status": "success",
                    "message": "User updated successfully",
                    "data": user.to_dict(),
                }

        except IntegrityError as exc:
            if session is not None:
                await session.rollback()
            return {
                "status": "error",
                "message": f"Database integrity error: {str(exc)}",
                "data": None,
            }
        except Exception as exc:
            if session is not None:
                await session.rollback()
            return {
                "status": "error",
                "message": f"Error updating user: {str(exc)}",
                "data": None,
            }
