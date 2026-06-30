"""Alembic environment configuration for database migrations."""
from __future__ import annotations

from logging.config import fileConfig
import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL
from dotenv import load_dotenv

# Add the app directory to the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from models.sql import Base  # noqa: E402
import models.sql  # noqa: F401,E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_version_table() -> str:
    """
    Return the Alembic version table configured for this migration scope.

    Args:
        None.

    Returns:
        str: Version table name from Alembic configuration, defaulting to the
        shared ``alembic_version`` table.

    Side Effects:
        None.
    """
    return config.get_main_option("version_table", "alembic_version")


def get_url() -> str:
    """Get database URL from environment variables."""
    load_dotenv()
    db_type = (os.getenv("DB_TYPE", "postgresql") or "").strip().lower()
    if db_type not in {"postgresql", "postgres", "mysql", "sqlite"}:
        raise ValueError(
            "Alembic migrations are only supported for SQL databases. "
            f"Current DB_TYPE: {db_type}"
        )

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5433")
        db_name = os.getenv("DB_NAME", "")
        db_user = os.getenv("DB_USER", "")

        db_password_file = os.getenv("DB_PASSWORD_FILE", "")
        if db_password_file and Path(db_password_file).exists():
            db_password = Path(db_password_file).read_text().strip()
        else:
            db_password = os.getenv("DB_PASSWORD", "")

        if db_type in {"postgresql", "postgres"}:
            if not all([db_host, db_name, db_user, db_password]):
                raise ValueError(
                    "Missing PostgreSQL configuration. Set DATABASE_URL or provide "
                    "DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD/DB_PASSWORD_FILE."
                )
            database_url = URL.create(
                "postgresql",
                username=db_user,
                password=db_password,
                host=db_host,
                port=int(db_port),
                database=db_name,
            ).render_as_string(hide_password=False)
        elif db_type == "mysql":
            if not all([db_host, db_name, db_user, db_password]):
                raise ValueError(
                    "Missing MySQL configuration. Set DATABASE_URL or provide "
                    "DB_HOST, DB_NAME, DB_USER, and DB_PASSWORD/DB_PASSWORD_FILE."
                )
            database_url = URL.create(
                "mysql+pymysql",
                username=db_user,
                password=db_password,
                host=db_host,
                port=int(db_port),
                database=db_name,
            ).render_as_string(hide_password=False)
        elif db_type == "sqlite":
            if not db_name:
                raise ValueError("Missing SQLite DB_NAME. Set DATABASE_URL or DB_NAME.")
            database_url = f"sqlite:///{db_name}"

    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://")
    if database_url.startswith("mysql+aiomysql://"):
        return database_url.replace("mysql+aiomysql://", "mysql+pymysql://")
    return database_url


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=get_version_table(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=get_version_table(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
