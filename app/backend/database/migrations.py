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
    2. Checks current migration version
    3. Runs all pending migrations
    4. Reports final version
    5. Only works with SQL databases (PostgreSQL, MySQL, SQLite)
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
        # Create Alembic configuration
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Set the script location (alembic directory)
        alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
        
        # Get current version before migration
        print("🔄 Checking migration status...")
        current_version = _get_current_version(alembic_cfg)
        
        if current_version:
            print(f"📍 Current database version: {current_version[:12]}...")
        else:
            print("📍 Database not initialized (no migrations applied yet)")
        
        # Check if there are pending migrations
        pending = _get_pending_migrations(alembic_cfg, current_version)
        
        if pending:
            print(f"🔄 Running {len(pending)} pending migration(s)...")
            for migration in pending:
                print(f"   ⏩ {migration}")
        else:
            print("✅ Database is up to date - no migrations needed")
            return
        
        # Run migrations to the latest version
        command.upgrade(alembic_cfg, "head")
        
        # Get final version after migration
        final_version = _get_current_version(alembic_cfg)
        
        print(f"✅ Migrations completed successfully!")
        print(f"📍 New database version: {final_version[:12]}...")
        
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        print("   The application will continue, but database schema may be outdated.")
        print("   Please run migrations manually: alembic upgrade head")


def _get_current_version(alembic_cfg):
    """Get the current database migration version."""
    try:
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
    except Exception:
        return None


def _get_pending_migrations(alembic_cfg, current_version):
    """Get list of pending migrations."""
    try:
        from alembic.script import ScriptDirectory
        
        script = ScriptDirectory.from_config(alembic_cfg)
        
        # Get all revisions from current to head
        if current_version:
            # Get revisions between current and head
            revisions = []
            for rev in script.iterate_revisions(current_version, "head"):
                if rev.revision != current_version:
                    # Format: revision_id - description
                    desc = rev.doc.split('\n')[0] if rev.doc else "No description"
                    revisions.append(f"{rev.revision[:12]} - {desc}")
            return list(reversed(revisions))  # Show in chronological order
        else:
            # No current version - all migrations are pending
            revisions = []
            for rev in script.walk_revisions():
                desc = rev.doc.split('\n')[0] if rev.doc else "No description"
                revisions.append(f"{rev.revision[:12]} - {desc}")
            return list(reversed(revisions))
    except Exception as e:
        print(f"   Warning: Could not determine pending migrations: {e}")
        return []


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
