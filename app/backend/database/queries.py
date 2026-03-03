"""
Database query helpers and utilities.
Provides a clean interface for executing database queries.
"""
from typing import Any, Dict, List, Optional
from .factory import get_database_handler


async def test_database_connection() -> Dict[str, Any]:
    """
    Test database connection and execute a simple query.
    
    Returns:
        dict: Connection status and query results
    """
    handler = get_database_handler()
    
    # Test connection
    connection_result = await handler.test_connection()
    
    handler_type = getattr(handler, "db_type", "")

    # For Neo4j, also run a test query
    if handler_type == "neo4j":
        try:
            query_result = await handler.execute_query("RETURN 1 AS test")
            return {
                "status": "success",
                "connection": connection_result,
                "query_result": query_result
            }
        except Exception as e:
            return {
                "status": "partial_success",
                "connection": connection_result,
                "query_error": str(e)
            }
    
    # For SQL databases, run a simple query
    elif handler_type == "sql":
        try:
            query_result = await handler.execute_query("SELECT 1 as test")
            return {
                "status": "success",
                "connection": connection_result,
                "query_result": query_result
            }
        except Exception as e:
            return {
                "status": "partial_success",
                "connection": connection_result,
                "query_error": str(e)
            }
    
    elif handler_type == "mongodb":
        try:
            query_result = await handler.execute_query(
                "count_documents",
                {"collection": "users", "filter": {}},
            )
            return {
                "status": "success",
                "connection": connection_result,
                "query_result": query_result,
            }
        except Exception as e:
            return {
                "status": "partial_success",
                "connection": connection_result,
                "query_error": str(e),
            }

    # Other providers rely on their own connection test.
    return {"status": "success", "connection": connection_result}


async def execute_query(query: str, params: Optional[Dict] = None) -> List[Any]:
    """
    Execute a database query using the configured handler.
    
    Args:
        query: Query string/operation (Cypher for Neo4j, SQL for SQL databases,
            operation name for MongoDB)
        params: Optional query parameters
        
    Returns:
        List of query results
    """
    handler = get_database_handler()
    return await handler.execute_query(query, params)
