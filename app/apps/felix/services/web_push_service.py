"""Felix ownership policy for reusable Web Push subscription persistence.

The service binds the shared provider-aware store to Felix-specific storage
identifiers and public-key configuration. It intentionally does not own private
VAPID signing material, delivery scheduling, or retry/revocation processing.
"""

from __future__ import annotations

from typing import Callable, Optional

from backend.shared_services.web_push_config import validate_vapid_public_key
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


class FelixWebPushService:
    """Coordinate Felix public-key discovery and account-owned subscriptions.

    Attributes:
        _store (Optional[WebPushSubscriptionStore]): Deferred provider edge.
        _public_key_loader (Callable[[], str]): Deferred environment reader.
    """

    def __init__(
        self,
        store: Optional[WebPushSubscriptionStore] = None,
        *,
        public_key_loader: Optional[Callable[[], str]] = None,
    ) -> None:
        """Create the Felix Web Push service.

        Args:
            store (Optional[WebPushSubscriptionStore]): Optional persistence
                override used by tests. Defaults to active-provider storage.
            public_key_loader (Optional[Callable[[], str]]): Optional deferred
                public-key reader. Defaults to the global runtime setting.

        Returns:
            None.

        Side Effects:
            None. Active-provider resolution remains lazy until a mutation.
        """
        self._store = store
        self._public_key_loader = public_key_loader or _load_public_key_setting

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
