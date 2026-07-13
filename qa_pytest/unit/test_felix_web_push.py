"""Unit coverage for Felix Web Push configuration, routing, and persistence."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Optional

import pytest
from fastapi import HTTPException

from api.settings import Settings
from api.shared_schemas.web_push import (
    WebPushSubscriptionDeleteRequest,
    WebPushSubscriptionRequest,
)
from apps.felix.routes import web_push
from apps.felix.services.web_push_service import FelixWebPushService
from backend.shared_services.web_push_config import validate_vapid_public_key
from backend.shared_services.web_push_subscriptions import WebPushSubscription


def _valid_public_key() -> str:
    """Return a URL-safe uncompressed P-256 public-key fixture.

    Args:
        None.

    Returns:
        str: Base64url key accepted by browser and backend validation.

    Side Effects:
        None.
    """
    return base64.urlsafe_b64encode(bytes([4, *([1] * 64)])).decode().rstrip("=")


def _subscription() -> WebPushSubscription:
    """Return one stable browser subscription fixture.

    Args:
        None.

    Returns:
        WebPushSubscription: Provider-neutral subscription material.

    Side Effects:
        None.
    """
    return WebPushSubscription(
        endpoint="https://push.example.test/subscription-1",
        expiration_time=None,
        p256dh="client-public-key",
        auth="client-auth-secret",
    )


class _FakeStore:
    """In-memory service boundary for Felix policy and route tests."""

    def __init__(self) -> None:
        """Create an empty account-scoped fake.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.owner: Optional[str] = None
        self.subscription: Optional[WebPushSubscription] = None

    async def upsert(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Record one account-owned subscription.

        Args:
            user_id (str): Authenticated account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True only for the first registration.

        Side Effects:
            Replaces the in-memory owner and subscription.
        """
        created = self.subscription is None
        self.owner = user_id
        self.subscription = subscription
        return created

    async def delete(self, user_id: str, endpoint: str) -> bool:
        """Delete only a matching owner and endpoint.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint.

        Returns:
            bool: True when the stored record matched and was removed.

        Side Effects:
            Clears the matching in-memory record.
        """
        matches = (
            self.owner == user_id
            and self.subscription is not None
            and self.subscription.endpoint == endpoint
        )
        if matches:
            self.owner = None
            self.subscription = None
        return matches


def test_vapid_public_key_validation_is_strict() -> None:
    """Ensure malformed or compressed public keys are rejected.

    Returns:
        None.
    """
    key = _valid_public_key()
    assert validate_vapid_public_key(key) == key
    with pytest.raises(ValueError, match="not configured"):
        validate_vapid_public_key("")
    with pytest.raises(ValueError, match="uncompressed P-256"):
        validate_vapid_public_key(base64.urlsafe_b64encode(b"short").decode())


def test_subscription_schema_rejects_unsafe_delivery_endpoints() -> None:
    """Ensure future delivery cannot be redirected to an unsafe HTTP target.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="safe HTTPS URL"):
        WebPushSubscriptionRequest.model_validate(
            {
                "endpoint": "http://localhost/internal",
                "expirationTime": None,
                "keys": {"p256dh": "public-key", "auth": "auth-secret"},
            }
        )


def test_public_key_setting_prefers_file_injection(tmp_path: Path) -> None:
    """Ensure deployed public-key files override direct environment values.

    Args:
        tmp_path (Path): Pytest-owned temporary directory.

    Returns:
        None.

    Side Effects:
        Writes one temporary public-key file.
    """
    public_key_file = tmp_path / "felix_web_push_public_key"
    public_key_file.write_text(_valid_public_key(), encoding="utf-8")
    configured = Settings(
        _env_file=None,
        WEB_PUSH_VAPID_PUBLIC_KEY="fallback",
        WEB_PUSH_VAPID_PUBLIC_KEY_FILE=str(public_key_file),
    )

    assert configured.get_web_push_vapid_public_key() == _valid_public_key()


def test_felix_service_keeps_registration_account_scoped() -> None:
    """Ensure Felix forwards authenticated ownership to the shared store.

    Returns:
        None.
    """
    store = _FakeStore()
    service = FelixWebPushService(store=store, public_key_loader=_valid_public_key)

    assert service.get_public_key() == _valid_public_key()
    assert asyncio.run(service.register("user-a", _subscription())) is True
    assert store.owner == "user-a"
    assert asyncio.run(service.unregister("user-b", _subscription().endpoint)) is False
    assert asyncio.run(service.unregister("user-a", _subscription().endpoint)) is True


def test_felix_routes_match_flutter_contract_without_api_prefix() -> None:
    """Ensure route paths exactly match the Flutter endpoint declarations.

    Returns:
        None.
    """
    routes = {
        (route.path, method)
        for route in web_push.router.routes
        for method in route.methods
    }
    assert ("/v1/notifications/web-push/public-key", "GET") in routes
    assert ("/v1/notifications/web-push/subscriptions", "POST") in routes
    assert ("/v1/notifications/web-push/subscriptions", "DELETE") in routes
    assert all(not path.startswith("/api/") for path, _ in routes)


def test_route_mutations_preserve_authenticated_owner_and_idempotency() -> None:
    """Ensure handlers pass the current user and keep missing deletion safe.

    Returns:
        None.
    """
    store = _FakeStore()
    service = FelixWebPushService(store=store, public_key_loader=_valid_public_key)
    request = WebPushSubscriptionRequest.model_validate(
        {
            "endpoint": _subscription().endpoint,
            "expirationTime": None,
            "keys": {"p256dh": "client-public-key", "auth": "client-auth-secret"},
        }
    )
    registered = asyncio.run(
        web_push.register_web_push_subscription(
            request,
            current_user_id="user-a",
            service=service,
        )
    )
    missing = asyncio.run(
        web_push.delete_web_push_subscription(
            WebPushSubscriptionDeleteRequest(endpoint=request.endpoint),
            current_user_id="user-b",
            service=service,
        )
    )

    assert registered.data.created is True
    assert store.owner == "user-a"
    assert missing.data.deleted is False


def test_public_key_route_fails_closed_when_unconfigured() -> None:
    """Ensure missing public configuration becomes a retryable 503 response.

    Returns:
        None.
    """
    service = FelixWebPushService(store=_FakeStore(), public_key_loader=lambda: "")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            web_push.get_web_push_public_key(
                current_user_id="user-a",
                service=service,
            )
        )
    assert exc_info.value.status_code == 503
