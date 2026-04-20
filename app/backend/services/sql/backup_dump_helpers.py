"""Backup creation helpers for SQL database backends."""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from api.settings import settings

from .backup_state import BackupStateTracker


def create_backup_to_temp(state: BackupStateTracker, compress: bool = True) -> tuple[str, Path]:
    """Create a temporary backup file for the configured SQL backend."""
    lock_operation = state.check_operation_lock()
    if lock_operation:
        raise Exception(f"Cannot create backup: {lock_operation} operation is in progress")

    if not state.acquire_lock("backup"):
        raise Exception("Failed to acquire lock for backup operation")

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_type = settings.DB_TYPE.lower()

        if db_type in ["postgresql", "postgres"]:
            return backup_postgresql(timestamp, compress)
        if db_type == "mysql":
            return backup_mysql(timestamp, compress)
        if db_type == "sqlite":
            return backup_sqlite(timestamp, compress)
        raise ValueError(f"Backup not supported for database type: {db_type}")
    finally:
        state.release_lock()


def backup_postgresql(timestamp: str, compress: bool) -> tuple[str, Path]:
    """Create a PostgreSQL backup via pg_dump."""
    filename = _build_backup_filename("postgresql", timestamp, ".sql", compress)
    filepath = _create_temp_file(".sql.gz" if compress else ".sql")
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.get_db_password()

    cmd = [
        "pg_dump",
        "-h",
        settings.DB_HOST,
        "-p",
        str(settings.DB_PORT),
        "-U",
        settings.DB_USER,
        "-d",
        settings.DB_NAME,
        "--no-owner",
        "--no-acl",
        "-F",
        "p",
    ]

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, check=True, text=True)
        _write_text_output(filepath, result.stdout, compress)
        return filename, filepath
    except subprocess.CalledProcessError as exc:
        raise Exception(f"PostgreSQL backup failed: {exc.stderr}") from exc


def backup_mysql(timestamp: str, compress: bool) -> tuple[str, Path]:
    """Create a MySQL backup using mariadb-dump or mysqldump."""
    filename = _build_backup_filename("mysql", timestamp, ".sql", compress)
    filepath = _create_temp_file(".sql.gz" if compress else ".sql")
    dump_cmd = "mariadb-dump" if shutil.which("mariadb-dump") else "mysqldump"

    cmd = [
        dump_cmd,
        "-h",
        settings.DB_HOST,
        "-P",
        str(settings.DB_PORT),
        "-u",
        settings.DB_USER,
        f"-p{settings.get_db_password()}",
        settings.DB_NAME,
        "--single-transaction",
        "--skip-lock-tables",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        _write_text_output(filepath, result.stdout, compress)
        return filename, filepath
    except subprocess.CalledProcessError as exc:
        raise Exception(f"MySQL backup failed: {exc.stderr}") from exc


def backup_sqlite(timestamp: str, compress: bool) -> tuple[str, Path]:
    """Create a SQLite backup by copying the database file."""
    filename = _build_backup_filename("sqlite", timestamp, ".db", compress)
    filepath = _create_temp_file(".db.gz" if compress else ".db")
    db_file = Path(settings.DB_NAME)

    if not db_file.exists():
        raise Exception(f"SQLite database file not found: {db_file}")

    try:
        if compress:
            with open(db_file, "rb") as source, gzip.open(filepath, "wb") as target:
                shutil.copyfileobj(source, target)
        else:
            shutil.copy2(db_file, filepath)
        return filename, filepath
    except Exception as exc:
        raise Exception(f"SQLite backup failed: {exc}") from exc


def _build_backup_filename(db_label: str, timestamp: str, suffix: str, compress: bool) -> str:
    """Build a human-readable backup filename."""
    filename = f"backup_{db_label}_{timestamp}{suffix}"
    if compress:
        filename += ".gz"
    return filename


def _create_temp_file(suffix: str) -> Path:
    """Create and close a temporary file, returning its path."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    filepath = Path(temp_file.name)
    temp_file.close()
    return filepath


def _write_text_output(filepath: Path, content: str, compress: bool) -> None:
    """Persist textual dump output to a plain or gzipped file."""
    if compress:
        with gzip.open(filepath, "wt", encoding="utf-8") as handle:
            handle.write(content)
        return
    filepath.write_text(content, encoding="utf-8")
