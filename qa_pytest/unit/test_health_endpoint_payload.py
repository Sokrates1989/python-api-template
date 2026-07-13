"""Unit coverage for runtime-derived shared health diagnostics."""

from typing import Any

from api.settings import settings
from main import app, check_health


def _capture_state(name: str) -> tuple[bool, Any]:
    """Capture whether one FastAPI state field exists and its value.

    Args:
        name (str): Application-state attribute name.

    Returns:
        tuple[bool, Any]: Existence flag and current value.
    """
    exists = hasattr(app.state, name)
    value = getattr(app.state, name, None)
    return exists, value


def _restore_state(name: str, exists: bool, value: Any) -> None:
    """Restore one previously captured FastAPI state field.

    Args:
        name (str): Application-state attribute name.
        exists (bool): Whether the attribute previously existed.
        value (Any): Previous attribute value.

    Returns:
        None.

    Side Effects:
        Restores or removes one shared application-state attribute.
    """
    if exists:
        setattr(app.state, name, value)
    elif hasattr(app.state, name):
        delattr(app.state, name)


class _BackgroundService:
    """Expose deterministic privacy-safe background health metadata."""

    @property
    def name(self) -> str:
        """Return the fake service name.

        Returns:
            str: Stable fake service key.
        """
        return "dispatch"

    def snapshot(self) -> dict[str, object]:
        """Return one count-only fake service snapshot.

        Returns:
            dict[str, object]: Enabled/running aggregate metadata.
        """
        return {"enabled": True, "status": "running", "polls": 2}


def test_health_payload_uses_runtime_state_diagnostics() -> None:
    """Ensure health reflects provider and safe background runtime state.

    Returns:
        None.
    """
    db_exists, db_value = _capture_state("database_type")
    probe_exists, probe_value = _capture_state("startup_probe")
    services_exists, services_value = _capture_state("background_services")
    try:
        app.state.database_type = "neo4j"
        app.state.startup_probe = {"status": "success"}
        app.state.background_services = [_BackgroundService()]
        payload = check_health()
    finally:
        _restore_state("database_type", db_exists, db_value)
        _restore_state("startup_probe", probe_exists, probe_value)
        _restore_state("background_services", services_exists, services_value)

    assert payload["status"] == "OK"
    assert payload["database_type"] == "neo4j"
    assert payload["provider_profile"] == "neo4j"
    assert payload["startup_probe_status"] == "success"
    assert payload["background_services"] == {
        "dispatch": {"enabled": True, "status": "running", "polls": 2}
    }


def test_health_payload_falls_back_when_state_is_missing() -> None:
    """Ensure missing runtime fields produce conservative defaults.

    Returns:
        None.
    """
    db_exists, db_value = _capture_state("database_type")
    probe_exists, probe_value = _capture_state("startup_probe")
    services_exists, services_value = _capture_state("background_services")
    try:
        if hasattr(app.state, "database_type"):
            delattr(app.state, "database_type")
        if hasattr(app.state, "startup_probe"):
            delattr(app.state, "startup_probe")
        if hasattr(app.state, "background_services"):
            delattr(app.state, "background_services")
        payload = check_health()
    finally:
        _restore_state("database_type", db_exists, db_value)
        _restore_state("startup_probe", probe_exists, probe_value)
        _restore_state("background_services", services_exists, services_value)

    assert payload["status"] == "OK"
    assert payload["database_type"] == settings.normalized_db_type()
    assert payload["startup_probe_status"] == "unknown"
    assert payload["background_services"] == {}
