"""
Unit tests for SecureMessagingSettings.get_client_tokens.

Covers:
- Neither JSON env var nor file env var set → empty dict (legacy fallback).
- SECURE_MESSAGING_CLIENT_TOKENS_JSON contains valid JSON → parsed map returned.
- SECURE_MESSAGING_CLIENT_TOKENS_JSON contains invalid JSON → ValueError raised.
- SECURE_MESSAGING_CLIENT_TOKENS_JSON is a non-dict JSON value → ValueError raised.
- SECURE_MESSAGING_CLIENT_TOKENS_FILE points to a file with valid JSON → parsed.
- SECURE_MESSAGING_CLIENT_TOKENS_FILE points to a missing file → ValueError raised.
- Values from both env vars are cast to str (defensive coercion).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.secure_messaging.config.runtime import SecureMessagingSettings


# ---------------------------------------------------------------------------
# Not configured → empty dict
# ---------------------------------------------------------------------------

def test_get_client_tokens_not_configured_returns_empty() -> None:
    """When neither variable is set, an empty dict is returned."""
    env: dict[str, str] = {}
    with patch.dict(os.environ, env, clear=False), patch.dict(
        os.environ,
        {},
        clear=False,
    ):
        # Ensure neither variable is present.
        env_copy = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "SECURE_MESSAGING_CLIENT_TOKENS_JSON",
                "SECURE_MESSAGING_CLIENT_TOKENS_FILE",
            }
        }
        with patch.dict(os.environ, env_copy, clear=True):
            result = SecureMessagingSettings.get_client_tokens()

    assert result == {}


# ---------------------------------------------------------------------------
# Inline JSON via env var
# ---------------------------------------------------------------------------

def test_get_client_tokens_from_json_env_var() -> None:
    """Valid JSON in SECURE_MESSAGING_CLIENT_TOKENS_JSON returns a parsed dict."""
    tokens = {"file-backup": "token-abc", "wiki-backup": "token-xyz"}
    env = {
        "SECURE_MESSAGING_CLIENT_TOKENS_JSON": json.dumps(tokens),
        "SECURE_MESSAGING_CLIENT_TOKENS_FILE": "",
    }
    with patch.dict(os.environ, env, clear=False):
        result = SecureMessagingSettings.get_client_tokens()

    assert result == tokens


def test_get_client_tokens_invalid_json_raises() -> None:
    """Malformed JSON raises ValueError."""
    env = {
        "SECURE_MESSAGING_CLIENT_TOKENS_JSON": "not-json{",
        "SECURE_MESSAGING_CLIENT_TOKENS_FILE": "",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError, match="Invalid JSON"):
            SecureMessagingSettings.get_client_tokens()


def test_get_client_tokens_non_dict_json_raises() -> None:
    """JSON value that is not an object raises ValueError."""
    env = {
        "SECURE_MESSAGING_CLIENT_TOKENS_JSON": '["list", "not", "object"]',
        "SECURE_MESSAGING_CLIENT_TOKENS_FILE": "",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError, match="JSON object"):
            SecureMessagingSettings.get_client_tokens()


# ---------------------------------------------------------------------------
# File-based token registry
# ---------------------------------------------------------------------------

def test_get_client_tokens_from_file() -> None:
    """Valid JSON file pointed to by SECURE_MESSAGING_CLIENT_TOKENS_FILE is parsed."""
    tokens = {"backup-client": "secret-token-999"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(tokens, f)
        tmp_path = f.name

    try:
        env = {
            "SECURE_MESSAGING_CLIENT_TOKENS_JSON": "",
            "SECURE_MESSAGING_CLIENT_TOKENS_FILE": tmp_path,
        }
        with patch.dict(os.environ, env, clear=False):
            result = SecureMessagingSettings.get_client_tokens()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    assert result == tokens


def test_get_client_tokens_missing_file_raises() -> None:
    """A declared but missing file path raises ValueError."""
    env = {
        "SECURE_MESSAGING_CLIENT_TOKENS_JSON": "",
        "SECURE_MESSAGING_CLIENT_TOKENS_FILE": "/nonexistent/path/tokens.json",
    }
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValueError, match="not found"):
            SecureMessagingSettings.get_client_tokens()


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def test_get_client_tokens_values_cast_to_str() -> None:
    """Numeric JSON values are cast to str for defensive consistency."""
    env = {
        "SECURE_MESSAGING_CLIENT_TOKENS_JSON": '{"int-key": 12345}',
        "SECURE_MESSAGING_CLIENT_TOKENS_FILE": "",
    }
    with patch.dict(os.environ, env, clear=False):
        result = SecureMessagingSettings.get_client_tokens()

    assert result == {"int-key": "12345"}
    assert isinstance(result["int-key"], str)
