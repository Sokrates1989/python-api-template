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
        
        # Debug logging (only if DEBUG is enabled)
        if settings.DEBUG:
            print(f"🔍 Debug - DB_HOST: {settings.DB_HOST}")
            print(f"🔍 Debug - DB_USER: {settings.DB_USER}")
            print(f"🔍 Debug - DB_NAME: {settings.DB_NAME}")
            print(f"🔍 Debug - DB_PORT: {settings.DB_PORT}")
            print(f"🔍 Debug - DB_PASSWORD_FILE: {settings.DB_PASSWORD_FILE}")
            print(f"🔍 Debug - DATABASE_URL (from env): {settings.DATABASE_URL}")
            
            # Mask password in URL for logging
            import re
            masked_url = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', database_url) if database_url else '<EMPTY>'
            print(f"🔍 Debug - Constructed database_url: {masked_url}")
        
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
