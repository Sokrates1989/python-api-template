"""
Database initialization and lifecycle management.
"""
from api.settings import settings
from .factory import DatabaseFactory


async def initialize_database():
    """
    Initialize database handler based on configuration.
    
    Returns:
        dict: Result of connection test with status and message
    """
    print(f"🔧 Initializing {settings.DB_TYPE} database...")
    
    if settings.DB_TYPE == "neo4j":
        handler = DatabaseFactory.create_handler(
            db_type="neo4j",
            url=settings.NEO4J_URL,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD
        )
    else:  # SQL databases
        handler = DatabaseFactory.create_handler(
            db_type=settings.DB_TYPE,
            database_url=settings.DATABASE_URL,
            echo=settings.DEBUG
        )
    
    DatabaseFactory.set_instance(handler)
    
    # Test the connection
    result = await handler.test_connection()
    if result["status"] == "success":
        print(f"✅ {result['message']}")
    else:
        print(f"❌ {result['message']}")
    
    return result


async def close_database():
    """Close database connection."""
    print("🔧 Closing database connection...")
    DatabaseFactory.close_instance()
    print("✅ Database connection closed")
