"""
MongoDB database handler implementation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseDatabaseHandler

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - handled at runtime
    AsyncIOMotorClient = None  # type: ignore[assignment]


class MongoDBHandler(BaseDatabaseHandler):
    """Handler for MongoDB document database."""

    def __init__(self, url: str, database: str, **kwargs):
        """
        Initialize MongoDB connection.

        Args:
            url: MongoDB connection URL
            database: Database name
        """
        if AsyncIOMotorClient is None:
            raise RuntimeError(
                "MongoDB support requires 'motor'. Install dependencies and rebuild the image."
            )

        self.db_type = "mongodb"
        self.url = url
        self.database_name = database
        self.client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
        self.database = self.client[database]

    def close(self):
        """Close MongoDB client."""
        if self.client:
            self.client.close()

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the MongoDB connection.

        Returns:
            Dict with status and message
        """
        try:
            await self.client.admin.command("ping")
            return {
                "status": "success",
                "message": "MongoDB connection successful",
                "database_type": "mongodb",
                "database_name": self.database_name,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"MongoDB connection failed: {str(exc)}",
                "database_type": "mongodb",
            }

    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Any]:
        """
        Execute a simple MongoDB operation.

        Supported operations:
            - query='find'
            - query='count_documents'
            - query='insert_one'
        """
        params = params or {}
        collection_name = params.get("collection")
        if not collection_name:
            raise ValueError("MongoDB operation requires 'collection' parameter")

        collection = self.database[collection_name]

        if query == "find":
            filter_doc = params.get("filter", {})
            limit = int(params.get("limit", 100))
            docs = await collection.find(filter_doc).limit(limit).to_list(length=limit)
            return [self._normalize_doc(doc) for doc in docs]

        if query == "count_documents":
            filter_doc = params.get("filter", {})
            count = await collection.count_documents(filter_doc)
            return [{"count": count}]

        if query == "insert_one":
            payload = params.get("document")
            if not isinstance(payload, dict):
                raise ValueError("insert_one requires 'document' dict")
            result = await collection.insert_one(payload)
            return [{"inserted_id": str(result.inserted_id)}]

        raise ValueError(f"Unsupported MongoDB query operation: {query}")

    def _normalize_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize MongoDB document into JSON-serializable dictionary."""
        normalized = dict(doc)
        if "_id" in normalized:
            normalized["_id"] = str(normalized["_id"])
        return normalized
