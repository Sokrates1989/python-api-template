"""Provider-neutral persistence for account-owned Web Push subscriptions.

The storage boundary accepts app-owned SQL table, MongoDB collection, and
Neo4j label names while keeping subscription behavior reusable across backend
apps. Callers remain responsible for SQL migrations, public-key configuration,
delivery scheduling, and product-specific authorization policy.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database import get_database_handler

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class WebPushStorageNames:
    """Define app-owned provider storage identifiers.

    Attributes:
        sql_table (str): Existing SQL table receiving subscription rows.
        mongo_collection (str): MongoDB collection receiving documents.
        neo4j_label (str): Neo4j node label receiving subscription nodes.
        neo4j_constraint (str): Neo4j uniqueness-constraint identifier.
    """

    sql_table: str
    mongo_collection: str
    neo4j_label: str
    neo4j_constraint: str

    def __post_init__(self) -> None:
        """Reject unsafe dynamic storage identifiers.

        Args:
            None.

        Returns:
            None.

        Raises:
            ValueError: When any identifier contains unsafe characters.

        Side Effects:
            None.
        """
        for field_name, value in (
            ("sql_table", self.sql_table),
            ("mongo_collection", self.mongo_collection),
            ("neo4j_label", self.neo4j_label),
            ("neo4j_constraint", self.neo4j_constraint),
        ):
            if not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"Unsafe Web Push {field_name}: {value!r}")


@dataclass(frozen=True)
class WebPushSubscription:
    """Represent browser subscription material required for encrypted delivery.

    Attributes:
        endpoint (str): Opaque push-service endpoint.
        expiration_time (Optional[int]): Optional expiry timestamp in millis.
        p256dh (str): Browser payload-encryption public key.
        auth (str): Browser payload-encryption authentication secret.
    """

    endpoint: str
    expiration_time: Optional[int]
    p256dh: str
    auth: str


class WebPushSubscriptionStore:
    """Persist subscriptions through the active promoted database provider.

    Attributes:
        handler (Any): Active MongoDB, SQL, or Neo4j database handler.
        names (WebPushStorageNames): Validated app-owned storage identifiers.
    """

    def __init__(
        self,
        names: WebPushStorageNames,
        *,
        handler: Any = None,
    ) -> None:
        """Create a provider-aware subscription store.

        Args:
            names (WebPushStorageNames): App-owned provider identifiers.
            handler (Any): Optional database-handler override used by tests.

        Returns:
            None.

        Side Effects:
            Resolves the global database handler when no override is supplied.
        """
        self.names = names
        self.handler = handler if handler is not None else get_database_handler()

    async def upsert(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Create or refresh one account-owned subscription.

        Args:
            user_id (str): Authenticated account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True when a new record was created, otherwise False.

        Raises:
            ValueError: When the active database provider is unsupported.

        Side Effects:
            Writes one provider record and may create a MongoDB index or Neo4j
            constraint.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            return await self._upsert_mongodb(user_id, subscription)
        if provider == "sql":
            return await self._upsert_sql(user_id, subscription)
        if provider == "neo4j":
            return await asyncio.to_thread(
                self._upsert_neo4j,
                user_id,
                subscription,
            )
        raise ValueError(f"Unsupported Web Push database provider: {provider}")

    async def delete(self, user_id: str, endpoint: str) -> bool:
        """Idempotently remove one account-owned endpoint.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint scoped to the account.

        Returns:
            bool: True when an existing provider record was deleted.

        Raises:
            ValueError: When the active database provider is unsupported.

        Side Effects:
            Deletes at most one provider record.
        """
        provider = self._provider_name()
        if provider == "mongodb":
            return await self._delete_mongodb(user_id, endpoint)
        if provider == "sql":
            return await self._delete_sql(user_id, endpoint)
        if provider == "neo4j":
            return await asyncio.to_thread(self._delete_neo4j, user_id, endpoint)
        raise ValueError(f"Unsupported Web Push database provider: {provider}")

    def _provider_name(self) -> str:
        """Normalize the active handler into one supported provider family.

        Args:
            None.

        Returns:
            str: ``mongodb``, ``sql``, ``neo4j``, or the unknown class name.

        Side Effects:
            None.
        """
        handler_name = type(self.handler).__name__
        return {
            "MongoDBHandler": "mongodb",
            "SQLHandler": "sql",
            "Neo4jHandler": "neo4j",
        }.get(handler_name, handler_name)

    async def _upsert_mongodb(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Upsert one MongoDB subscription document.

        Args:
            user_id (str): Authenticated account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True when no matching document existed before the write.

        Side Effects:
            Ensures the account/endpoint unique index and writes one document.
        """
        collection = self.handler.database[self.names.mongo_collection]
        await collection.create_index(
            [("user_id", 1), ("endpoint_hash", 1)],
            unique=True,
            name=f"idx_{self.names.mongo_collection}_owner_endpoint",
        )
        lookup = {
            "user_id": user_id,
            "endpoint_hash": _endpoint_hash(subscription.endpoint),
        }
        existing = await collection.find_one(lookup, {"_id": 1})
        now = _iso_now()
        await collection.update_one(
            lookup,
            {
                "$set": {
                    "endpoint": subscription.endpoint,
                    **_subscription_payload(subscription, updated_at=now),
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return existing is None

    async def _delete_mongodb(self, user_id: str, endpoint: str) -> bool:
        """Delete one MongoDB subscription document.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint.

        Returns:
            bool: True when one document was deleted.

        Side Effects:
            Deletes at most one matching MongoDB document.
        """
        collection = self.handler.database[self.names.mongo_collection]
        result = await collection.delete_one(
            {
                "user_id": user_id,
                "endpoint_hash": _endpoint_hash(endpoint),
                "endpoint": endpoint,
            }
        )
        return bool(result.deleted_count)

    async def _upsert_sql(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Create or refresh one SQL subscription row.

        Args:
            user_id (str): Authenticated account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True when a new row was created.

        Side Effects:
            Inserts or updates one row and commits the SQL transaction.
        """
        table_name = self.names.sql_table
        params = _sql_params(user_id, subscription)
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    f"SELECT pk FROM {table_name} "  # nosec B608
                    "WHERE user_id = :user_id AND endpoint_hash = :endpoint_hash"
                ),
                params,
            )
            created = result.scalar_one_or_none() is None
            try:
                await session.execute(
                    text(
                        _sql_insert(table_name) if created else _sql_update(table_name)
                    ),
                    params,
                )
                await session.commit()
                return created
            except IntegrityError:
                await session.rollback()
                await session.execute(text(_sql_update(table_name)), params)
                await session.commit()
                return False

    async def _delete_sql(self, user_id: str, endpoint: str) -> bool:
        """Delete one SQL subscription row.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint.

        Returns:
            bool: True when one row was deleted.

        Side Effects:
            Deletes at most one row and commits the SQL transaction.
        """
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    f"DELETE FROM {self.names.sql_table} "  # nosec B608
                    "WHERE user_id = :user_id AND endpoint_hash = :endpoint_hash "
                    "AND endpoint = :endpoint"
                ),
                {
                    "user_id": user_id,
                    "endpoint_hash": _endpoint_hash(endpoint),
                    "endpoint": endpoint,
                },
            )
            await session.commit()
            return bool(result.rowcount)

    def _upsert_neo4j(
        self,
        user_id: str,
        subscription: WebPushSubscription,
    ) -> bool:
        """Create or refresh one Neo4j subscription node.

        Args:
            user_id (str): Authenticated account identifier.
            subscription (WebPushSubscription): Browser subscription material.

        Returns:
            bool: True when a new node was created.

        Side Effects:
            Ensures a uniqueness constraint and writes one node.
        """
        label = self.names.neo4j_label
        now = _iso_now()
        with self.handler.driver.session() as session:
            session.run(
                f"CREATE CONSTRAINT {self.names.neo4j_constraint} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE (n.user_id, n.endpoint_hash) IS UNIQUE"
            )
            record = session.run(
                f"""
                MERGE (s:{label} {{
                    user_id: $user_id,
                    endpoint_hash: $endpoint_hash
                }})
                ON CREATE SET s.created_at = $now
                SET s.endpoint = $endpoint,
                    s.expiration_time = $expiration_time,
                    s.p256dh = $p256dh,
                    s.auth = $auth,
                    s.updated_at = $now
                RETURN s.created_at = $now AS created
                """,
                user_id=user_id,
                endpoint_hash=_endpoint_hash(subscription.endpoint),
                endpoint=subscription.endpoint,
                expiration_time=subscription.expiration_time,
                p256dh=subscription.p256dh,
                auth=subscription.auth,
                now=now,
            ).single()
        return bool(record and record["created"])

    def _delete_neo4j(self, user_id: str, endpoint: str) -> bool:
        """Delete one Neo4j subscription node.

        Args:
            user_id (str): Authenticated account identifier.
            endpoint (str): Opaque browser endpoint.

        Returns:
            bool: True when one node was deleted.

        Side Effects:
            Deletes at most one matching Neo4j node.
        """
        with self.handler.driver.session() as session:
            record = session.run(
                f"""
                MATCH (s:{self.names.neo4j_label} {{
                    user_id: $user_id,
                    endpoint_hash: $endpoint_hash,
                    endpoint: $endpoint
                }})
                WITH collect(s) AS subscriptions
                FOREACH (item IN subscriptions | DELETE item)
                RETURN size(subscriptions) > 0 AS deleted
                """,
                user_id=user_id,
                endpoint_hash=_endpoint_hash(endpoint),
                endpoint=endpoint,
            ).single()
        return bool(record and record["deleted"])


def _subscription_payload(
    subscription: WebPushSubscription,
    *,
    updated_at: str,
) -> dict[str, Any]:
    """Build provider-neutral mutable subscription fields.

    Args:
        subscription (WebPushSubscription): Browser subscription material.
        updated_at (str): Current UTC timestamp text.

    Returns:
        dict[str, Any]: Persistence fields excluding account and created time.

    Side Effects:
        None.
    """
    return {
        "expiration_time": subscription.expiration_time,
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
        "updated_at": updated_at,
    }


def _sql_params(
    user_id: str,
    subscription: WebPushSubscription,
) -> dict[str, Any]:
    """Build bound SQL parameters for one subscription write.

    Args:
        user_id (str): Authenticated account identifier.
        subscription (WebPushSubscription): Browser subscription material.

    Returns:
        dict[str, Any]: Bound values for insert and update statements.

    Side Effects:
        None.
    """
    return {
        "user_id": user_id,
        "endpoint": subscription.endpoint,
        "endpoint_hash": _endpoint_hash(subscription.endpoint),
        "expiration_time": subscription.expiration_time,
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
        "updated_at": datetime.now(timezone.utc),
    }


def _sql_insert(table_name: str) -> str:
    """Return the validated SQL insertion statement.

    Args:
        table_name (str): Validated app-owned table identifier.

    Returns:
        str: Parameterized insertion statement.

    Side Effects:
        None.
    """
    # ``table_name`` passed this boundary through WebPushStorageNames' strict
    # identifier allowlist; every external value remains a bound parameter.
    return f"""
        INSERT INTO {table_name} (
            user_id, endpoint, endpoint_hash, expiration_time, p256dh, auth,
            created_at, updated_at
        ) VALUES (
            :user_id, :endpoint, :endpoint_hash, :expiration_time, :p256dh, :auth,
            :updated_at, :updated_at
        )
    """  # nosec B608


def _sql_update(table_name: str) -> str:
    """Return the validated SQL update statement.

    Args:
        table_name (str): Validated app-owned table identifier.

    Returns:
        str: Parameterized account/endpoint update statement.

    Side Effects:
        None.
    """
    # ``table_name`` passed this boundary through WebPushStorageNames' strict
    # identifier allowlist; every external value remains a bound parameter.
    return f"""
        UPDATE {table_name}
        SET expiration_time = :expiration_time,
            p256dh = :p256dh,
            auth = :auth,
            updated_at = :updated_at,
            endpoint = :endpoint
        WHERE user_id = :user_id AND endpoint_hash = :endpoint_hash
    """  # nosec B608


def _endpoint_hash(endpoint: str) -> str:
    """Return a fixed-width lookup digest for an opaque endpoint.

    Args:
        endpoint (str): Full browser push-service endpoint.

    Returns:
        str: Lowercase SHA-256 hexadecimal digest.

    Side Effects:
        None.
    """
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _iso_now() -> str:
    """Return the current UTC timestamp as ISO-8601 text.

    Args:
        None.

    Returns:
        str: Timezone-aware UTC timestamp.

    Side Effects:
        Reads the system clock.
    """
    return datetime.now(timezone.utc).isoformat()
