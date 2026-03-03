"""Database migration utilities using Alembic."""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from api.settings import settings
from backend.observability import log_event

logger = logging.getLogger("backend.database.migrations")


def run_migrations(fail_on_error: bool = False) -> bool:
    """
    Run database migrations automatically on startup.

    Args:
        fail_on_error: Raise exception on migration failure when True.

    Returns:
        bool: True when migrations succeeded or were not required.
    """
    if not settings.is_sql_database():
        log_event(
            logger,
            logging.INFO,
            "migrations.skipped_non_sql",
            db_type=settings.DB_TYPE,
        )
        return True

    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"
    if not alembic_ini_path.exists():
        log_event(
            logger,
            logging.WARNING,
            "migrations.skipped_missing_config",
            alembic_ini_path=str(alembic_ini_path),
        )
        return True

    try:
        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))

        log_event(logger, logging.INFO, "migrations.status_check.begin")
        current_version = _get_current_version()
        if current_version:
            log_event(
                logger,
                logging.INFO,
                "migrations.status_check.current_version",
                current_version=current_version,
            )
        else:
            log_event(
                logger,
                logging.INFO,
                "migrations.status_check.no_version",
            )

        pending = _get_pending_migrations(alembic_cfg, current_version)
        if not pending:
            log_event(logger, logging.INFO, "migrations.no_pending")
            return True

        log_event(
            logger,
            logging.INFO,
            "migrations.pending",
            count=len(pending),
            revisions=pending,
        )

        logging.getLogger("alembic").setLevel(logging.ERROR)
        logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
        try:
            alembic_cfg.set_main_option("sqlalchemy.echo", "false")
            command.upgrade(alembic_cfg, "head")
        finally:
            logging.getLogger("alembic").setLevel(logging.INFO)
            logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

        final_version = _get_current_version()
        log_event(
            logger,
            logging.INFO,
            "migrations.complete",
            applied=len(pending),
        )
        if final_version:
            log_event(
                logger,
                logging.INFO,
                "migrations.final_version",
                final_version=final_version,
            )
        return True
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "migrations.failed",
            error=str(exc),
            manual_hint="alembic upgrade head",
        )
        if fail_on_error:
            raise
        return False


def _get_current_version() -> str | None:
    """Get the current database migration version."""
    try:
        db_url = settings.get_database_url()
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        if db_url.startswith("mysql+aiomysql://"):
            db_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://")

        engine = create_engine(db_url)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()
    except Exception:
        return None


def _get_pending_migrations(alembic_cfg: Config, current_version: str | None):
    """Get list of pending migrations with revision metadata."""
    try:
        script = ScriptDirectory.from_config(alembic_cfg)
        if current_version:
            revisions = []
            for rev in script.iterate_revisions("head", current_version):
                if rev.revision != current_version:
                    desc = rev.doc.split("\n")[0] if rev.doc else "No description"
                    revisions.append({"revision": rev.revision, "description": desc})
            return list(reversed(revisions))

        revisions = []
        for rev in script.walk_revisions():
            desc = rev.doc.split("\n")[0] if rev.doc else "No description"
            revisions.append({"revision": rev.revision, "description": desc})
        return list(reversed(revisions))
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "migrations.pending_detection_failed",
            error=str(exc),
        )
        return []


def create_migration(message: str):
    """
    Create a new migration file.

    Args:
        message: Description of the migration
    """
    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"

    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {alembic_ini_path}")

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    command.revision(alembic_cfg, message=message, autogenerate=True)
    log_event(logger, logging.INFO, "migrations.created", message=message)


def get_current_revision():
    """Backward-compatible alias to fetch current migration revision."""
    return _get_current_version()
