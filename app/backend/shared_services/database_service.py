"""
Shared database service used by backend app route modules.

This service provides a clean interface for database operations and resolves the
active provider at runtime.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from backend.adapters.provider_capability_factory import get_provider_capabilities_for_db_type
from backend.database import get_database_handler, test_database_connection


class DatabaseService:
    """Service for database operations."""

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test database connection.

        Args:
            None.

        Returns:
            Dict[str, Any]: Connection status and provider details.

        Side Effects:
            Opens a short-lived database interaction through the active handler.
        """
        return await test_database_connection()

    async def get_database_info(self) -> Dict[str, Any]:
        """
        Return information about the active database provider.

        Args:
            None.

        Returns:
            Dict[str, Any]: Provider type, description, and capability metadata.

        Side Effects:
            Reads runtime state from the active database handler.
        """
        handler = get_database_handler()
        try:
            capabilities = asdict(
                get_provider_capabilities_for_db_type(getattr(handler, "db_type", ""))
            )
        except ValueError:
            capabilities = {}

        normalized_db_type = getattr(handler, "db_type", "").strip().lower()
        if normalized_db_type == "neo4j":
            return {
                "database_type": "neo4j",
                "description": "Graph database for connected data",
                "capabilities": capabilities,
            }
        if normalized_db_type == "sql":
            masked_url = handler._mask_password(handler.database_url) if hasattr(handler, "_mask_password") else getattr(handler, "database_url", "")
            return {
                "database_type": "sql",
                "description": "Relational database",
                "url": masked_url,
                "capabilities": capabilities,
            }
        if normalized_db_type == "mongodb":
            return {
                "database_type": "mongodb",
                "description": "Document database",
                "url": getattr(handler, "url", ""),
                "database_name": getattr(handler, "database_name", ""),
                "capabilities": capabilities,
            }
        return {
            "database_type": "unknown",
            "description": "Unknown database type",
        }

    async def execute_sample_query(self) -> Dict[str, Any]:
        """
        Execute a provider-specific sample query.

        Args:
            None.

        Returns:
            Dict[str, Any]: Query status and example results.

        Side Effects:
            Executes a sample read operation against the active provider.
        """
        handler = get_database_handler()
        normalized_db_type = getattr(handler, "db_type", "").strip().lower()

        try:
            if normalized_db_type == "neo4j":
                results = await handler.execute_query("RETURN 'Hello from Neo4j' as message")
                return {"status": "success", "results": results}
            if normalized_db_type == "sql":
                results = await handler.execute_query("SELECT 'Hello from SQL' as message")
                return {"status": "success", "results": results}
            if normalized_db_type == "mongodb":
                results = await handler.execute_query(
                    "count_documents",
                    {"collection": "users", "filter": {}},
                )
                return {
                    "status": "success",
                    "results": [
                        {
                            "message": "Hello from MongoDB",
                            "users_collection_count": results[0].get("count", 0) if results else 0,
                        }
                    ],
                }
            return {"status": "error", "message": "Unknown database type"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
