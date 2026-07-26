"""Regression tests for Felix SQL child-state provisioning races.

Access-readiness and rewards rows reference the shared users table. These tests
verify that requests arriving before the application user row exists return a
stable not-found envelope without attempting a foreign-key child insert.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.felix.services.access_readiness_service import FelixAccessReadinessService
from apps.felix.services.rewards_service import FelixRewardsService


class _MissingUserResult:
    """Represent a SQL scalar lookup that found no application user row."""

    def scalar_one_or_none(self) -> None:
        """Return no scalar row for the provisioning guard.

        Args:
            None.

        Returns:
            None: The fake user lookup did not match a row.

        Side Effects:
            None.
        """
        return None


class SQLHandler:
    """Minimal name-compatible SQL handler used by Felix service dispatch."""

    def __init__(self, session: MagicMock) -> None:
        """Expose one reusable asynchronous session context factory.

        Args:
            session (MagicMock): Session double returned for each unit of work.

        Returns:
            None.

        Side Effects:
            Creates a mock ``AsyncSessionLocal`` factory.
        """
        self.AsyncSessionLocal = MagicMock(return_value=session)


def _missing_user_session() -> MagicMock:
    """Build a SQL session whose parent-user lookups always miss.

    Args:
        None.

    Returns:
        MagicMock: Async-context-compatible SQL session double.

    Side Effects:
        None.
    """
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=[_MissingUserResult(), _MissingUserResult()])
    session.commit = AsyncMock()
    return session


@pytest.mark.parametrize(
    ("service_class", "get_method", "update_method"),
    [
        (
            FelixAccessReadinessService,
            "get_access_readiness_state",
            "update_access_readiness_state",
        ),
        (FelixRewardsService, "get_rewards_state", "update_rewards_state"),
    ],
)
def test_sql_child_state_returns_stable_missing_user_result(
    service_class: type[Any],
    get_method: str,
    update_method: str,
) -> None:
    """Return not-found before readiness or rewards can violate their FK.

    Args:
        service_class (type[Any]): Felix state service under test.
        get_method (str): Public read method name for the service.
        update_method (str): Public patch method name for the service.

    Returns:
        None.

    Side Effects:
        Runs the asynchronous service methods against a fake SQL session.
    """
    session = _missing_user_session()
    service = object.__new__(service_class)
    service.handler = SQLHandler(session)
    expected = {"status": "error", "message": "User not found", "data": None}

    read_result = asyncio.run(getattr(service, get_method)("missing-user"))
    update_result = asyncio.run(getattr(service, update_method)("missing-user", {}))

    assert read_result == expected
    assert update_result == expected
    assert session.execute.await_count == 2
    assert all(
        "FROM users" in str(call.args[0]) and "FOR UPDATE" in str(call.args[0])
        for call in session.execute.await_args_list
    )
    session.commit.assert_not_awaited()
