from main import app, check_health
from api.settings import settings


def _capture_state(name: str):
    exists = hasattr(app.state, name)
    value = getattr(app.state, name, None)
    return exists, value


def _restore_state(name: str, exists: bool, value):
    if exists:
        setattr(app.state, name, value)
    elif hasattr(app.state, name):
        delattr(app.state, name)


def test_health_payload_uses_runtime_state_diagnostics() -> None:
    db_exists, db_value = _capture_state("database_type")
    probe_exists, probe_value = _capture_state("startup_probe")
    try:
        app.state.database_type = "neo4j"
        app.state.startup_probe = {"status": "success"}
        payload = check_health()
    finally:
        _restore_state("database_type", db_exists, db_value)
        _restore_state("startup_probe", probe_exists, probe_value)

    assert payload["status"] == "OK"
    assert payload["database_type"] == "neo4j"
    assert payload["provider_profile"] == "neo4j"
    assert payload["startup_probe_status"] == "success"


def test_health_payload_falls_back_when_state_is_missing() -> None:
    db_exists, db_value = _capture_state("database_type")
    probe_exists, probe_value = _capture_state("startup_probe")
    try:
        if hasattr(app.state, "database_type"):
            delattr(app.state, "database_type")
        if hasattr(app.state, "startup_probe"):
            delattr(app.state, "startup_probe")
        payload = check_health()
    finally:
        _restore_state("database_type", db_exists, db_value)
        _restore_state("startup_probe", probe_exists, probe_value)

    assert payload["status"] == "OK"
    assert payload["database_type"] == settings.normalized_db_type()
    assert payload["startup_probe_status"] == "unknown"
