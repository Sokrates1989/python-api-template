"""Felix ownership policy for reusable Web Push subscription persistence.

The service binds shared provider-aware storage and encrypted delivery to
Felix-specific storage identifiers, payload policy, and runtime configuration.
Recurring scheduling and durable retry queues remain separate product work.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Optional

from backend.shared_services.web_push_config import validate_vapid_public_key
from backend.shared_services.web_push_delivery import (
    WebPushDeliveryConfig,
    WebPushDeliveryCoordinator,
    WebPushDeliveryReport,
    WebPushSender,
)
from backend.shared_services.web_push_subscriptions import (
    WebPushStorageNames,
    WebPushSubscription,
    WebPushSubscriptionStore,
)

#
# Felix provider storage ownership.
# The generic store stays app-neutral while these identifiers keep every
# persisted subscription inside the Felix namespace.
#
FELIX_WEB_PUSH_STORAGE = WebPushStorageNames(
    sql_table="felix_web_push_subscriptions",
    mongo_collection="felix_web_push_subscriptions",
    neo4j_label="FelixWebPushSubscription",
    neo4j_constraint="felix_web_push_owner_endpoint",
)


@dataclass(frozen=True)
class FelixWebPushMessage:
    """Define one bounded Felix notification payload for the service worker.

    Attributes:
        title (str): Visible notification title.
        body (str): Visible notification body.
        tag (str): Browser replacement/de-duplication tag.
        route (str): Same-app Flutter route beginning with one slash.
        renotify (bool): Whether replacing the tag may alert again.
        require_interaction (bool): Whether supported browsers keep it visible.
        silent (bool): Whether supported browsers suppress sound/vibration.
    """

    title: str
    body: str
    tag: str = "felix-reminder"
    route: str = "/notifications"
    renotify: bool = False
    require_interaction: bool = False
    silent: bool = False

    def __post_init__(self) -> None:
        """Reject blank, oversized, or non-app notification fields.

        Returns:
            None.

        Raises:
            ValueError: When text is blank/oversized or route ownership is
                ambiguous.

        Side Effects:
            None.
        """
        _validate_message_text("title", self.title, maximum=120)
        _validate_message_text("body", self.body, maximum=500)
        _validate_message_text("tag", self.tag, maximum=120)
        if (
            self.route != self.route.strip()
            or not self.route.startswith("/")
            or self.route.startswith("//")
            or len(self.route) > 512
        ):
            raise ValueError("Felix Web Push route must be one bounded app route.")

    def to_payload(self) -> str:
        """Serialize fields consumed by ``felix_service_worker.js``.

        Returns:
            str: Compact UTF-8 JSON notification payload.

        Side Effects:
            None.
        """
        return json.dumps(
            {
                "title": self.title,
                "body": self.body,
                "tag": self.tag,
                "route": self.route,
                "renotify": self.renotify,
                "requireInteraction": self.require_interaction,
                "silent": self.silent,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


class FelixWebPushService:
    """Coordinate Felix public-key discovery and account-owned subscriptions.

    Attributes:
        _store (Optional[WebPushSubscriptionStore]): Deferred provider edge.
        _public_key_loader (Callable[[], str]): Deferred environment reader.
        _delivery (Optional[WebPushDeliveryCoordinator]): Deferred sender.
    """

    def __init__(
        self,
        store: Optional[WebPushSubscriptionStore] = None,
        *,
        public_key_loader: Optional[Callable[[], str]] = None,
        delivery: Optional[WebPushDeliveryCoordinator] = None,
        delivery_config_loader: Optional[Callable[[], WebPushDeliveryConfig]] = None,
    ) -> None:
        """Create the Felix Web Push service.

        Args:
            store (Optional[WebPushSubscriptionStore]): Optional persistence
                override used by tests. Defaults to active-provider storage.
            public_key_loader (Optional[Callable[[], str]]): Optional deferred
                public-key reader. Defaults to the global runtime setting.
            delivery (Optional[WebPushDeliveryCoordinator]): Optional encrypted
                delivery override used by tests or internal workers.
            delivery_config_loader (Optional[Callable[[], WebPushDeliveryConfig]]):
                Optional deferred private signing/network configuration.

        Returns:
            None.

        Side Effects:
            None. Active-provider resolution remains lazy until a mutation.
        """
        self._store = store
        self._public_key_loader = public_key_loader or _load_public_key_setting
        self._delivery = delivery
        self._delivery_config_loader = (
            delivery_config_loader or load_web_push_delivery_config
        )

    def get_public_key(self) -> str:
        """Return the validated browser-safe public VAPID key.

        Args:
            None.

        Returns:
            str: Configured uncompressed P-256 public key.

        Raises:
            ValueError: When public Web Push configuration is unavailable.

        Side Effects:
            May read a file-backed runtime setting.
        """
        return validate_vapid_public_key(self._public_key_loader())

    async def register(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Idempotently associate one browser subscription with an account.

        Args:
            user_id (str): Authenticated Felix account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True when a new provider record was created.

        Side Effects:
            Writes through the active provider store.
        """
        return await self._subscription_store().upsert(user_id, subscription)

    async def unregister(self, user_id: str, endpoint: str) -> bool:
        """Idempotently remove one account-owned browser endpoint.

        Args:
            user_id (str): Authenticated Felix account identifier.
            endpoint (str): Opaque browser endpoint to remove.

        Returns:
            bool: True when an existing provider record was deleted.

        Side Effects:
            Deletes at most one active-provider record.
        """
        return await self._subscription_store().delete(user_id, endpoint)

    async def deliver(
        self,
        user_id: str,
        message: FelixWebPushMessage,
    ) -> WebPushDeliveryReport:
        """Deliver one Felix-owned payload to an account's subscriptions.

        This internal service boundary intentionally has no arbitrary public
        send route. Authorized product schedulers may call it in a later slice.

        Args:
            user_id (str): Internally authorized account identifier.
            message (FelixWebPushMessage): Bounded visible notification.

        Returns:
            WebPushDeliveryReport: Aggregate delivery and stale-cleanup counts.

        Side Effects:
            Reads subscriptions, sends encrypted pushes, and removes endpoints
            proven expired locally or remotely.
        """
        return await self._delivery_coordinator().deliver_to_user(
            user_id,
            message.to_payload(),
        )

    def _subscription_store(self) -> WebPushSubscriptionStore:
        """Return the injected or lazily constructed provider store.

        Args:
            None.

        Returns:
            WebPushSubscriptionStore: Reusable active-provider persistence.

        Side Effects:
            Resolves and caches the global database handler on first mutation.
        """
        if self._store is None:
            self._store = WebPushSubscriptionStore(FELIX_WEB_PUSH_STORAGE)
        return self._store

    def _delivery_coordinator(self) -> WebPushDeliveryCoordinator:
        """Return the injected or lazily configured encrypted sender.

        Returns:
            WebPushDeliveryCoordinator: Account-scoped delivery boundary.

        Raises:
            ValueError: When private signing configuration is unavailable.

        Side Effects:
            May resolve the active provider and validate runtime secrets.
        """
        if self._delivery is None:
            self._delivery = WebPushDeliveryCoordinator(
                self._subscription_store(),
                WebPushSender(self._delivery_config_loader()),
            )
        return self._delivery


def _load_public_key_setting() -> str:
    """Read the generic Web Push public-key setting lazily.

    Args:
        None.

    Returns:
        str: Direct or file-backed public key text.

    Raises:
        ValueError: When a configured key file does not exist.

    Side Effects:
        Imports runtime settings and may read a configured file.
    """
    from api.settings import settings

    return settings.get_web_push_vapid_public_key()


def load_web_push_delivery_config() -> WebPushDeliveryConfig:
    """Read private VAPID and bounded network configuration lazily.

    Returns:
        WebPushDeliveryConfig: Validated signing and delivery settings.

    Raises:
        ValueError: When a secret file or delivery setting is invalid.

    Side Effects:
        Checks a configured private-key file path without logging its contents.
    """
    from api.settings import settings

    return WebPushDeliveryConfig(
        private_key_reference=settings.get_web_push_vapid_private_key_reference(),
        subject=settings.WEB_PUSH_VAPID_SUBJECT,
        ttl_seconds=settings.WEB_PUSH_DEFAULT_TTL_SECONDS,
        timeout_seconds=settings.WEB_PUSH_REQUEST_TIMEOUT_SECONDS,
    )


def _validate_message_text(field_name: str, value: str, *, maximum: int) -> None:
    """Reject blank, outer-whitespace, or oversized notification text.

    Args:
        field_name (str): Human-readable field label for safe errors.
        value (str): Candidate Felix payload text.
        maximum (int): Maximum character count.

    Returns:
        None.

    Raises:
        ValueError: When the value violates the bounded text contract.

    Side Effects:
        None.
    """
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(
            f"Felix Web Push {field_name} must be non-blank and at most "
            f"{maximum} characters."
        )
