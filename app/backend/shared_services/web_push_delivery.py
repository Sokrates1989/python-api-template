"""Reusable VAPID signing, Web Push transport, and stale-endpoint cleanup.

This module owns only app-neutral delivery mechanics. Product payload policy,
recipient selection, scheduling, retry queues, and public routes remain with
the selected backend app. Private keys are passed to ``pywebpush`` by value or
mounted-file reference and are never included in results or logs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from backend.shared_services.web_push_subscriptions import WebPushSubscription

MAX_WEB_PUSH_PAYLOAD_BYTES = 3072
MAX_WEB_PUSH_TTL_SECONDS = 2_419_200
PERMANENT_SUBSCRIPTION_STATUS_CODES = frozenset({404, 410})


class WebPushSubscriptionRepository(Protocol):
    """Describe persistence required by the generic delivery coordinator."""

    async def list_for_user(self, user_id: str) -> list[WebPushSubscription]:
        """Return every subscription owned by one authenticated user.

        Args:
            user_id (str): Authenticated account identifier.

        Returns:
            list[WebPushSubscription]: Account-owned browser subscriptions.
        """

    async def delete(self, user_id: str, endpoint: str) -> bool:
        """Delete one account-owned browser endpoint.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint.

        Returns:
            bool: True when an existing record was removed.
        """


class WebPushDeliveryError(RuntimeError):
    """Report a retryable or configuration-related delivery failure.

    Attributes:
        status_code (int | None): Optional remote push-service status code.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Create a delivery error without retaining sensitive response data.

        Args:
            message (str): Safe operational summary.
            status_code (int | None): Optional remote status code.

        Returns:
            None.
        """
        super().__init__(message)
        self.status_code = status_code


class WebPushSubscriptionGone(WebPushDeliveryError):
    """Signal that a remote push service permanently rejected an endpoint."""


@dataclass(frozen=True)
class WebPushDeliveryConfig:
    """Define secret signing and bounded network-delivery configuration.

    Attributes:
        private_key_reference (str): DER key text or mounted PEM path.
        subject (str): VAPID contact using ``mailto:`` or absolute HTTPS.
        ttl_seconds (int): Push-service retention, defaulting to one day.
        timeout_seconds (float): Per-request timeout, defaulting to ten seconds.
    """

    private_key_reference: str
    subject: str
    ttl_seconds: int = 86_400
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        """Reject missing secrets and unsafe or unbounded delivery settings.

        Raises:
            ValueError: When the private key, subject, TTL, or timeout is not
                suitable for bounded VAPID delivery.

        Returns:
            None.

        Side Effects:
            None.
        """
        if not self.private_key_reference.strip():
            raise ValueError("Web Push VAPID private key is not configured.")
        if not _is_valid_vapid_subject(self.subject):
            raise ValueError(
                "Web Push VAPID subject must be a mailto or absolute HTTPS URI."
            )
        if not 0 <= self.ttl_seconds <= MAX_WEB_PUSH_TTL_SECONDS:
            raise ValueError("Web Push TTL must be between zero and four weeks.")
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError(
                "Web Push timeout must be greater than zero and at most 60s."
            )


@dataclass(frozen=True)
class WebPushDeliveryReport:
    """Summarize one account-scoped delivery attempt without endpoint data.

    Attributes:
        considered (int): Subscriptions loaded for the account.
        delivered (int): Remote push services that accepted a message.
        expired_removed (int): Locally expired records removed before sending.
        gone_removed (int): Remotely expired records removed after 404/410.
        failed (int): Retryable/configuration-safe per-endpoint failures.
    """

    considered: int
    delivered: int
    expired_removed: int
    gone_removed: int
    failed: int

    @property
    def removed(self) -> int:
        """Return the total number of stale provider records removed.

        Returns:
            int: Sum of locally expired and remotely gone subscriptions.
        """
        return self.expired_removed + self.gone_removed


WebPushTransport = Callable[..., Any]


class WebPushSender:
    """Encrypt and send one payload through a synchronous Web Push transport."""

    def __init__(
        self,
        config: WebPushDeliveryConfig,
        *,
        transport: WebPushTransport | None = None,
    ) -> None:
        """Create a sender with injectable transport for isolated verification.

        Args:
            config (WebPushDeliveryConfig): Validated VAPID/network settings.
            transport (WebPushTransport | None): Optional synchronous sender;
                defaults to a lazy ``pywebpush.webpush`` adapter.

        Returns:
            None.
        """
        self.config = config
        self._transport = transport or _send_with_pywebpush

    async def send(self, subscription: WebPushSubscription, payload: str) -> None:
        """Send one bounded UTF-8 payload without blocking the event loop.

        Args:
            subscription (WebPushSubscription): Browser delivery material.
            payload (str): Serialized app-owned notification payload.

        Returns:
            None.

        Raises:
            ValueError: When the UTF-8 payload exceeds the safe size bound.
            WebPushSubscriptionGone: When the remote endpoint returns 404/410.
            WebPushDeliveryError: For other transport failures.

        Side Effects:
            Performs one outbound HTTPS request in a worker thread.
        """
        _validate_payload(payload)
        try:
            await asyncio.to_thread(
                self._transport,
                subscription_info=_subscription_info(subscription),
                data=payload,
                vapid_private_key=self.config.private_key_reference,
                vapid_claims={"sub": self.config.subject},
                ttl=self.config.ttl_seconds,
                timeout=self.config.timeout_seconds,
            )
        except WebPushDeliveryError:
            raise
        except Exception as exc:
            status_code = _response_status_code(exc)
            if status_code in PERMANENT_SUBSCRIPTION_STATUS_CODES:
                raise WebPushSubscriptionGone(
                    "Web Push subscription is no longer available.",
                    status_code=status_code,
                ) from exc
            raise WebPushDeliveryError(
                "Web Push delivery was not accepted.",
                status_code=status_code,
            ) from exc


class WebPushDeliveryCoordinator:
    """Deliver to one account and remove only definitively stale endpoints."""

    def __init__(
        self,
        repository: WebPushSubscriptionRepository,
        sender: WebPushSender,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create an account-scoped delivery coordinator.

        Args:
            repository (WebPushSubscriptionRepository): Subscription storage.
            sender (WebPushSender): Configured encrypted transport.
            clock (Callable[[], float]): Unix-second clock used for expiry.

        Returns:
            None.
        """
        self.repository = repository
        self.sender = sender
        self._clock = clock

    async def deliver_to_user(
        self,
        user_id: str,
        payload: str,
    ) -> WebPushDeliveryReport:
        """Deliver one payload to every current subscription for an account.

        Args:
            user_id (str): Authenticated or internally authorized account id.
            payload (str): Serialized app-owned notification payload.

        Returns:
            WebPushDeliveryReport: Aggregate acceptance and cleanup counts.

        Side Effects:
            Reads account subscriptions, performs outbound delivery, and
            deletes locally expired or remotely gone endpoints.
        """
        subscriptions = await self.repository.list_for_user(user_id)
        counts = _MutableDeliveryCounts(considered=len(subscriptions))
        now_millis = int(self._clock() * 1000)
        for subscription in subscriptions:
            await self._deliver_one(user_id, subscription, payload, now_millis, counts)
        return counts.freeze()

    async def _deliver_one(
        self,
        user_id: str,
        subscription: WebPushSubscription,
        payload: str,
        now_millis: int,
        counts: "_MutableDeliveryCounts",
    ) -> None:
        """Deliver or clean one subscription while updating aggregate counts.

        Args:
            user_id (str): Account owner.
            subscription (WebPushSubscription): Candidate endpoint.
            payload (str): Serialized app-owned notification payload.
            now_millis (int): Current Unix timestamp in milliseconds.
            counts (_MutableDeliveryCounts): Mutable aggregate accumulator.

        Returns:
            None.

        Side Effects:
            May send one request or delete one stale subscription.
        """
        if _is_expired(subscription, now_millis):
            counts.expired_removed += int(
                await self.repository.delete(user_id, subscription.endpoint)
            )
            return
        try:
            await self.sender.send(subscription, payload)
        except WebPushSubscriptionGone:
            counts.gone_removed += int(
                await self.repository.delete(user_id, subscription.endpoint)
            )
        except WebPushDeliveryError:
            counts.failed += 1
        else:
            counts.delivered += 1


@dataclass
class _MutableDeliveryCounts:
    """Accumulate delivery counts before returning an immutable report."""

    considered: int = 0
    delivered: int = 0
    expired_removed: int = 0
    gone_removed: int = 0
    failed: int = 0

    def freeze(self) -> WebPushDeliveryReport:
        """Return an immutable snapshot of current counts.

        Returns:
            WebPushDeliveryReport: Current aggregate values.
        """
        return WebPushDeliveryReport(
            considered=self.considered,
            delivered=self.delivered,
            expired_removed=self.expired_removed,
            gone_removed=self.gone_removed,
            failed=self.failed,
        )


def _send_with_pywebpush(**kwargs: Any) -> Any:
    """Load and invoke ``pywebpush`` only when real delivery is requested.

    Args:
        **kwargs (Any): Keyword arguments accepted by ``pywebpush.webpush``.

    Returns:
        Any: Transport response returned by ``pywebpush``.

    Raises:
        Exception: Propagates library, encryption, or network errors for safe
            classification by :class:`WebPushSender`.

    Side Effects:
        Imports the optional transport and performs outbound HTTPS delivery.
    """
    from pywebpush import webpush

    return webpush(**kwargs)


def _subscription_info(subscription: WebPushSubscription) -> dict[str, Any]:
    """Convert provider-neutral storage into the standard browser contract.

    Args:
        subscription (WebPushSubscription): Stored browser delivery material.

    Returns:
        dict[str, Any]: ``pywebpush`` subscription payload.
    """
    return {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }


def _validate_payload(payload: str) -> None:
    """Enforce a conservative encrypted-payload size budget.

    Args:
        payload (str): Serialized application payload.

    Returns:
        None.

    Raises:
        ValueError: When payload is not text or exceeds 3072 UTF-8 bytes.
    """
    if not isinstance(payload, str):
        raise ValueError("Web Push payload must be serialized text.")
    if len(payload.encode("utf-8")) > MAX_WEB_PUSH_PAYLOAD_BYTES:
        raise ValueError("Web Push payload exceeds the 3072-byte safety limit.")


def _response_status_code(exc: Exception) -> int | None:
    """Extract a remote status code without reading or retaining response data.

    Args:
        exc (Exception): Transport exception raised by ``pywebpush``.

    Returns:
        int | None: Integer status code when a response exists.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _is_expired(subscription: WebPushSubscription, now_millis: int) -> bool:
    """Return whether a browser-declared expiry has elapsed.

    Args:
        subscription (WebPushSubscription): Stored browser subscription.
        now_millis (int): Current Unix timestamp in milliseconds.

    Returns:
        bool: True only when a declared expiry is not in the future.
    """
    expiration = subscription.expiration_time
    return expiration is not None and expiration <= now_millis


def _is_valid_vapid_subject(subject: str) -> bool:
    """Return whether a VAPID contact is a safe mailto or HTTPS URI.

    Args:
        subject (str): Candidate VAPID ``sub`` claim.

    Returns:
        bool: True for a non-empty mailto address or absolute safe HTTPS URI.
    """
    value = subject.strip()
    if value != subject or not value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme.lower() == "mailto":
        return bool(
            parsed.path
            and "@" in parsed.path
            and not parsed.query
            and not parsed.fragment
        )
    return bool(
        parsed.scheme.lower() == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )
