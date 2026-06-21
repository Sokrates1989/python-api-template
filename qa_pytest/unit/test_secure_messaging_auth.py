"""
Unit tests for the secure_messaging authentication service.

Covers:
- Missing / malformed Authorization header → 401.
- Per-client token registry: hit and miss.
- Legacy single-token fallback: hit and miss.
- Priority order: registry is checked before legacy token.
- Legacy mode emits a migration warning log.
- Configuration errors propagate as 503.
- No valid token → 403.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from apps.secure_messaging.services.auth import authenticate_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(auth_header: str | None) -> MagicMock:
    """
    Build a minimal mock of a FastAPI Request with the given Authorization header.

    Args:
        auth_header (str | None): Value for the Authorization header, or None
            to simulate a missing header.

    Returns:
        MagicMock: Mock request object with a headers dict-like attribute.
    """
    req = MagicMock()
    if auth_header is None:
        req.headers = {}
    else:
        req.headers = {"authorization": auth_header}
    return req


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------

def test_missing_auth_header_raises_401() -> None:
    """Absent Authorization header must return 401."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate_request(_request(None), app="test-app")
    assert exc_info.value.status_code == 401


def test_malformed_auth_header_raises_401() -> None:
    """Authorization header without 'Bearer' scheme must return 401."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate_request(_request("Basic dXNlcjpwYXNz"), app="test-app")
    assert exc_info.value.status_code == 401


def test_bearer_without_token_raises_401() -> None:
    """'Bearer' keyword alone (no token value) must return 401."""
    with pytest.raises(HTTPException) as exc_info:
        authenticate_request(_request("Bearer"), app="test-app")
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Per-client registry — successful auth
# ---------------------------------------------------------------------------

def test_client_registry_hit_returns_client_name() -> None:
    """A token matching a registry entry returns its client name."""
    registry = {"file-backup": "token-abc", "wiki-backup": "token-xyz"}

    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value=registry,
    ):
        result = authenticate_request(
            _request("Bearer token-abc"), app="file-backup"
        )

    assert result.app == "file-backup"
    assert result.client_name == "file-backup"


def test_client_registry_second_entry_matches() -> None:
    """Every entry in the registry is checked."""
    registry = {"client-a": "token-aaa", "client-b": "token-bbb"}

    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value=registry,
    ):
        result = authenticate_request(
            _request("Bearer token-bbb"), app="client-b"
        )

    assert result.client_name == "client-b"


# ---------------------------------------------------------------------------
# Per-client registry — failed auth falls through to legacy
# ---------------------------------------------------------------------------

def test_registry_miss_falls_through_to_legacy() -> None:
    """
    A token absent from the registry must be compared against the legacy token
    and succeed when it matches.
    """
    registry = {"other-client": "token-other"}

    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value=registry,
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="legacy-token",
    ):
        result = authenticate_request(
            _request("Bearer legacy-token"), app="old-client"
        )

    assert result.app == "old-client"
    assert result.client_name is None


def test_legacy_fallback_logs_migration_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Successful legacy-token auth must emit a warning log."""
    import logging

    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value={},
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="legacy-token",
    ):
        with caplog.at_level(logging.WARNING, logger="secure_messaging.auth"):
            authenticate_request(_request("Bearer legacy-token"), app="old-client")

    assert any("legacy" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# Registry empty → falls through to legacy
# ---------------------------------------------------------------------------

def test_empty_registry_falls_through_to_legacy() -> None:
    """An empty registry dict must trigger the legacy path."""
    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value={},
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="legacy-only",
    ):
        result = authenticate_request(_request("Bearer legacy-only"), app="x")

    assert result.client_name is None


# ---------------------------------------------------------------------------
# Wrong token → 403
# ---------------------------------------------------------------------------

def test_wrong_token_raises_403() -> None:
    """A token that matches neither the registry nor the legacy token must return 403."""
    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value={"client-a": "correct-token"},
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="legacy-correct",
    ):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_request(_request("Bearer wrong-token"), app="attacker")

    assert exc_info.value.status_code == 403


def test_wrong_legacy_token_raises_403() -> None:
    """Wrong token with no registry configured must return 403."""
    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value={},
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="the-real-token",
    ):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_request(_request("Bearer not-the-token"), app="attacker")

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Priority: registry is checked before legacy token
# ---------------------------------------------------------------------------

def test_registry_checked_before_legacy() -> None:
    """
    When both registry and legacy token are configured, the registry entry
    wins and client_name is set (not None).
    """
    registry = {"preferred": "shared-token"}

    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value=registry,
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        return_value="shared-token",
    ):
        result = authenticate_request(_request("Bearer shared-token"), app="preferred")

    assert result.client_name == "preferred"


# ---------------------------------------------------------------------------
# Configuration errors → 503
# ---------------------------------------------------------------------------

def test_registry_config_error_raises_503() -> None:
    """A malformed client-tokens file must surface as 503."""
    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        side_effect=ValueError("Bad JSON"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_request(_request("Bearer any"), app="any")

    assert exc_info.value.status_code == 503


def test_legacy_config_error_raises_503() -> None:
    """A missing legacy token file must surface as 503 (not 403)."""
    with patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_client_tokens",
        return_value={},
    ), patch(
        "apps.secure_messaging.services.auth.SecureMessagingSettings.get_auth_token",
        side_effect=ValueError("Token not configured"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            authenticate_request(_request("Bearer any"), app="any")

    assert exc_info.value.status_code == 503
