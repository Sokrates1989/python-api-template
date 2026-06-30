"""Database migration utilities using Alembic."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from api.settings import settings
from backend.observability import log_event

if TYPE_CHECKING:
    from alembic.config import Config

logger = logging.getLogger("backend.database.migrations")


def run_migrations(fail_on_error: bool = False) -> bool:
    """
    Run database migrations automatically on startup.

    Args:
        fail_on_error: Raise exception on migration failure when True.

    Returns:
        bool: True when migrations succeeded or were not required.
    """
    from alembic.config import Config

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
        global_cfg = Config(str(alembic_ini_path))
        _configure_global_alembic_paths(global_cfg, project_root)
        _run_migration_scope(
            alembic_cfg=global_cfg,
            version_table="alembic_version",
            scope="global",
        )

        app_cfg = Config(str(alembic_ini_path))
        if _configure_selected_app_alembic_paths(app_cfg, project_root):
            selected_app = settings.get_backend_app_definition()
            _run_migration_scope(
                alembic_cfg=app_cfg,
                version_table=f"alembic_version_{_safe_identifier(selected_app.app_id)}",
                scope=f"app:{selected_app.app_id}",
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


def _configure_global_alembic_paths(alembic_cfg: "Config", project_root: Path) -> None:
    """
    Configure Alembic to run shared global migrations only.

    Args:
        alembic_cfg (Config): Alembic configuration to mutate.
        project_root (Path): Repository root containing ``alembic``.

    Returns:
        None.

    Side Effects:
        Sets Alembic script and version-location options for shared migrations.
    """
    global_versions = project_root / "alembic" / "versions"
    _set_alembic_paths(alembic_cfg, project_root, (global_versions,))
    log_event(
        logger,
        logging.INFO,
        "migrations.version_locations",
        scope="global",
        locations=[str(global_versions)],
    )


def _configure_selected_app_alembic_paths(alembic_cfg: "Config", project_root: Path) -> bool:
    """
    Configure Alembic to run migrations owned by the selected app.

    Args:
        alembic_cfg (Config): Alembic configuration to mutate.
        project_root (Path): Repository root containing ``app/apps``.

    Returns:
        bool: True when at least one selected-app version directory exists.

    Side Effects:
        Sets Alembic script and version-location options for selected-app
        migrations.
    """
    selected_app = settings.get_backend_app_definition()
    app_root = project_root / "app" / "apps" / selected_app.app_id
    version_locations = []

    for location in selected_app.migration_version_locations:
        path = Path(location)
        resolved_path = path if path.is_absolute() else app_root / path
        if resolved_path.exists():
            version_locations.append(resolved_path)
        else:
            log_event(
                logger,
                logging.WARNING,
                "migrations.app_version_location_missing",
                app_id=selected_app.app_id,
                path=str(resolved_path),
            )

    if not version_locations:
        log_event(
            logger,
            logging.INFO,
            "migrations.app_scope_skipped",
            app_id=selected_app.app_id,
        )
        return False

    _set_alembic_paths(alembic_cfg, project_root, tuple(version_locations))
    log_event(
        logger,
        logging.INFO,
        "migrations.version_locations",
        scope=f"app:{selected_app.app_id}",
        locations=[str(path) for path in version_locations],
    )
    return True


def _set_alembic_paths(
    alembic_cfg: "Config",
    project_root: Path,
    version_locations: tuple[Path, ...],
) -> None:
    """
    Apply script and version-location options to an Alembic config.

    Args:
        alembic_cfg (Config): Alembic configuration to mutate.
        project_root (Path): Repository root containing the shared Alembic env.
        version_locations (tuple[Path, ...]): Directories containing revision
            files for this migration scope.

    Returns:
        None.

    Side Effects:
        Mutates Alembic configuration options.
    """
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option(
        "version_locations",
        os.pathsep.join(str(path) for path in version_locations),
    )
    alembic_cfg.set_main_option("version_path_separator", "os")


def _run_migration_scope(alembic_cfg: "Config", version_table: str, scope: str) -> None:
    """
    Run one configured Alembic migration scope.

    Args:
        alembic_cfg (Config): Alembic configuration for the scope.
        version_table (str): Version table that tracks this migration scope.
        scope (str): Human-readable scope label for logs.

    Returns:
        None.

    Raises:
        Exception: Propagates Alembic or database errors.

    Side Effects:
        Applies pending SQL migrations for one scope.
    """
    from alembic import command

    alembic_cfg.set_main_option("version_table", version_table)
    log_event(logger, logging.INFO, "migrations.status_check.begin", scope=scope)
    current_version = _get_current_version(version_table=version_table)
    if current_version:
        log_event(
            logger,
            logging.INFO,
            "migrations.status_check.current_version",
            scope=scope,
            current_version=current_version,
        )
    else:
        log_event(logger, logging.INFO, "migrations.status_check.no_version", scope=scope)

    pending = _get_pending_migrations(alembic_cfg, current_version)
    if not pending:
        log_event(logger, logging.INFO, "migrations.no_pending", scope=scope)
        return

    log_event(
        logger,
        logging.INFO,
        "migrations.pending",
        scope=scope,
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

    final_version = _get_current_version(version_table=version_table)
    log_event(logger, logging.INFO, "migrations.complete", scope=scope, applied=len(pending))
    if final_version:
        log_event(
            logger,
            logging.INFO,
            "migrations.final_version",
            scope=scope,
            final_version=final_version,
        )


def _get_current_version(version_table: str = "alembic_version") -> str | None:
    """
    Get the current database migration version for one scope.

    Args:
        version_table (str): Alembic version table to inspect.

    Returns:
        str | None: Current revision for the version table, or None when the
        table does not exist or cannot be read.

    Side Effects:
        Opens a short-lived SQLAlchemy connection.
    """
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    try:
        db_url = settings.get_database_url()
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        if db_url.startswith("mysql+aiomysql://"):
            db_url = db_url.replace("mysql+aiomysql://", "mysql+pymysql://")

        engine = create_engine(db_url)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"version_table": version_table})
            return context.get_current_revision()
    except Exception:
        return None


def _get_pending_migrations(alembic_cfg: "Config", current_version: str | None):
    """
    Get pending revisions for one configured Alembic scope.

    Args:
        alembic_cfg (Config): Alembic configuration with version locations set.
        current_version (str | None): Current version from the scope's version
            table.

    Returns:
        list[dict[str, str]]: Pending revision metadata in application order.

    Side Effects:
        Logs a warning when Alembic cannot inspect the configured script tree.
    """
    from alembic.script import ScriptDirectory

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
    Create a new shared migration file.

    Args:
        message (str): Description of the migration.

    Returns:
        None.

    Side Effects:
        Writes a new revision into the global Alembic version tree. App-specific
        migrations should be created inside the owning app slice instead.
    """
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).parent.parent.parent.parent
    alembic_ini_path = project_root / "alembic.ini"

    if not alembic_ini_path.exists():
        raise FileNotFoundError(f"Alembic configuration not found at: {alembic_ini_path}")

    alembic_cfg = Config(str(alembic_ini_path))
    _configure_global_alembic_paths(alembic_cfg, project_root)
    command.revision(alembic_cfg, message=message, autogenerate=True)
    log_event(logger, logging.INFO, "migrations.created", message=message)


def get_current_revision():
    """
    Fetch the current shared migration revision.

    Args:
        None.

    Returns:
        str | None: Current shared Alembic revision, or None when unavailable.

    Side Effects:
        Opens a short-lived SQLAlchemy connection.
    """
    return _get_current_version()


def _safe_identifier(value: str) -> str:
    """
    Convert an app id into a safe SQL identifier fragment.

    Args:
        value (str): Raw application identifier.

    Returns:
        str: Lowercase identifier fragment containing only letters, digits, and
        underscores.

    Side Effects:
        None.
    """
    normalized = "".join(char if char.isalnum() else "_" for char in value.lower())
    return normalized.strip("_") or "app"
