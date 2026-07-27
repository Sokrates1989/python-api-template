"""Lifecycle state evidence used by the Felix production health gate."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.config import lifecycle
from backend.database import migrations


def test_sql_lifecycle_records_migration_and_startup_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose successful SQL migration/startup state only after all gates pass."""
    events: list[str] = []
    selected_app = SimpleNamespace(
        requires_database=True,
        requires_redis=False,
        background_service_factories=(),
    )
    runtime_settings = SimpleNamespace(
        APP_PROFILE="felix",
        DB_MODE="external",
        normalized_db_type=lambda: "postgresql",
        is_sql_database=lambda: True,
    )
    handler = SimpleNamespace(db_type="postgresql")

    async def _initialize_database() -> dict[str, str]:
        events.append("database")
        return {"status": "success"}

    async def _startup_probe(_handler: object) -> dict[str, str]:
        events.append("probe")
        return {"status": "success"}

    async def _close_database() -> None:
        events.append("close")

    def _run_migrations(*, fail_on_error: bool) -> bool:
        assert fail_on_error is True
        events.append("migrations")
        return True

    monkeypatch.setattr(lifecycle, "settings", runtime_settings)
    monkeypatch.setattr(
        lifecycle, "get_backend_app_definition", lambda _profile: selected_app
    )
    monkeypatch.setattr(lifecycle, "initialize_database", _initialize_database)
    monkeypatch.setattr(lifecycle, "get_database_handler", lambda: handler)
    monkeypatch.setattr(lifecycle, "run_provider_startup_probe", _startup_probe)
    monkeypatch.setattr(lifecycle, "close_database", _close_database)
    monkeypatch.setattr(migrations, "run_migrations", _run_migrations)

    app = SimpleNamespace(state=SimpleNamespace())

    async def _exercise_lifespan() -> None:
        async with lifecycle.create_lifespan_handler()(app):
            assert app.state.startup_probe == {"status": "success"}
            assert app.state.database_type == "postgresql"
            assert app.state.migration_status == "success"
            assert app.state.startup_complete is True

    asyncio.run(_exercise_lifespan())

    assert events == ["database", "probe", "migrations", "close"]


def test_sql_lifecycle_rejects_unsuccessful_migration_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep startup incomplete when the migration runner returns failure."""
    selected_app = SimpleNamespace(
        requires_database=True,
        requires_redis=False,
        background_service_factories=(),
    )
    runtime_settings = SimpleNamespace(
        APP_PROFILE="felix",
        DB_MODE="external",
        normalized_db_type=lambda: "postgresql",
        is_sql_database=lambda: True,
    )

    async def _initialize_database() -> dict[str, str]:
        return {"status": "success"}

    async def _startup_probe(_handler: object) -> dict[str, str]:
        return {"status": "success"}

    monkeypatch.setattr(lifecycle, "settings", runtime_settings)
    monkeypatch.setattr(
        lifecycle, "get_backend_app_definition", lambda _profile: selected_app
    )
    monkeypatch.setattr(lifecycle, "initialize_database", _initialize_database)
    monkeypatch.setattr(
        lifecycle,
        "get_database_handler",
        lambda: SimpleNamespace(db_type="postgresql"),
    )
    monkeypatch.setattr(lifecycle, "run_provider_startup_probe", _startup_probe)
    monkeypatch.setattr(
        migrations,
        "run_migrations",
        lambda *, fail_on_error: False,
    )

    app = SimpleNamespace(state=SimpleNamespace())

    async def _exercise_lifespan() -> None:
        with pytest.raises(
            RuntimeError, match="SQL migrations did not complete successfully"
        ):
            async with lifecycle.create_lifespan_handler()(app):
                raise AssertionError("failed migrations must not yield startup")

    asyncio.run(_exercise_lifespan())

    assert app.state.migration_status == "pending"
    assert app.state.startup_complete is False
