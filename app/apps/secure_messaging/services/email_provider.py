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
    "receivers",  # Nested object containing recipient mappings
}


def _has_email_target(sender_config: dict[str, str]) -> bool:
    """
    Return whether an email sender has at least one recipient target.

    Args:
        sender_config (dict[str, str]): Merged sender configuration containing
            SMTP settings and receivers (nested or flat format).

    Returns:
        bool: True when the sender has any recipient target.

    Side Effects:
        None.
    """
    receivers = _get_receivers_dict(sender_config)
    return any(bool(v) for v in receivers.values())


def _get_receivers_dict(sender_config: dict[str, str]) -> dict[str, str]:
    """
    Extract receivers mapping from sender config.

    Supports two formats for backward compatibility:
    1. Nested: {"host": "...", "receivers": {"info": "a@b.com", "warning": "c@d.com"}}
    2. Flat: {"host": "...", "info": "a@b.com", "warning": "c@d.com"}

    Args:
        sender_config (dict[str, str]): Sender configuration.

    Returns:
        dict[str, str]: Mapping of recipient keys to email addresses.
    """
    # Prefer nested receivers object (new format)
    receivers_json = sender_config.get("receivers", "")
    if receivers_json:
        try:
            import json
            nested = json.loads(receivers_json)
            if isinstance(nested, dict):
                return {str(k): str(v) for k, v in nested.items()}
        except (json.JSONDecodeError, ValueError):
            pass

    # Fall back to flat structure (backward compatibility)
    non_target_keys = EMAIL_NON_TARGET_KEYS | {"password"}
    return {k: v for k, v in sender_config.items() if k not in non_target_keys}


def _resolve_recipients(sender_config: dict[str, str], to: str | None) -> list[str]:
    """
    Resolve recipient email addresses from 'to' parameter or sender config.

    Supports comma-separated list for multiple recipients.
    If 'to' is provided:
        - Looks up as key in receivers (info, warning, error, etc.)
        - If not found, uses the value directly as email address
    If 'to' is None:
        - Uses first available receiver from config

    Args:
        sender_config (dict[str, str]): Sender configuration with SMTP settings and receivers.
        to (str | None): Recipient key(s) or direct email address(es).

    Returns:
        list[str]: List of resolved email addresses.

    Raises:
        ValueError: When no recipients can be resolved.
    """
    receivers = _get_receivers_dict(sender_config)

    if to:
        # Handle comma-separated recipients
        to_values = [t.strip() for t in to.split(",")]
        addresses: list[str] = []

        for to_value in to_values:
            # Try lookup as key in receivers first
            if to_value in receivers:
                addresses.append(receivers[to_value])
            else:
                # Use directly as email address
                addresses.append(to_value)

        if addresses:
            return addresses

    # No 'to' provided - use first available receiver
    if receivers:
        return [next(iter(receivers.values()))]

    raise ValueError("No recipient configured")


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
    subject: str,
    html_body: str,
    app: str,
    sender_name: str | None = None,
    to: str | None = None,
) -> ProviderDispatchResult:
    """
    Send notification via SMTP email.

    Args:
        subject (str): Email subject line.
        html_body (str): HTML-formatted email body.
        app (str): App identifier for internal logging.
        sender_name (str | None): Specific sender to use. Uses first available if None.
        to (str | None): Recipient key(s) or direct email address(es). Comma-separated for multiple.
            Key lookup order: checks sender config for matching key, else uses directly.

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

    # Validate configuration
    if not smtp_host:
        raise ProviderDispatchError("Email not configured: missing SMTP host", "email")
    if not from_addr:
        raise ProviderDispatchError("Email not configured: missing from address", "email")

    # Resolve recipients
    try:
        to_addrs = _resolve_recipients(sender_config, to)
    except ValueError as exc:
        raise ProviderDispatchError(str(exc), "email") from exc

    # Send to all resolved recipients
    errors: list[str] = []
    sent_count = 0

    for to_addr in to_addrs:
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
                html_body,
            )

            logger.info(
                "email.notification.sent",
                extra={
                    "app": app,
                    "to": to_addr,
                    "subject": subject,
                },
            )
            sent_count += 1

        except smtplib.SMTPAuthenticationError as exc:
            logger.error("email.notification.auth_error", extra={"app": app})
            errors.append(f"{to_addr}: Authentication failed")

        except smtplib.SMTPConnectError as exc:
            logger.error("email.notification.connect_error", extra={"app": app})
            errors.append(f"{to_addr}: Connection failed")

        except smtplib.SMTPException as exc:
            logger.error(
                "email.notification.smtp_error",
                extra={"app": app, "error": str(exc)},
            )
            errors.append(f"{to_addr}: SMTP error")

        except Exception as exc:
            logger.error(
                "email.notification.unexpected_error",
                extra={"app": app, "error": str(exc)},
            )
            errors.append(f"{to_addr}: Unexpected error")

    # Determine overall result
    if sent_count == len(to_addrs):
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
