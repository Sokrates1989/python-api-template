"""
Notification service for dispatching to configured providers.
"""
from __future__ import annotations

import logging
from typing import Literal

from apps.secure_messaging.schemas.notifications import NotifyRequest
from apps.secure_messaging.services.email_provider import (
    is_email_configured,
    send_email_notification,
)
from apps.secure_messaging.services.markdown_formatter import format_email_content, format_telegram_message
from apps.secure_messaging.services.providers import ProviderDispatchError, ProviderDispatchResult
from apps.secure_messaging.services.redaction import redact_sensitive_content
from apps.secure_messaging.services.telegram_provider import (
    is_telegram_configured,
    send_telegram_notification,
)

logger = logging.getLogger("secure_messaging.notification_service")


def _get_enabled_providers() -> dict[str, bool]:
    """
    Get currently enabled and configured providers.

    Returns:
        dict[str, bool]: Map of provider names to enabled status.
    """
    return {
        "telegram": is_telegram_configured(),
        "email": is_email_configured(),
    }


def _determine_dispatch_targets(
    requested_provider: Literal["telegram", "email", "all"],
    enabled_providers: dict[str, bool],
) -> tuple[list[str], bool]:
    """
    Determine which providers to dispatch to.

    Args:
        requested_provider (str): Provider requested by client.
        enabled_providers (dict): Map of provider names to enabled status.

    Returns:
        tuple[list[str], bool]: (target_providers, has_any_enabled) where
            target_providers is the list to dispatch to, and has_any_enabled
            indicates if at least one provider is configured.

    Raises:
        ValueError: When requested provider is disabled or no providers enabled.
    """
    if requested_provider == "all":
        targets = [name for name, enabled in enabled_providers.items() if enabled]
        if not targets:
            raise ValueError("No providers enabled. Configure Telegram or email.")
        return targets, True

    # Specific provider requested
    if requested_provider not in enabled_providers:
        raise ValueError(f"Unknown provider: {requested_provider}")

    if not enabled_providers[requested_provider]:
        raise ValueError(f"Provider '{requested_provider}' is disabled or not configured")

    return [requested_provider], True


async def dispatch_notification(
    request: NotifyRequest,
) -> tuple[Literal["sent", "partial_failure", "failed"], dict[str, ProviderDispatchResult]]:
    """
    Dispatch a notification to configured providers.

    Args:
        request (NotifyRequest): Validated notification request.

    Returns:
        tuple[str, dict]: (overall_status, provider_results) where
            overall_status is sent, partial_failure, or failed, and
            provider_results maps provider names to their dispatch results.

    Raises:
        ValueError: When provider configuration is invalid.

    Side Effects:
        Sends notifications via external providers.
    """
    # Redact sensitive content before sending
    redacted_message = redact_sensitive_content(request.message)
    redacted_title = redact_sensitive_content(request.title) if request.title else None

    # Determine dispatch targets
    enabled_providers = _get_enabled_providers()
    targets, _ = _determine_dispatch_targets(request.provider, enabled_providers)

    # Get sender name from request (None = use default)
    sender_name = request.sender
    to_override = request.to

    # Dispatch to each target
    results: dict[str, ProviderDispatchResult] = {}
    success_count = 0
    failure_count = 0

    for provider in targets:
        try:
            if provider == "telegram":
                # Format message with optional title and app footer.
                formatted_message = format_telegram_message(redacted_title, redacted_message, app=request.app)
                result = await send_telegram_notification(
                    formatted_message=formatted_message,
                    app=request.app,
                    sender_name=sender_name,
                    to=to_override,
                )
            elif provider == "email":
                # Format email with title as subject
                subject, html_body = format_email_content(
                    title=redacted_title,
                    message=redacted_message,
                    app=request.app,
                )
                result = await send_email_notification(
                    subject=subject,
                    html_body=html_body,
                    app=request.app,
                    sender_name=sender_name,
                    to=to_override,
                )
            else:
                # Should not happen due to validation above
                result = ProviderDispatchResult(
                    status="failed",
                    sender=sender_name,
                    error=f"Unknown provider: {provider}",
                )

            results[provider] = result
            if result.status == "sent":
                success_count += 1
            else:
                failure_count += 1

        except ProviderDispatchError as exc:
            logger.error(
                "notification.dispatch_error",
                extra={
                    "provider": provider,
                    "app": request.app,
                    "sender": sender_name,
                    "error": str(exc),
                },
            )
            results[provider] = ProviderDispatchResult(
                status="failed",
                sender=sender_name,
                error=str(exc),
            )
            failure_count += 1

    # Determine overall status
    if success_count > 0 and failure_count == 0:
        overall_status: Literal["sent", "partial_failure", "failed"] = "sent"
    elif success_count > 0 and failure_count > 0:
        overall_status = "partial_failure"
    else:
        overall_status = "failed"

    logger.info(
        "notification.dispatch_complete",
        extra={
            "app": request.app,
            "provider": request.provider,
            "overall_status": overall_status,
            "success_count": success_count,
            "failure_count": failure_count,
        },
    )

    return overall_status, results
