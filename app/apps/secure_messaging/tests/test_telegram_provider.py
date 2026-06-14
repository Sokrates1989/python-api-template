"""
Regression tests for the secure messaging Telegram provider.

The tests keep Telegram network behavior mocked so provider errors can be
verified without sending real notifications.
"""
from __future__ import annotations

import httpx
import pytest

from apps.secure_messaging.services import telegram_provider
from apps.secure_messaging.services.providers import ProviderDispatchError


class FakeTelegramClient:
    """
    Minimal async HTTP client used to mock Telegram responses.

    Attributes:
        timeout (float | None): Timeout value passed by the provider.

    Methods:
        post: Return a prepared HTTP response for Telegram sendMessage.
    """

    last_payload: dict[str, object] | None = None

    def __init__(self, timeout: float | None = None) -> None:
        """
        Store the requested timeout for parity with ``httpx.AsyncClient``.

        Args:
            timeout (float | None): Timeout passed by the production provider.

        Returns:
            None: Instance state is initialized in place.
        """
        self.timeout = timeout

    async def __aenter__(self) -> "FakeTelegramClient":
        """
        Enter the async context manager.

        Returns:
            FakeTelegramClient: This fake client instance.
        """
        return self

    async def __aexit__(self, *args: object) -> None:
        """
        Exit the async context manager.

        Args:
            *args (object): Exception details provided by the runtime.

        Returns:
            None: No cleanup is required.
        """
        return None

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        """
        Return a Telegram-style bad request response.

        Args:
            url (str): Request URL built by the provider.
            json (dict[str, object]): JSON payload sent by the provider.

        Returns:
            httpx.Response: Prepared 400 response containing Telegram details.
        """
        FakeTelegramClient.last_payload = json
        request = httpx.Request("POST", url, json=json)
        return httpx.Response(
            400,
            json={
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: chat not found",
            },
            request=request,
        )


@pytest.mark.asyncio
async def test_telegram_http_error_includes_description(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Verify Telegram HTTP failures preserve Telegram's diagnostic description.

    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture used to isolate
            environment variables and replace the HTTP client.

    Returns:
        None: Assertions validate the raised provider error.

    Raises:
        AssertionError: If the provider hides the Telegram description or sends
            an unnecessary null ``parse_mode`` field.
    """
    monkeypatch.setenv(
        "SECURE_MESSAGING_TELEGRAM_SENDERS_JSON",
        '{"backup":{"info":"-1001234567890"}}',
    )
    monkeypatch.setenv(
        "SECURE_MESSAGING_TELEGRAM_SENDER_TOKENS_JSON",
        '{"backup":"123456:test-token"}',
    )
    monkeypatch.setattr(telegram_provider.httpx, "AsyncClient", FakeTelegramClient)

    with pytest.raises(ProviderDispatchError) as exc_info:
        await telegram_provider.send_telegram_notification(
            level="info",
            title="Test",
            app="pytest",
            message="Hello",
            tags=[],
            sender_name="backup",
        )

    assert "Bad Request: chat not found" in str(exc_info.value)
    assert FakeTelegramClient.last_payload is not None
    assert "parse_mode" not in FakeTelegramClient.last_payload
