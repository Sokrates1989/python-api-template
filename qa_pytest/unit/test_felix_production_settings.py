"""Production-only settings coverage for the fixed Felix runtime contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from api.settings import Settings


def _secret_file(tmp_path: Path, name: str, value: str = "test-secret") -> str:
    """Create one isolated mounted-secret stand-in.

    Args:
        tmp_path (Path): Pytest-owned temporary directory.
        name (str): Secret filename within the temporary directory.
        value (str): File content, defaulting to a non-production test value.

    Returns:
        str: Absolute path to the created secret stand-in.

    Side Effects:
        Writes one file below ``tmp_path``.
    """
    path = tmp_path / name
    path.write_text(value, encoding="utf-8")
    return str(path)


def _production_values(tmp_path: Path) -> dict[str, object]:
    """Build the complete Felix production settings fixture.

    Args:
        tmp_path (Path): Directory in which required secret stand-ins are
            created.

    Returns:
        dict[str, object]: Public settings and file paths satisfying the fixed
            candidate contract.

    Side Effects:
        Creates isolated database and Keycloak secret stand-in files.
    """
    return {
        "_env_file": None,
        "APP_ENVIRONMENT": "production",
        "BACKEND_APP_ID": "felix",
        "APP_PROFILE": "felix",
        "DB_TYPE": "postgresql",
        "DB_MODE": "external",
        "DB_PASSWORD": "",
        "DB_PASSWORD_FILE": _secret_file(tmp_path, "db_password"),
        "CORS_ORIGINS": "https://felix-app.fe-wi.com",
        "AUTH_PROVIDER": "keycloak",
        "KEYCLOAK_SERVER_URL": "https://keycloak.fe-wi.com",
        "KEYCLOAK_INTERNAL_URL": "",
        "KEYCLOAK_REALM": "felix-new",
        "KEYCLOAK_CLIENT_ID": "felix-new-frontend",
        "KEYCLOAK_CLIENT_SECRET": "",
        "KEYCLOAK_ISSUER_URL": "https://keycloak.fe-wi.com/realms/felix-new",
        "KEYCLOAK_JWKS_URL": (
            "https://keycloak.fe-wi.com/realms/felix-new/"
            "protocol/openid-connect/certs"
        ),
        "KEYCLOAK_ENFORCE_AUDIENCE": True,
        "KEYCLOAK_AUDIENCE": "felix-new-backend",
        "KEYCLOAK_ADMIN_CLIENT_ID": "felix-new-backend",
        "KEYCLOAK_ADMIN_CLIENT_SECRET_FILE": _secret_file(
            tmp_path, "keycloak_admin_client_secret"
        ),
        "ADMIN_API_KEY": "",
        "BACKUP_RESTORE_API_KEY": "",
        "BACKUP_DELETE_API_KEY": "",
        "AI_CHAT_API_KEY": "",
        "WEB_PUSH_VAPID_PRIVATE_KEY": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "DEBUG": False,
        "DEBUG_ENABLED": False,
        "SQL_ECHO_ENABLED": False,
        "ENABLE_HTTP_DEBUG_LOGGING": False,
        "LOG_REQUEST_HEADERS": False,
        "LOG_REQUEST_BODY": False,
        "LOG_RESPONSE_HEADERS": False,
        "LOG_RESPONSE_BODY": False,
        "AI_CHAT_DEBUG_ENABLED": False,
        "AI_CHAT_DEBUG_INCLUDE_PROMPTS": False,
        "LOG_LEVEL": "INFO",
    }


def test_complete_felix_production_settings_are_accepted(tmp_path: Path) -> None:
    """Accept the exact candidate identity with mounted secrets.

    Args:
        tmp_path (Path): Pytest-owned directory for secret stand-in files.

    Returns:
        None.
    """
    configured = Settings(**_production_values(tmp_path))

    assert configured.is_production_environment() is True
    assert configured.normalized_app_profile() == "felix"
    assert configured.get_auth_provider() == "keycloak"
    assert configured.get_keycloak_admin_client_secret() == "test-secret"


@pytest.mark.parametrize(
    ("field", "unsafe_value", "expected_message"),
    [
        ("APP_PROFILE", "demo_app", "must both be 'felix'"),
        ("AUTH_PROVIDER", "cognito", "must be 'keycloak'"),
        (
            "CORS_ORIGINS",
            "http://localhost:3000",
            "must contain only https://felix-app.fe-wi.com",
        ),
        ("DEBUG", True, "production debug flags must be disabled"),
        ("KEYCLOAK_ENFORCE_AUDIENCE", False, "must be enabled"),
        (
            "KEYCLOAK_CLIENT_ID",
            "legacy-frontend",
            "must be 'felix-new-frontend'",
        ),
        (
            "KEYCLOAK_AUDIENCE",
            "legacy-backend",
            "must be 'felix-new-backend'",
        ),
        (
            "KEYCLOAK_ADMIN_CLIENT_ID",
            "broad-admin",
            "must be 'felix-new-backend'",
        ),
        ("KEYCLOAK_CLIENT_SECRET", "direct-secret", "must be file-backed"),
        ("DB_PASSWORD", "direct-password", "must be file-backed"),
        ("DATABASE_URL", "postgresql://user:secret@db/felix", "must be file-backed"),
        ("AWS_REGION", "eu-central-1", "authentication settings must be absent"),
    ],
)
def test_felix_production_rejects_unsafe_runtime_values(
    tmp_path: Path,
    field: str,
    unsafe_value: object,
    expected_message: str,
) -> None:
    """Fail before startup for identity, provider, debug, or secret drift.

    Args:
        tmp_path (Path): Pytest-owned directory for secret stand-in files.
        field (str): Production setting to replace with an unsafe value.
        unsafe_value (object): Drift value expected to be rejected.
        expected_message (str): Validation-error fragment proving the gate.

    Returns:
        None.
    """
    values = _production_values(tmp_path)
    values[field] = unsafe_value

    with pytest.raises(ValidationError, match=expected_message):
        Settings(**values)


def test_production_requires_existing_nonempty_secret_files(tmp_path: Path) -> None:
    """Reject an absent Keycloak administration secret mount.

    Args:
        tmp_path (Path): Pytest-owned directory used to form a missing path.

    Returns:
        None.
    """
    values = _production_values(tmp_path)
    values["KEYCLOAK_ADMIN_CLIENT_SECRET_FILE"] = str(tmp_path / "missing")

    with pytest.raises(ValidationError, match="does not reference a readable file"):
        Settings(**values)


def test_development_defaults_remain_flexible() -> None:
    """Keep the legacy template defaults outside explicit production mode.

    Returns:
        None.
    """
    configured = Settings(
        _env_file=None,
        APP_ENVIRONMENT="development",
        APP_PROFILE="demo_app",
        BACKEND_APP_ID="demo_app",
        AUTH_PROVIDER="cognito",
        CORS_ORIGINS="http://localhost:3000",
        DEBUG=True,
    )

    assert configured.is_production_environment() is False
    assert configured.get_auth_provider() == "cognito"


def test_unknown_environment_name_is_rejected() -> None:
    """Reject environment typos that could otherwise bypass production gates.

    Returns:
        None.
    """
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENVIRONMENT="prod")
