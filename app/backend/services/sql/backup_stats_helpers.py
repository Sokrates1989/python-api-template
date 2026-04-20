"""Database statistics helpers for SQL backup operations."""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict

import psycopg2
from api.settings import settings


def get_database_stats() -> Dict:
    """Collect high-level statistics for the configured SQL database."""
    db_type = settings.DB_TYPE.lower()

    if db_type in ["postgresql", "postgres"]:
        return get_postgresql_stats()
    if db_type == "mysql":
        return get_mysql_stats()
    if db_type == "sqlite":
        return get_sqlite_stats()
    raise ValueError(f"Database stats not supported for database type: {db_type}")


def get_postgresql_stats() -> Dict:
    """Return per-table and database size stats for PostgreSQL."""
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.get_db_password(),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    relname AS table_name,
                    COALESCE(n_live_tup, 0)::bigint AS row_estimate,
                    pg_total_relation_size(relid) AS total_bytes
                FROM pg_stat_user_tables
                ORDER BY relname;
                """
            )
            table_rows = cursor.fetchall()

            tables = []
            total_rows = 0
            for table_name, row_estimate, total_bytes in table_rows:
                row_count = int(row_estimate)
                tables.append(
                    {
                        "name": table_name,
                        "row_count": row_count,
                        "size_mb": round(total_bytes / (1024 * 1024), 2),
                    }
                )
                total_rows += row_count

            cursor.execute("SELECT pg_database_size(%s)", (settings.DB_NAME,))
            database_size_bytes = cursor.fetchone()[0]

        return {
            "table_count": len(tables),
            "total_rows": total_rows,
            "database_size_mb": round(database_size_bytes / (1024 * 1024), 2),
            "tables": tables,
        }
    finally:
        conn.close()


def get_mysql_stats() -> Dict:
    """Return per-table and aggregate size stats for MySQL/MariaDB."""
    mysql_cmd = next((candidate for candidate in ["mysql", "mariadb"] if shutil.which(candidate)), None)
    if not mysql_cmd:
        raise Exception("MySQL client (mysql or mariadb) not found on system")

    escaped_db = settings.DB_NAME.replace("'", "''")
    query = (
        "SELECT table_name, IFNULL(table_rows, 0) AS rows, "
        "IFNULL(data_length + index_length, 0) AS total_bytes "
        "FROM information_schema.tables "
        f"WHERE table_schema = '{escaped_db}';"
    )
    cmd = [
        mysql_cmd,
        "-h",
        settings.DB_HOST,
        "-P",
        str(settings.DB_PORT),
        "-u",
        settings.DB_USER,
        f"-p{settings.get_db_password()}",
        "--batch",
        "--raw",
        "--silent",
        "-N",
        "-e",
        query,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"MySQL stats query failed: {result.stderr.strip()}")

    tables = []
    total_rows = 0
    total_bytes = 0
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        name, row_count, size_bytes = _parse_mysql_stat_line(line)
        tables.append(
            {
                "name": name,
                "row_count": row_count,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
            }
        )
        total_rows += row_count
        total_bytes += size_bytes

    return {
        "table_count": len(tables),
        "total_rows": total_rows,
        "database_size_mb": round(total_bytes / (1024 * 1024), 2),
        "tables": tables,
    }


def get_sqlite_stats() -> Dict:
    """Return table counts and file size stats for SQLite."""
    db_path = Path(settings.DB_NAME)
    if not db_path.exists():
        raise Exception(f"SQLite database file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        table_names = [row[0] for row in cursor.fetchall()]

        tables = []
        total_rows = 0
        for table_name in table_names:
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            row_count = cursor.fetchone()[0]
            total_rows += row_count
            tables.append({"name": table_name, "row_count": row_count})
    finally:
        conn.close()

    size_bytes = db_path.stat().st_size if db_path.exists() else 0
    return {
        "table_count": len(tables),
        "total_rows": total_rows,
        "database_size_mb": round(size_bytes / (1024 * 1024), 2),
        "tables": tables,
    }


def _parse_mysql_stat_line(line: str) -> tuple[str, int, int]:
    """Parse one TSV line from the MySQL statistics query."""
    parts = line.split("\t")
    if len(parts) < 3:
        return line, 0, 0
    name, rows_str, bytes_str = parts[:3]
    try:
        row_count = int(float(rows_str))
    except ValueError:
        row_count = 0
    try:
        size_bytes = int(float(bytes_str))
    except ValueError:
        size_bytes = 0
    return name, row_count, size_bytes
