"""Example service for MongoDB-backed example records."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from backend.database import get_database_handler
from backend.database.mongodb_handler import MongoDBHandler


class ExampleService:
    """Service for MongoDB example operations."""

    def __init__(self):
        handler = get_database_handler()
        if not isinstance(handler, MongoDBHandler):
            raise ValueError("MongoDB ExampleService requires MongoDB database")

        self.handler = handler
        self.collection = handler.database["examples"]
        self._indexes_initialized = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_initialized:
            return

        await self.collection.create_index("id", unique=True, name="idx_examples_id_unique")
        await self.collection.create_index("name", name="idx_examples_name")
        await self.collection.create_index("created_at", name="idx_examples_created_at")
        self._indexes_initialized = True

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_example(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None

        data = dict(doc)
        data.pop("_id", None)

        for key in ("created_at", "updated_at"):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = value.isoformat()

        return data

    async def create_example(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        await self._ensure_indexes()

        try:
            now_iso = self._utc_now_iso()
            example_id = str(uuid4())
            payload = {
                "id": example_id,
                "name": name,
                "description": description,
                "created_at": now_iso,
                "updated_at": None,
            }
            await self.collection.insert_one(payload)

            created = await self.collection.find_one({"id": example_id})
            return {
                "status": "success",
                "message": "Example created successfully",
                "data": self._normalize_example(created),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to create example: {str(exc)}",
            }

    async def get_example(self, example_id: str) -> Dict[str, Any]:
        try:
            doc = await self.collection.find_one({"id": example_id})
            if not doc:
                return {
                    "status": "error",
                    "message": f"Example with id {example_id} not found",
                }

            return {
                "status": "success",
                "data": self._normalize_example(doc),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to get example: {str(exc)}",
            }

    async def list_examples(
        self,
        limit: int = 100,
        offset: int = 0,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            filter_doc: Dict[str, Any] = {}
            if name:
                filter_doc["name"] = name

            cursor = (
                self.collection.find(filter_doc)
                .sort("created_at", -1)
                .skip(offset)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            total = await self.collection.count_documents(filter_doc)

            data = [self._normalize_example(doc) for doc in docs if doc]
            return {
                "status": "success",
                "data": data,
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "count": len(data),
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to list examples: {str(exc)}",
            }

    async def update_example(
        self,
        example_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            existing = await self.collection.find_one({"id": example_id})
            if not existing:
                return {
                    "status": "error",
                    "message": f"Example with id {example_id} not found",
                }

            updates: Dict[str, Any] = {}
            if name is not None:
                updates["name"] = name
            if description is not None:
                updates["description"] = description

            if not updates:
                return {
                    "status": "success",
                    "message": "No changes applied",
                    "data": self._normalize_example(existing),
                }

            updates["updated_at"] = self._utc_now_iso()
            await self.collection.update_one({"id": example_id}, {"$set": updates})

            updated = await self.collection.find_one({"id": example_id})
            return {
                "status": "success",
                "message": "Example updated successfully",
                "data": self._normalize_example(updated),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to update example: {str(exc)}",
            }

    async def delete_example(self, example_id: str) -> Dict[str, Any]:
        try:
            result = await self.collection.delete_one({"id": example_id})
            if result.deleted_count == 0:
                return {
                    "status": "error",
                    "message": f"Example with id {example_id} not found",
                }

            return {
                "status": "success",
                "message": f"Example {example_id} deleted successfully",
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to delete example: {str(exc)}",
            }

    async def delete_all_examples(self) -> Dict[str, Any]:
        try:
            result = await self.collection.delete_many({})
            return {
                "status": "success",
                "message": f"Deleted {result.deleted_count} example(s)",
                "deleted_count": result.deleted_count,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to delete all examples: {str(exc)}",
            }
