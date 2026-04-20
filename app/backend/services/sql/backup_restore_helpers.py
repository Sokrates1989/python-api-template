"""Restore helpers for SQL database backups."""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from api.settings import settings

from .backup_state import BackupStateTracker


def restore_backup(state: BackupStateTracker, backup_file: Path) -> dict:
    """Restore the configured database from a backup file."""
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    lock_operation = state.check_operation_lock()
    if lock_operation:
        raise Exception(f"Cannot restore: {lock_operation} operation is in progress")

    if not state.acquire_lock("restore"):
        raise Exception("Failed to acquire lock for restore operation")

    db_type = settings.DB_TYPE.lower()
    warnings: list = []

    try:
        state.update_restore_progress(
            status="in_progress",
            message="Starting restore operation...",
            warnings=warnings,
        )
        is_compressed = backup_file.suffix == ".gz"

        state.update_restore_progress(
            status="in_progress",
            message="Dropping existing database data...",
            warnings=warnings,
        )
        drop_database()

        state.update_restore_progress(
            status="in_progress",
            message=f"Restoring {db_type} database from backup...",
            warnings=warnings,
        )
        if db_type in ["postgresql", "postgres"]:
            restore_postgresql(backup_file, is_compressed)
        elif db_type == "mysql":
            restore_mysql(backup_file, is_compressed)
        elif db_type == "sqlite":
            restore_sqlite(backup_file, is_compressed)
        else:
            raise ValueError(f"Restore not supported for database type: {db_type}")

        state.update_restore_progress(
            status="completed",
            message="Restore completed successfully",
            warnings=warnings,
        )
        return {"warnings": warnings, "warning_count": len(warnings)}
    except Exception as exc:
        state.update_restore_progress(
            status="failed",
            message=f"Restore failed: {exc}",
            warnings=warnings,
        )
        raise
    finally:
        state.release_lock()
        if backup_file.exists():
            try:
                backup_file.unlink()
            except Exception as cleanup_error:  # pragma: no cover - defensive fallback
                print(f"Warning: Failed to clean up temp file: {cleanup_error}")


def restore_postgresql(backup_file: Path, is_compressed: bool) -> None:
    """Restore PostgreSQL data using psql."""
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.get_db_password()
    cmd = [
        "psql",
        "-h",
        settings.DB_HOST,
        "-p",
        str(settings.DB_PORT),
        "-U",
        settings.DB_USER,
        "-d",
        settings.DB_NAME,
    ]
    sql_content = _read_text_backup(backup_file, is_compressed)
    try:
        subprocess.run(cmd, env=env, input=sql_content, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise Exception(f"PostgreSQL restore failed: {exc.stderr}") from exc


def restore_mysql(backup_file: Path, is_compressed: bool) -> None:
    """Restore MySQL/MariaDB data using the local client."""
    mysql_cmd = "mariadb" if shutil.which("mariadb") else "mysql"
    cmd = [
        mysql_cmd,
        "-h",
        settings.DB_HOST,
        "-P",
        str(settings.DB_PORT),
        "-u",
        settings.DB_USER,
        f"-p{settings.get_db_password()}",
        settings.DB_NAME,
    ]
    sql_content = _read_text_backup(backup_file, is_compressed)
    try:
        subprocess.run(cmd, input=sql_content, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise Exception(f"MySQL restore failed: {exc.stderr}") from exc


def restore_sqlite(backup_file: Path, is_compressed: bool) -> None:
    """Restore SQLite by replacing the database file."""
    db_file = Path(settings.DB_NAME)
    backup_current = None
    if db_file.exists():
        backup_current = db_file.with_suffix(".db.backup")
        shutil.copy2(db_file, backup_current)

    try:
        if is_compressed:
            with gzip.open(backup_file, "rb") as source, open(db_file, "wb") as target:
                shutil.copyfileobj(source, target)
        else:
            shutil.copy2(backup_file, db_file)
    except Exception as exc:
        if backup_current and backup_current.exists():
            shutil.copy2(backup_current, db_file)
        raise Exception(f"SQLite restore failed: {exc}") from exc


def drop_database() -> None:
    """Drop all user tables for the configured SQL database."""
    db_type = settings.DB_TYPE.lower()
    if db_type in ["postgresql", "postgres"]:
        drop_postgresql_tables()
    elif db_type == "mysql":
        drop_mysql_tables()
    elif db_type == "sqlite":
        drop_sqlite_tables()


def drop_postgresql_tables() -> None:
    """Drop all PostgreSQL tables from the public schema."""
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.get_db_password()
    drop_sql = """
    DO $$ DECLARE
        r RECORD;
    BEGIN
        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
            EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
        END LOOP;
    END $$;
    """
    cmd = [
        "psql",
        "-h",
        settings.DB_HOST,
        "-p",
        str(settings.DB_PORT),
        "-U",
        settings.DB_USER,
        "-d",
        settings.DB_NAME,
    ]
    try:
        subprocess.run(cmd, env=env, input=drop_sql, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise Exception(f"Failed to drop PostgreSQL tables: {exc.stderr}") from exc


def drop_mysql_tables() -> None:
    """Drop all MySQL tables in the configured schema."""
    env = os.environ.copy()
    env["MYSQL_PWD"] = settings.get_db_password()
    drop_sql = f"""
    SET FOREIGN_KEY_CHECKS = 0;
    SET @tables = NULL;
    SELECT GROUP_CONCAT(table_name) INTO @tables
    FROM information_schema.tables
    WHERE table_schema = '{settings.DB_NAME}';
    SET @tables = CONCAT('DROP TABLE IF EXISTS ', @tables);
    PREPARE stmt FROM @tables;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    SET FOREIGN_KEY_CHECKS = 1;
    """
    cmd = _build_mysql_drop_command()
    try:
        subprocess.run(cmd, env=env, input=drop_sql, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise Exception(f"Failed to drop MySQL tables: {exc.stderr}") from exc


def drop_sqlite_tables() -> None:
    """Drop all SQLite tables from the configured database file."""
    db_file = Path(settings.DB_NAME)
    if not db_file.exists():
        return

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table_name, in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        conn.commit()
        conn.close()
    except Exception as exc:
        raise Exception(f"Failed to drop SQLite tables: {exc}") from exc


def _build_mysql_drop_command() -> list[str]:
    """Choose the first available MySQL client command for destructive maintenance."""
    for mysql_cmd in ["mariadb", "mysql"]:
        if shutil.which(mysql_cmd):
            return [
                mysql_cmd,
                "-h",
                settings.DB_HOST,
                "-P",
                str(settings.DB_PORT),
                "-u",
                settings.DB_USER,
                settings.DB_NAME,
            ]
    raise Exception("Neither mariadb nor mysql command found")


def _read_text_backup(backup_file: Path, is_compressed: bool) -> str:
    """Read plain or gzipped SQL backup content as text."""
    if is_compressed:
        with gzip.open(backup_file, "rt", encoding="utf-8") as handle:
            return handle.read()
    return backup_file.read_text(encoding="utf-8")
