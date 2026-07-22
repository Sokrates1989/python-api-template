"""Tests identifier and credential safety in SQL backup maintenance queries."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest import mock

from backend.services.sql import backup_restore_helpers, backup_stats_helpers


def test_mysql_drop_uses_selected_database_without_interpolation() -> None:
    """Use ``DATABASE()`` instead of composing the configured schema value."""

    completed = SimpleNamespace(returncode=0, stdout="", stderr="")
    with mock.patch.object(
        backup_restore_helpers.settings,
        "DB_NAME",
        "unsafe' schema",
    ), mock.patch.object(
        type(backup_restore_helpers.settings),
        "get_db_password",
        return_value="private-value",
    ), mock.patch.object(
        backup_restore_helpers,
        "_build_mysql_drop_command",
        return_value=["mysql"],
    ), mock.patch.object(
        backup_restore_helpers.subprocess,
        "run",
        return_value=completed,
    ) as run:
        backup_restore_helpers.drop_mysql_tables()

    statement = run.call_args.kwargs["input"]
    assert "table_schema = DATABASE()" in statement
    assert "unsafe' schema" not in statement
    assert run.call_args.kwargs["env"]["MYSQL_PWD"] == "private-value"


def test_mysql_stats_keeps_password_out_of_arguments() -> None:
    """Pass the MySQL password through the process environment only."""

    completed = SimpleNamespace(returncode=0, stdout="", stderr="")
    with mock.patch.object(
        backup_stats_helpers.shutil,
        "which",
        return_value="mysql",
    ), mock.patch.object(
        type(backup_stats_helpers.settings),
        "get_db_password",
        return_value="private-value",
    ), mock.patch.object(
        backup_stats_helpers.subprocess,
        "run",
        return_value=completed,
    ) as run:
        result = backup_stats_helpers.get_mysql_stats()

    command = run.call_args.args[0]
    assert all("private-value" not in argument for argument in command)
    assert command[command.index("-D") + 1] == backup_stats_helpers.settings.DB_NAME
    assert "table_schema = DATABASE();" in command[-1]
    assert run.call_args.kwargs["env"]["MYSQL_PWD"] == "private-value"
    assert result["table_count"] == 0


def test_sqlite_stats_quotes_database_owned_identifiers(tmp_path) -> None:
    """Count a table whose identifier contains an embedded quote safely."""

    database = tmp_path / "quoted.sqlite"
    connection = sqlite3.connect(database)
    connection.execute('CREATE TABLE "quoted""table" (value INTEGER)')
    connection.execute('INSERT INTO "quoted""table" VALUES (1)')
    connection.commit()
    connection.close()

    with mock.patch.object(backup_stats_helpers.settings, "DB_NAME", str(database)):
        result = backup_stats_helpers.get_sqlite_stats()

    assert result["table_count"] == 1
    assert result["total_rows"] == 1
    assert result["tables"][0]["name"] == 'quoted"table'
