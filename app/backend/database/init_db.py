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
        # Get password from file or environment
        password = settings.get_db_password()
        handler = DatabaseFactory.create_handler(
            db_type="neo4j",
            url=settings.NEO4J_URL,
            user=settings.DB_USER,
            password=password
        )
    else:  # SQL databases
        # Get database URL (builds from components if needed)
        database_url = settings.get_database_url()
        handler = DatabaseFactory.create_handler(
            db_type=settings.DB_TYPE,
            database_url=database_url,
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
