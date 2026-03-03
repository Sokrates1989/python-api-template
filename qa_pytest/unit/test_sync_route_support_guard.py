from unittest import mock

import pytest
from fastapi import HTTPException

from api.routes.sql import sync as sync_route


def test_ensure_sync_supported_rejects_non_sql_backends() -> None:
    with mock.patch.object(type(sync_route.settings), "is_sql_database", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            sync_route.ensure_sync_supported()

    assert exc_info.value.status_code == 400
    assert "not supported" in str(exc_info.value.detail)


def test_ensure_sync_supported_allows_sql_backends() -> None:
    with mock.patch.object(type(sync_route.settings), "is_sql_database", return_value=True):
        sync_route.ensure_sync_supported()
