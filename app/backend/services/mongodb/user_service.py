"""User service for MongoDB-backed user profiles."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.database import get_database_handler
from backend.database.mongodb_handler import MongoDBHandler

try:  # pragma: no cover - import guard for environments without Mongo deps
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
except Exception:  # pragma: no cover
    ReturnDocument = None  # type: ignore[assignment]

    class DuplicateKeyError(Exception):
        """Fallback duplicate key error when pymongo is unavailable."""


class UserService:
    """Service for MongoDB user operations."""

    def __init__(self):
        handler = get_database_handler()
        if not isinstance(handler, MongoDBHandler):
            raise ValueError("MongoDB UserService requires MongoDB database")
        if ReturnDocument is None:
            raise RuntimeError(
                "MongoDB support requires 'motor'/'pymongo'. Install dependencies and rebuild."
            )

        self.handler = handler
        self.collection = handler.database["users"]
        self._indexes_initialized = False

    async def _ensure_indexes(self) -> None:
        """Create unique indexes required by the user domain."""
        if self._indexes_initialized:
            return

        await self.collection.create_index("id", unique=True, name="idx_users_id_unique")
        await self.collection.create_index("email", unique=True, name="idx_users_email_unique")
        await self.collection.create_index(
            "username",
            unique=True,
            name="idx_users_username_unique",
        )
        self._indexes_initialized = True

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_user(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None

        data = dict(doc)
        data.pop("_id", None)
        data.setdefault("version", 1)
        data.setdefault("is_active", True)

        for key in ("created_at", "updated_at"):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = value.isoformat()

        return data

    async def create_user(
        self,
        user_id: str,
        email: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new user profile document."""
        await self._ensure_indexes()

        try:
            if not username:
                username = email.split("@")[0]

            if await self.collection.find_one({"id": user_id}, {"_id": 1}):
                return {
                    "status": "error",
                    "message": f"User with ID {user_id} already exists",
                    "data": None,
                }

            if await self.collection.find_one({"email": email}, {"_id": 1}):
                return {
                    "status": "error",
                    "message": f"Email {email} already registered",
                    "data": None,
                }

            if await self.collection.find_one({"username": username}, {"_id": 1}):
                return {
                    "status": "error",
                    "message": f"Username {username} already in use",
                    "data": None,
                }

            now_iso = self._utc_now_iso()
            payload = {
                "id": user_id,
                "email": email,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "version": 1,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

            await self.collection.insert_one(payload)
            created = await self.collection.find_one({"id": user_id})
            return {
                "status": "success",
                "message": "User created successfully",
                "data": self._normalize_user(created),
            }
        except DuplicateKeyError as exc:
            return {
                "status": "error",
                "message": f"Database integrity error: {str(exc)}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error creating user: {str(exc)}",
                "data": None,
            }

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get user profile by ID."""
        try:
            user = await self.collection.find_one({"id": user_id})
            if not user:
                return {
                    "status": "error",
                    "message": f"User with ID {user_id} not found",
                    "data": None,
                }

            return {
                "status": "success",
                "message": "User retrieved successfully",
                "data": self._normalize_user(user),
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
        """Update multiple mutable user fields."""
        payload = {
            "email": email,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        }
        return await self.apply_profile_patch(user_id=user_id, payload=payload)

    async def update_username(self, user_id: str, username: str) -> Dict[str, Any]:
        """Update only username."""
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
        """Apply profile updates with optional optimistic version checks."""
        await self._ensure_indexes()

        try:
            existing_doc = await self.collection.find_one({"id": user_id})
            if not existing_doc:
                return {
                    "status": "error",
                    "message": f"User with ID {user_id} not found",
                    "data": None,
                }

            existing = self._normalize_user(existing_doc) or {}
            current_version = int(existing.get("version") or 1)

            if expected_version is not None and current_version != expected_version:
                return {
                    "status": "conflict",
                    "message": "Version conflict",
                    "data": existing,
                }

            updates: Dict[str, Any] = {}

            email = payload.get("email")
            if email is not None and email != existing.get("email"):
                email_owner = await self.collection.find_one(
                    {"email": email, "id": {"$ne": user_id}},
                    {"_id": 1},
                )
                if email_owner:
                    return {
                        "status": "error",
                        "message": "Email already in use",
                        "data": None,
                    }
                updates["email"] = email

            username = payload.get("username")
            if username is not None and username != existing.get("username"):
                username_owner = await self.collection.find_one(
                    {"username": username, "id": {"$ne": user_id}},
                    {"_id": 1},
                )
                if username_owner:
                    return {
                        "status": "error",
                        "message": "Username already in use",
                        "data": None,
                    }
                updates["username"] = username

            first_name = payload.get("first_name")
            if first_name is not None and first_name != existing.get("first_name"):
                updates["first_name"] = first_name

            last_name = payload.get("last_name")
            if last_name is not None and last_name != existing.get("last_name"):
                updates["last_name"] = last_name

            if not updates:
                return {
                    "status": "success",
                    "message": "No changes applied",
                    "data": existing,
                }

            updates["updated_at"] = self._utc_now_iso()
            filter_query: Dict[str, Any] = {"id": user_id}
            if expected_version is not None:
                filter_query["version"] = expected_version

            updated_doc = await self.collection.find_one_and_update(
                filter_query,
                {"$set": updates, "$inc": {"version": 1}},
                return_document=ReturnDocument.AFTER,
            )

            if not updated_doc:
                latest_doc = await self.collection.find_one({"id": user_id})
                latest = self._normalize_user(latest_doc)
                if expected_version is not None and latest is not None:
                    return {
                        "status": "conflict",
                        "message": "Version conflict",
                        "data": latest,
                    }
                return {
                    "status": "error",
                    "message": "Failed to update user",
                    "data": latest,
                }

            return {
                "status": "success",
                "message": "User updated successfully",
                "data": self._normalize_user(updated_doc),
            }
        except DuplicateKeyError as exc:
            return {
                "status": "error",
                "message": f"Database integrity error: {str(exc)}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error updating user: {str(exc)}",
                "data": None,
            }

