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
MAX_LOGGED_TELEGRAM_BODY_LENGTH = 1000


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


def _resolve_recipients(sender_config: dict[str, str], to: str | None) -> list[str]:
    """
    Resolve recipient chat IDs from 'to' parameter or sender config.

    Supports comma-separated list for multiple recipients.
    If 'to' is provided:
        - Looks up as key in sender_config (info, warning, error, etc.)
        - If not found, uses the value directly as chat ID
    If 'to' is None:
        - Uses first available target from sender_config

    Args:
        sender_config (dict[str, str]): Sender configuration with token and targets.
        to (str | None): Recipient key(s) or direct chat ID(s).

    Returns:
        list[str]: List of resolved chat IDs.

    Raises:
        ValueError: When no recipients can be resolved.
    """
    if to:
        # Handle comma-separated recipients
        to_values = [t.strip() for t in to.split(",")]
        chat_ids: list[str] = []

        for to_value in to_values:
            # Try lookup as key first
            if to_value in sender_config and to_value != "token":
                chat_ids.append(sender_config[to_value])
            else:
                # Use directly as chat ID (basic validation: looks like a chat ID)
                chat_ids.append(to_value)

        if chat_ids:
            return chat_ids

    # No 'to' provided - use first available target
    targets = {k: v for k, v in sender_config.items() if k != "token"}
    if targets:
        return [next(iter(targets.values()))]

    raise ValueError("No recipient configured")


def _truncate_for_logs(value: str, max_length: int = MAX_LOGGED_TELEGRAM_BODY_LENGTH) -> str:
    """
    Bound provider response text before it is written to logs.

    Args:
        value (str): Response body or error text intended for diagnostics.
        max_length (int): Maximum number of characters to keep. Defaults to
            ``MAX_LOGGED_TELEGRAM_BODY_LENGTH``.

    Returns:
        str: Original value when short enough, otherwise a truncated marker.

    Side Effects:
        None.
    """
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}...<truncated length={len(value)}>"


def _telegram_error_payload(response: httpx.Response) -> dict[str, Any]:
    """
    Extract sanitized Telegram error details from an HTTP response.

    Args:
        response (httpx.Response): Telegram API response.

    Returns:
        dict[str, Any]: Sanitized status, error code, description, and bounded
            response body fields suitable for API logs.

    Side Effects:
        None.
    """
    payload: dict[str, Any] = {
        "status_code": response.status_code,
        "response_body": _truncate_for_logs(response.text),
    }
    try:
        body = response.json()
    except ValueError:
        return payload

    if isinstance(body, dict):
        payload["telegram_ok"] = body.get("ok")
        payload["telegram_error_code"] = body.get("error_code")
        payload["telegram_description"] = body.get("description")
    return payload


def _format_telegram_dispatch_error(response: httpx.Response) -> str:
    """
    Build a sanitized error message for a failed Telegram response.

    Args:
        response (httpx.Response): Telegram API response.

    Returns:
        str: Human-readable provider error without bot token or request URL.

    Side Effects:
        None.
    """
    payload = _telegram_error_payload(response)
    description = payload.get("telegram_description")
    if description:
        return f"Telegram HTTP error {response.status_code}: {description}"
    return f"Telegram HTTP error: {response.status_code}"


async def send_telegram_notification(
    formatted_message: str,
    app: str,
    sender_name: str | None = None,
    to: str | None = None,
) -> ProviderDispatchResult:
    """
    Send notification via Telegram Bot API.

    Args:
        formatted_message (str): Pre-formatted message for Telegram MarkdownV2.
        app (str): App identifier for internal logging.
        sender_name (str | None): Specific sender to use. Uses first available if None.
        to (str | None): Recipient key(s) or direct chat ID(s). Comma-separated for multiple.
            Key lookup order: checks sender config for matching key, else uses directly.

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
    if not bot_token:
        raise ProviderDispatchError(
            "Telegram not configured: missing bot token",
            "telegram",
        )

    # Resolve recipients
    try:
        chat_ids = _resolve_recipients(sender_config, to)
    except ValueError as exc:
        raise ProviderDispatchError(str(exc), "telegram") from exc

    # Send to all resolved chat IDs
    errors: list[str] = []
    sent_count = 0

    for chat_id in chat_ids:
        url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": formatted_message,
            "parse_mode": "MarkdownV2",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

            result = response.json()
            if not result.get("ok"):
                error_desc = result.get("description", "Unknown Telegram error")
                errors.append(f"Chat {chat_id}: {error_desc}")
                continue

            logger.info(
                "telegram.notification.sent",
                extra={"app": app, "chat_id": chat_id},
            )
            sent_count += 1

        except httpx.HTTPStatusError as exc:
            logger.error(
                "telegram.notification.http_error",
                extra={
                    "app": app,
                    "sender": sender_name,
                    "chat_id": chat_id,
                    **_telegram_error_payload(exc.response),
                },
            )
            errors.append(_format_telegram_dispatch_error(exc.response))

        except httpx.RequestError as exc:
            logger.error(
                "telegram.notification.request_error",
                extra={
                    "app": app,
                    "sender": sender_name,
                    "chat_id": chat_id,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
            )
            errors.append(f"Chat {chat_id}: Network error")

        except Exception as exc:
            logger.error(
                "telegram.notification.unexpected_error",
                extra={
                    "app": app,
                    "sender": sender_name,
                    "chat_id": chat_id,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
            )
            errors.append(f"Chat {chat_id}: Unexpected error")

    # Determine overall result
    if sent_count == len(chat_ids):
        return ProviderDispatchResult(status="sent", sender=sender_name)
    elif sent_count > 0:
        return ProviderDispatchResult(
            status="partial_failure",
            sender=sender_name,
            error="; ".join(errors),
        )
    else:
        return ProviderDispatchResult(
            status="failed",
            sender=sender_name,
            error="; ".join(errors) if errors else "All sends failed",
        )


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
