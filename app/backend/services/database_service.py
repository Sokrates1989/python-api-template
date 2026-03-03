"""
Database service - handles database operations business logic.

This service provides a clean interface for database operations.
It automatically uses the configured database backend (Neo4j, SQL, or MongoDB).
"""
from dataclasses import asdict
from typing import Dict, Any

from backend.adapters.provider_capability_factory import (
    get_provider_capabilities_for_db_type,
)
from backend.database import test_database_connection, get_database_handler
from backend.database.neo4j_handler import Neo4jHandler
from backend.database.mongodb_handler import MongoDBHandler
from backend.database.sql_handler import SQLHandler


class DatabaseService:
    """Service for database operations."""
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test database connection.
        
        Returns:
            Dictionary with connection status and details
        """
        return await test_database_connection()
    
    async def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the current database.
        
        Returns:
            Dictionary with database type and connection info
        """
        handler = get_database_handler()
        try:
            capabilities = asdict(
                get_provider_capabilities_for_db_type(getattr(handler, "db_type", ""))
            )
        except ValueError:
            capabilities = {}
        
        if isinstance(handler, Neo4jHandler):
            return {
                "database_type": "neo4j",
                "description": "Graph database for connected data",
                "capabilities": capabilities,
            }
        elif isinstance(handler, SQLHandler):
            return {
                "database_type": "sql",
                "description": "Relational database",
                "url": handler._mask_password(handler.database_url),
                "capabilities": capabilities,
            }
        elif isinstance(handler, MongoDBHandler):
            return {
                "database_type": "mongodb",
                "description": "Document database",
                "url": handler.url,
                "database_name": handler.database_name,
                "capabilities": capabilities,
            }
        else:
            return {
                "database_type": "unknown",
                "description": "Unknown database type"
            }
    
    async def execute_sample_query(self) -> Dict[str, Any]:
        """
        Execute a sample query based on database type.
        
        Returns:
            Dictionary with query results
        """
        handler = get_database_handler()
        
        try:
            if isinstance(handler, Neo4jHandler):
                # Neo4j Cypher query
                results = await handler.execute_query("RETURN 'Hello from Neo4j' as message")
                return {"status": "success", "results": results}
            
            elif isinstance(handler, SQLHandler):
                # SQL query
                results = await handler.execute_query("SELECT 'Hello from SQL' as message")
                return {"status": "success", "results": results}
            elif isinstance(handler, MongoDBHandler):
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
            
            else:
                return {"status": "error", "message": "Unknown database type"}
        
        except Exception as e:
            return {"status": "error", "message": str(e)}
