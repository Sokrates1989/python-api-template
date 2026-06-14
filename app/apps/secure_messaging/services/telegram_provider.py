"""
Telegram Bot API provider for secure messaging.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from apps.secure_messaging.config.runtime import SecureMessagingSettings
from apps.secure_messaging.services.providers import ProviderDispatchError, ProviderDispatchResult

logger = logging.getLogger("secure_messaging.telegram")

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
TELEGRAM_NON_TARGET_KEYS = {"token"}


def _has_telegram_target(sender_config: dict[str, str]) -> bool:
    """
    Return whether a Telegram sender has at least one recipient target.

    Args:
        sender_config (dict[str, str]): Merged sender configuration containing
            a bot token and level/default chat targets.

    Returns:
        bool: True when the sender has any non-token target value.

    Side Effects:
        None.
    """
    return any(
        bool(value)
        for key, value in sender_config.items()
        if key not in TELEGRAM_NON_TARGET_KEYS
    )


def _format_telegram_message(
    level: str,
    title: str,
    app: str,
    message: str,
    tags: list[str],
) -> str:
    """
    Format notification for Telegram delivery.

    Args:
        level (str): Notification level.
        title (str): Notification title.
        app (str): App identifier.
        message (str): Redacted notification message.
        tags (list[str]): Categorization tags.

    Returns:
        str: Formatted Telegram message.
    """
    level_emoji = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🚨",
    }.get(level, "📌")

    lines = [
        f"{level_emoji} [{level.upper()}] {title}",
        "",
        f"App: {app}",
        f"Level: {level}",
    ]

    if tags:
        lines.append(f"Tags: {', '.join(tags)}")

    lines.extend(["", message])
    return "\n".join(lines)


async def send_telegram_notification(
    level: str,
    title: str,
    app: str,
    message: str,
    tags: list[str],
    sender_name: str | None = None,
    to: str | None = None,
) -> ProviderDispatchResult:
    """
    Send notification via Telegram Bot API.

    Args:
        level (str): Notification level.
        title (str): Notification title.
        app (str): App identifier.
        message (str): Redacted notification message.
        tags (list[str]): Categorization tags.
        sender_name (str | None): Specific sender to use. Uses first available if None.
        to (str | None): Optional override chat ID. Uses sender default if None.

    Returns:
        ProviderDispatchResult: Dispatch result status.

    Raises:
        ProviderDispatchError: When Telegram API call fails.

    Side Effects:
        Makes HTTP request to Telegram API.
    """
    # Get sender configuration
    senders = SecureMessagingSettings.get_telegram_senders()
    if not senders:
        raise ProviderDispatchError("No Telegram senders configured", "telegram")

    # Select sender
    if sender_name:
        sender_config = senders.get(sender_name)
        if not sender_config:
            available = list(senders.keys())
            raise ProviderDispatchError(
                f"Unknown sender '{sender_name}'. Available: {available}",
                "telegram",
            )
    else:
        # Use first available sender as default
        sender_name, sender_config = next(iter(senders.items()))

    bot_token = sender_config.get("token", "")

    # Determine chat_id: custom override > level-based default > first available target
    if to:
        chat_id = to
    elif level in sender_config:
        chat_id = sender_config[level]
    elif "default" in sender_config:
        chat_id = sender_config["default"]
    else:
        # Use first defined target as fallback
        targets = {k: v for k, v in sender_config.items() if k != "token"}
        chat_id = next(iter(targets.values())) if targets else ""

    if not bot_token or not chat_id:
        raise ProviderDispatchError(
            "Telegram not configured: missing bot token or chat ID",
            "telegram",
        )

    formatted_message = _format_telegram_message(level, title, app, message, tags)

    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": formatted_message,
        "parse_mode": None,  # Plain text for safety with redacted content
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        result = response.json()
        if not result.get("ok"):
            error_desc = result.get("description", "Unknown Telegram error")
            raise ProviderDispatchError(
                f"Telegram API error: {error_desc}",
                "telegram",
            )

        logger.info(
            "telegram.notification.sent",
            extra={"app": app, "level": level, "chat_id": chat_id},
        )
        return ProviderDispatchResult(status="sent", sender=sender_name)

    except httpx.HTTPStatusError as exc:
        logger.error(
            "telegram.notification.http_error",
            extra={
                "app": app,
                "level": level,
                "status_code": exc.response.status_code,
            },
        )
        raise ProviderDispatchError(
            f"Telegram HTTP error: {exc.response.status_code}",
            "telegram",
        ) from exc

    except httpx.RequestError as exc:
        logger.error(
            "telegram.notification.request_error",
            extra={"app": app, "level": level, "error": str(exc)},
        )
        raise ProviderDispatchError(
            "Telegram request failed: network error",
            "telegram",
        ) from exc

    except Exception as exc:
        logger.error(
            "telegram.notification.unexpected_error",
            extra={"app": app, "level": level, "error": str(exc)},
        )
        raise ProviderDispatchError(
            "Telegram dispatch failed: unexpected error",
            "telegram",
        ) from exc


def is_telegram_configured() -> bool:
    """
    Check if Telegram provider is properly configured.

    Returns:
        bool: True if at least one sender has a token and recipient target.
    """
    try:
        senders = SecureMessagingSettings.get_telegram_senders()
        if not senders:
            return False

        # Match the dispatch path, which accepts level-based targets such as
        # info/warning/error, a default target, or any other named target.
        for sender_config in senders.values():
            if sender_config.get("token") and _has_telegram_target(sender_config):
                return True
        return False
    except ValueError:
        return False
