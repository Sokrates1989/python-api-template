"""Tests the SQL-only guard on legacy compatibility sync routes."""

from unittest import mock

import pytest
from fastapi import HTTPException

from api.routes.sql import sync as sync_route


def test_ensure_sql_sync_supported_rejects_non_sql_backends() -> None:
    """Reject the legacy SQL sync route for non-SQL providers."""

    with mock.patch.object(
        type(sync_route.settings),
        "is_sql_database",
        return_value=False,
    ):
        with pytest.raises(HTTPException) as exc_info:
            sync_route.ensure_sql_sync_supported()

    assert exc_info.value.status_code == 400
    assert "only supported for SQL" in str(exc_info.value.detail)


def test_ensure_sql_sync_supported_allows_sql_backends() -> None:
    """Allow the legacy sync route when the active provider is SQL."""

    with mock.patch.object(
        type(sync_route.settings),
        "is_sql_database",
        return_value=True,
    ):
        sync_route.ensure_sql_sync_supported()
