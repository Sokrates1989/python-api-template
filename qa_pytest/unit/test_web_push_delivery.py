"""Unit coverage for reusable encrypted Web Push delivery and cleanup."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from backend.shared_services.web_push_delivery import (
    MAX_WEB_PUSH_PAYLOAD_BYTES,
    WebPushDeliveryConfig,
    WebPushDeliveryCoordinator,
    WebPushSender,
)
from backend.shared_services.web_push_subscriptions import WebPushSubscription


def _subscription(
    endpoint_suffix: str,
    *,
    expiration_time: Optional[int] = None,
) -> WebPushSubscription:
    """Build deterministic delivery material for one fake endpoint.

    Args:
        endpoint_suffix (str): Final path component identifying behavior.
        expiration_time (Optional[int]): Optional Unix-millisecond expiry.

    Returns:
        WebPushSubscription: Provider-neutral browser subscription.

    Side Effects:
        None.
    """
    return WebPushSubscription(
        endpoint=f"https://push.example.test/{endpoint_suffix}",
        expiration_time=expiration_time,
        p256dh="browser-public-key",
        auth="browser-auth-secret",
    )


def _delivery_config() -> WebPushDeliveryConfig:
    """Return valid deterministic signing configuration.

    Returns:
        WebPushDeliveryConfig: Test-only private reference and contact claim.

    Side Effects:
        None.
    """
    return WebPushDeliveryConfig(
        private_key_reference="private-der-reference",
        subject="mailto:operations@example.test",
        ttl_seconds=600,
        timeout_seconds=4.0,
    )


class _FakeRepository:
    """Store deterministic account subscriptions and deletion observations."""

    def __init__(self, subscriptions: list[WebPushSubscription]) -> None:
        """Create an owner-scoped in-memory repository.

        Args:
            subscriptions (list[WebPushSubscription]): Records returned by list.

        Returns:
            None.

        Side Effects:
            Copies the supplied list into mutable fake state.
        """
        self.subscriptions = list(subscriptions)
        self.deleted: list[tuple[str, str]] = []

    async def list_for_user(self, user_id: str) -> list[WebPushSubscription]:
        """Return all fake records for the requested owner.

        Args:
            user_id (str): Account owner, required to be non-empty.

        Returns:
            list[WebPushSubscription]: Copy of current fake records.

        Raises:
            AssertionError: When no owner id is supplied.

        Side Effects:
            None.
        """
        assert user_id
        return list(self.subscriptions)

    async def delete(self, user_id: str, endpoint: str) -> bool:
        """Delete one matching fake endpoint and record ownership.

        Args:
            user_id (str): Account owner.
            endpoint (str): Endpoint to remove.

        Returns:
            bool: True when a matching record existed.

        Side Effects:
            Removes one record and appends a deletion observation.
        """
        self.deleted.append((user_id, endpoint))
        for index, subscription in enumerate(self.subscriptions):
            if subscription.endpoint == endpoint:
                del self.subscriptions[index]
                return True
        return False


@dataclass
class _Response:
    """Represent the status surface exposed by WebPushException.

    Attributes:
        status_code (int): Remote push-service HTTP status.
    """

    status_code: int


class _RemoteFailure(Exception):
    """Expose one response-bearing transport failure."""

    def __init__(self, status_code: int) -> None:
        """Create a remote failure with no sensitive response content.

        Args:
            status_code (int): Remote HTTP status.

        Returns:
            None.
        """
        super().__init__("remote failure")
        self.response = _Response(status_code)


class _RecordingTransport:
    """Record Web Push arguments and emulate selected remote outcomes."""

    def __init__(self) -> None:
        """Create an empty transport call log.

        Returns:
            None.

        Side Effects:
            Initializes mutable call observations.
        """
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> None:
        """Record one call and raise endpoint-selected remote failures.

        Args:
            **kwargs (Any): ``pywebpush.webpush``-compatible arguments.

        Returns:
            None.

        Raises:
            _RemoteFailure: With 410 for ``gone`` and 503 for ``retry`` paths.

        Side Effects:
            Appends an argument snapshot to ``calls``.
        """
        self.calls.append(kwargs)
        endpoint = kwargs["subscription_info"]["endpoint"]
        if endpoint.endswith("/gone"):
            raise _RemoteFailure(410)
        if endpoint.endswith("/retry"):
            raise _RemoteFailure(503)


def test_delivery_configuration_rejects_unsafe_or_unbounded_values() -> None:
    """Ensure private signing configuration fails closed.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="private key"):
        WebPushDeliveryConfig("", "mailto:operations@example.test")
    with pytest.raises(ValueError, match="mailto or absolute HTTPS"):
        WebPushDeliveryConfig("private", "http://example.test/contact")
    with pytest.raises(ValueError, match="four weeks"):
        WebPushDeliveryConfig(
            "private",
            "mailto:operations@example.test",
            ttl_seconds=2_419_201,
        )


def test_sender_builds_standard_subscription_and_bounded_vapid_call() -> None:
    """Ensure sender passes only standard browser and bounded config fields.

    Returns:
        None.
    """
    transport = _RecordingTransport()
    sender = WebPushSender(_delivery_config(), transport=transport)

    asyncio.run(sender.send(_subscription("accepted"), '{"title":"Felix"}'))

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["subscription_info"] == {
        "endpoint": "https://push.example.test/accepted",
        "keys": {
            "p256dh": "browser-public-key",
            "auth": "browser-auth-secret",
        },
    }
    assert call["vapid_private_key"] == "private-der-reference"
    assert call["vapid_claims"] == {"sub": "mailto:operations@example.test"}
    assert call["ttl"] == 600
    assert call["timeout"] == 4.0


def test_sender_rejects_payload_above_encryption_budget() -> None:
    """Ensure oversized application data never reaches the network transport.

    Returns:
        None.
    """
    transport = _RecordingTransport()
    sender = WebPushSender(_delivery_config(), transport=transport)

    with pytest.raises(ValueError, match="3072-byte"):
        asyncio.run(
            sender.send(
                _subscription("accepted"),
                "x" * (MAX_WEB_PUSH_PAYLOAD_BYTES + 1),
            )
        )
    assert transport.calls == []


def test_coordinator_delivers_and_removes_only_definitively_stale_records() -> None:
    """Ensure expiry/410 cleanup and retryable-failure accounting are distinct.

    Returns:
        None.
    """
    repository = _FakeRepository(
        [
            _subscription("expired", expiration_time=1_999_999),
            _subscription("accepted"),
            _subscription("gone"),
            _subscription("retry"),
        ]
    )
    transport = _RecordingTransport()
    coordinator = WebPushDeliveryCoordinator(
        repository,
        WebPushSender(_delivery_config(), transport=transport),
        clock=lambda: 2000.0,
    )

    report = asyncio.run(coordinator.deliver_to_user("user-a", "{}"))

    assert report.considered == 4
    assert report.delivered == 1
    assert report.expired_removed == 1
    assert report.gone_removed == 1
    assert report.failed == 1
    assert report.removed == 2
    assert [call["subscription_info"]["endpoint"] for call in transport.calls] == [
        "https://push.example.test/accepted",
        "https://push.example.test/gone",
        "https://push.example.test/retry",
    ]
    assert repository.deleted == [
        ("user-a", "https://push.example.test/expired"),
        ("user-a", "https://push.example.test/gone"),
    ]
