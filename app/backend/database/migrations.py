"""Database migration utilities using Alembic."""
import os
import sys
from pathlib import Path
from alembic import command
from alembic.config import Config
from api.settings import settings


def run_migrations():
    """
    Run database migrations automatically on startup.
    
    This function:
    1. Locates the alembic.ini file
    2. Runs all pending migrations
    3. Only works with SQL databases (PostgreSQL, MySQL, SQLite)
    """
    # Only run migrations for SQL databases
    if settings.DB_TYPE not in ["postgresql", "postgres", "mysql", "sqlite"]:
        print(f"⚠️  Migrations skipped: DB_TYPE={settings.DB_TYPE} (only SQL databases supported)")
        return
    
    # Get the project root directory (where alembic.ini is located)
    # In Docker: /app/backend/database/migrations.py -> /app/
    # Go up: migrations.py -> database -> backend -> project_root (/app)
    current_file = Path(__file__).resolve()
    # From /app/backend/database/migrations.py, go up 3 levels to /app/
    project_root = current_file.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"
    
    if not alembic_ini_path.exists():
        print(f"⚠️  Alembic configuration not found at: {alembic_ini_path}")
        print(f"   Current file: {current_file}")
        print(f"   Project root: {project_root}")
        print("   Skipping migrations...")
        return
    
    try:
        print("🔄 Running database migrations...")
        
        # Create Alembic configuration
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Set the script location (alembic directory)
        alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
        
        # Run migrations to the latest version
        command.upgrade(alembic_cfg, "head")
        
        print("✅ Database migrations completed successfully")
        
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        print("   The application will continue, but database schema may be outdated.")
        print("   Please run migrations manually: alembic upgrade head")


def create_migration(message: str):
    """
    Create a new migration file.
    
    Args:
        message: Description of the migration
        
    Usage:
        from backend.database.migrations import create_migration
        create_migration("add users table")
    """
    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"
    
    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {alembic_ini_path}")
    
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    
    # Generate migration with autogenerate
    command.revision(alembic_cfg, message=message, autogenerate=True)
    print(f"✅ Migration created: {message}")


def get_current_revision():
    """Get the current database revision."""
    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"
    
    if not alembic_ini_path.exists():
        return None
    
    try:
        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
        
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        
        # Get database URL
        if settings.DB_TYPE in ["postgresql", "postgres"]:
            db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        else:
            db_url = settings.DATABASE_URL
        
        engine = create_engine(db_url)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            return current_rev
            
    except Exception as e:
        print(f"Error getting current revision: {e}")
        return None
