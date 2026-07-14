"""Verify independent API and SQL logging-level configuration.

The cases keep ordinary production and application DEBUG logs focused while
allowing an operator to opt into SQLAlchemy statements for a bounded local
investigation.

Dependencies:
    - pytest monkeypatch fixtures for isolated environment controls.
    - API settings and centralized backend logging policy.

Usage:
    Run ``pytest qa_pytest/unit/test_logging_config.py`` in the selected backend
    dependency environment.
"""

from __future__ import annotations

import logging

from api.settings import Settings
from backend import logging_config


def test_sqlalchemy_logs_stay_quiet_during_general_debug(
    monkeypatch,
) -> None:
    """Ensure DEBUG does not implicitly expose every SQL statement.

    Args:
        monkeypatch: Pytest environment mutation fixture.

    Returns:
        None.

    Side Effects:
        Temporarily removes ``SQL_ECHO_ENABLED`` from the test environment.
    """
    monkeypatch.delenv("SQL_ECHO_ENABLED", raising=False)

    assert (
        logging_config._resolve_sqlalchemy_log_level(logging.DEBUG) == logging.WARNING
    )


def test_sqlalchemy_logs_require_debug_and_explicit_opt_in(monkeypatch) -> None:
    """Ensure SQL echo activates only under the two-part operator policy.

    Args:
        monkeypatch: Pytest environment mutation fixture.

    Returns:
        None.

    Side Effects:
        Temporarily enables ``SQL_ECHO_ENABLED`` in the test environment.
    """
    monkeypatch.setenv("SQL_ECHO_ENABLED", "true")

    assert logging_config._resolve_sqlalchemy_log_level(logging.DEBUG) == logging.INFO
    assert logging_config._resolve_sqlalchemy_log_level(logging.INFO) == logging.WARNING


def test_database_echo_requires_the_same_two_part_policy() -> None:
    """Ensure SQLAlchemy engine construction follows logger-level policy.

    Returns:
        None.

    Side Effects:
        None. Settings instances ignore repository environment files.
    """
    general_debug = Settings(
        _env_file=None,
        DEBUG=True,
        SQL_ECHO_ENABLED=False,
    )
    explicit_sql_debug = Settings(
        _env_file=None,
        LOG_LEVEL="DEBUG",
        SQL_ECHO_ENABLED=True,
    )
    production = Settings(
        _env_file=None,
        LOG_LEVEL="INFO",
        SQL_ECHO_ENABLED=True,
    )

    assert general_debug.is_sql_echo_enabled() is False
    assert explicit_sql_debug.is_sql_echo_enabled() is True
    assert production.is_sql_echo_enabled() is False
