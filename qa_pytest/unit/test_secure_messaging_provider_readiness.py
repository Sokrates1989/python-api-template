"""
Unit tests for secure_messaging provider readiness checks.

Covers:
- is_telegram_configured: token present → ready (no pre-configured targets needed).
- is_telegram_configured: no token → not ready.
- is_telegram_configured: no senders → not ready.
- is_telegram_configured: configuration error → not ready (no exception raised).
- is_email_configured: host + from present → ready (no pre-configured recipients needed).
- is_email_configured: missing host → not ready.
- is_email_configured: missing from → not ready.
- is_email_configured: no senders → not ready.
- is_email_configured: configuration error → not ready (no exception raised).
"""
from __future__ import annotations

from unittest.mock import patch

from apps.secure_messaging.services.telegram_provider import is_telegram_configured
from apps.secure_messaging.services.email_provider import is_email_configured


# ---------------------------------------------------------------------------
# Telegram readiness
# ---------------------------------------------------------------------------

def test_telegram_ready_when_token_present_no_targets() -> None:
    """
    A sender with a valid token but no pre-configured target IDs must be
    considered ready because callers can supply chat IDs directly via `to`.
    """
    senders = {
        "backup": {
            "token": "1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ",
            # intentionally no chat IDs configured
        }
    }
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        return_value=senders,
    ):
        assert is_telegram_configured() is True


def test_telegram_ready_when_token_and_targets_present() -> None:
    """A sender with token and pre-configured targets is also ready."""
    senders = {
        "backup": {
            "token": "1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ",
            "info": "-1001234567890",
            "error": "-1009876543210",
        }
    }
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        return_value=senders,
    ):
        assert is_telegram_configured() is True


def test_telegram_not_ready_when_no_token() -> None:
    """A sender without a bot token is not ready."""
    senders = {"backup": {"info": "-1001234567890"}}
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        return_value=senders,
    ):
        assert is_telegram_configured() is False


def test_telegram_not_ready_when_no_senders() -> None:
    """An empty senders map means Telegram is not configured."""
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        return_value={},
    ):
        assert is_telegram_configured() is False


def test_telegram_not_ready_on_config_error() -> None:
    """A ValueError from get_telegram_senders must return False, not raise."""
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        side_effect=ValueError("Bad config"),
    ):
        assert is_telegram_configured() is False


def test_telegram_ready_when_any_sender_has_token() -> None:
    """At least one sender having a valid token is sufficient."""
    senders = {
        "broken": {},
        "working": {"token": "abc:def"},
    }
    with patch(
        "apps.secure_messaging.services.telegram_provider.SecureMessagingSettings.get_telegram_senders",
        return_value=senders,
    ):
        assert is_telegram_configured() is True


# ---------------------------------------------------------------------------
# Email readiness
# ---------------------------------------------------------------------------

def test_email_ready_when_host_and_from_present_no_recipients() -> None:
    """
    A sender with SMTP host and from-address but no pre-configured recipient
    keys must be considered ready because callers can supply addresses via `to`.
    """
    senders = {
        "default": {
            "host": "smtp.example.com",
            "from": "backup@example.com",
            # intentionally no receiver keys configured
        }
    }
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value=senders,
    ):
        assert is_email_configured() is True


def test_email_ready_when_host_from_and_recipients_present() -> None:
    """A sender with SMTP settings and pre-configured recipients is also ready."""
    senders = {
        "default": {
            "host": "smtp.example.com",
            "from": "backup@example.com",
            "info": "ops@example.com",
        }
    }
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value=senders,
    ):
        assert is_email_configured() is True


def test_email_not_ready_when_host_missing() -> None:
    """Missing SMTP host means the sender is not ready."""
    senders = {"default": {"from": "backup@example.com"}}
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value=senders,
    ):
        assert is_email_configured() is False


def test_email_not_ready_when_from_missing() -> None:
    """Missing from address means the sender is not ready."""
    senders = {"default": {"host": "smtp.example.com"}}
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value=senders,
    ):
        assert is_email_configured() is False


def test_email_not_ready_when_no_senders() -> None:
    """An empty senders map means email is not configured."""
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value={},
    ):
        assert is_email_configured() is False


def test_email_not_ready_on_config_error() -> None:
    """A ValueError from get_email_senders must return False, not raise."""
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        side_effect=ValueError("Bad config"),
    ):
        assert is_email_configured() is False


def test_email_ready_when_any_sender_is_complete() -> None:
    """At least one fully configured sender is sufficient for readiness."""
    senders = {
        "broken": {"host": ""},
        "working": {"host": "smtp.example.com", "from": "backup@example.com"},
    }
    with patch(
        "apps.secure_messaging.services.email_provider.SecureMessagingSettings.get_email_senders",
        return_value=senders,
    ):
        assert is_email_configured() is True
