"""
SMTP email provider for secure messaging.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from apps.secure_messaging.config.runtime import SecureMessagingSettings
from apps.secure_messaging.services.providers import ProviderDispatchError, ProviderDispatchResult

logger = logging.getLogger("secure_messaging.email")
EMAIL_NON_TARGET_KEYS = {
    "host",
    "port",
    "username",
    "password",
    "use_tls",
    "from",
}


def _has_email_target(sender_config: dict[str, str]) -> bool:
    """
    Return whether an email sender has at least one recipient target.

    Args:
        sender_config (dict[str, str]): Merged sender configuration containing
            SMTP settings and level/default recipient targets.

    Returns:
        bool: True when the sender has any recipient target.

    Side Effects:
        None.
    """
    return any(
        bool(value)
        for key, value in sender_config.items()
        if key not in EMAIL_NON_TARGET_KEYS
    )


def _format_email_subject(level: str, app: str, title: str) -> str:
    """
    Format email subject line.

    Args:
        level (str): Notification level.
        app (str): App identifier.
        title (str): Notification title.

    Returns:
        str: Formatted subject line.
    """
    level_upper = level.upper()
    return f"[{level_upper}] {app}: {title}"


def _format_email_body(
    level: str,
    title: str,
    app: str,
    message: str,
    tags: list[str],
) -> str:
    """
    Format plain text email body.

    Args:
        level (str): Notification level.
        title (str): Notification title.
        app (str): App identifier.
        message (str): Redacted notification message.
        tags (list[str]): Categorization tags.

    Returns:
        str: Formatted plain text email body.
    """
    lines = [
        f"App: {app}",
        f"Level: {level}",
        f"Title: {title}",
    ]

    if tags:
        lines.append(f"Tags: {', '.join(tags)}")

    lines.extend(["", message])
    return "\n".join(lines)


def _send_smtp_sync(
    smtp_host: str,
    smtp_port: int,
    use_tls: bool,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """
    Synchronous SMTP send function for use with asyncio.to_thread.

    Args:
        smtp_host (str): SMTP server host.
        smtp_port (int): SMTP server port.
        use_tls (bool): Whether to use STARTTLS.
        username (str): SMTP auth username.
        password (str): SMTP auth password.
        from_addr (str): From email address.
        to_addr (str): To email address.
        subject (str): Email subject.
        body (str): Email body.

    Returns:
        None.

    Raises:
        smtplib.SMTPException: On SMTP errors.
    """
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(msg)


async def send_email_notification(
    level: str,
    title: str,
    app: str,
    message: str,
    tags: list[str],
    sender_name: str | None = None,
    to: str | None = None,
) -> ProviderDispatchResult:
    """
    Send notification via SMTP email.

    Args:
        level (str): Notification level.
        title (str): Notification title.
        app (str): App identifier.
        message (str): Redacted notification message.
        tags (list[str]): Categorization tags.
        sender_name (str | None): Specific sender to use. Uses first available if None.
        to (str | None): Optional override recipient. Uses sender default if None.

    Returns:
        ProviderDispatchResult: Dispatch result status.

    Raises:
        ProviderDispatchError: When SMTP send fails.

    Side Effects:
        Sends email via SMTP.
    """
    # Get sender configuration
    senders = SecureMessagingSettings.get_email_senders()
    if not senders:
        raise ProviderDispatchError("No email senders configured", "email")

    # Select sender
    if sender_name:
        sender_config = senders.get(sender_name)
        if not sender_config:
            available = list(senders.keys())
            raise ProviderDispatchError(
                f"Unknown sender '{sender_name}'. Available: {available}",
                "email",
            )
    else:
        # Use first available sender as default
        sender_name, sender_config = next(iter(senders.items()))

    # Extract SMTP settings from sender config
    smtp_host = sender_config.get("host", "")
    smtp_port_str = sender_config.get("port", "587")
    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        smtp_port = 587
    use_tls_str = sender_config.get("use_tls", "true")
    use_tls = use_tls_str.lower() in ("true", "1", "yes", "on")
    username = sender_config.get("username", "")
    password = sender_config.get("password", "")
    from_addr = sender_config.get("from", "")

    # Determine recipient: custom override > level-based default > default_to > first available target
    if to:
        to_addr = to
    elif level in sender_config:
        to_addr = sender_config[level]
    elif "default_to" in sender_config:
        to_addr = sender_config["default_to"]
    elif "default" in sender_config:
        to_addr = sender_config["default"]
    else:
        # Use first defined target as fallback (excluding SMTP settings)
        targets = {
            k: v
            for k, v in sender_config.items()
            if k not in EMAIL_NON_TARGET_KEYS
        }
        to_addr = next(iter(targets.values())) if targets else ""

    # Validate configuration
    if not smtp_host:
        raise ProviderDispatchError("Email not configured: missing SMTP host", "email")
    if not from_addr:
        raise ProviderDispatchError("Email not configured: missing from address", "email")
    if not to_addr:
        raise ProviderDispatchError("Email not configured: missing to address", "email")

    subject = _format_email_subject(level, app, title)
    body = _format_email_body(level, title, app, message, tags)

    try:
        await asyncio.to_thread(
            _send_smtp_sync,
            smtp_host,
            smtp_port,
            use_tls,
            username,
            password,
            from_addr,
            to_addr,
            subject,
            body,
        )

        logger.info(
            "email.notification.sent",
            extra={
                "app": app,
                "level": level,
                "to": to_addr,
                "subject": subject,
            },
        )
        return ProviderDispatchResult(status="sent", sender=sender_name)

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("email.notification.auth_error", extra={"app": app, "level": level})
        raise ProviderDispatchError("Email authentication failed", "email") from exc

    except smtplib.SMTPConnectError as exc:
        logger.error("email.notification.connect_error", extra={"app": app, "level": level})
        raise ProviderDispatchError("Email connection failed", "email") from exc

    except smtplib.SMTPException as exc:
        logger.error(
            "email.notification.smtp_error",
            extra={"app": app, "level": level, "error": str(exc)},
        )
        raise ProviderDispatchError(f"Email SMTP error: {type(exc).__name__}", "email") from exc

    except Exception as exc:
        logger.error(
            "email.notification.unexpected_error",
            extra={"app": app, "level": level, "error": str(exc)},
        )
        raise ProviderDispatchError("Email dispatch failed: unexpected error", "email") from exc


def is_email_configured() -> bool:
    """
    Check if email provider is properly configured.

    Returns:
        bool: True if at least one sender has SMTP settings and a recipient.
    """
    try:
        senders = SecureMessagingSettings.get_email_senders()
        if not senders:
            return False

        # Match the dispatch path, which accepts level-based recipients,
        # default_to/default, or any other named recipient target.
        for sender_config in senders.values():
            if (sender_config.get("host") and
                sender_config.get("from") and
                _has_email_target(sender_config)):
                return True
        return False
    except ValueError:
        return False
