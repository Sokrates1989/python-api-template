"""Provider-contract tests for the reusable Web Push subscription store."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from backend.shared_services.web_push_subscriptions import (
    WebPushStorageNames,
    WebPushSubscription,
    WebPushSubscriptionStore,
)


def _subscription() -> WebPushSubscription:
    """Return stable provider-neutral browser subscription material.

    Args:
        None.

    Returns:
        WebPushSubscription: A deterministic subscription fixture.

    Side Effects:
        None.
    """
    return WebPushSubscription(
        endpoint="https://push.example.test/subscription-1",
        expiration_time=None,
        p256dh="client-public-key",
        auth="client-auth-secret",
    )


def _storage_names() -> WebPushStorageNames:
    """Return safe provider identifiers for the test app boundary.

    Args:
        None.

    Returns:
        WebPushStorageNames: Valid SQL, MongoDB, and Neo4j identifiers.

    Side Effects:
        None.
    """
    return WebPushStorageNames(
        sql_table="test_web_push",
        mongo_collection="test_web_push",
        neo4j_label="TestWebPush",
        neo4j_constraint="test_web_push_owner_endpoint",
    )


@dataclass
class _DeleteResult:
    """Represent a minimal MongoDB deletion result.

    Attributes:
        deleted_count (int): Number of removed fake documents.
    """

    deleted_count: int


class _MongoCollection:
    """Emulate the MongoDB operations used by the shared store."""

    def __init__(self) -> None:
        """Create an empty collection and index observation log.

        Returns:
            None.

        Side Effects:
            Initializes mutable in-memory provider state.
        """
        self.document: Optional[dict[str, Any]] = None
        self.index_keys: Optional[list[tuple[str, int]]] = None

    async def create_index(
        self,
        keys: list[tuple[str, int]],
        *,
        unique: bool,
        name: str,
    ) -> str:
        """Record the requested composite uniqueness index.

        Args:
            keys (list[tuple[str, int]]): Ordered MongoDB index fields.
            unique (bool): Whether MongoDB must enforce uniqueness.
            name (str): Stable index name.

        Returns:
            str: The supplied index name.

        Raises:
            AssertionError: When the shared store requests a non-unique index.

        Side Effects:
            Stores the keys for assertions.
        """
        assert unique
        self.index_keys = keys
        return name

    async def find_one(
        self,
        lookup: dict[str, Any],
        projection: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Return the stored document when every lookup field matches.

        Args:
            lookup (dict[str, Any]): Equality fields used by the store.
            projection (dict[str, Any]): Requested fields, ignored by this fake.

        Returns:
            Optional[dict[str, Any]]: A document copy or None.

        Side Effects:
            None.
        """
        del projection
        if self.document and all(
            self.document.get(key) == value for key, value in lookup.items()
        ):
            return dict(self.document)
        return None

    async def update_one(
        self,
        lookup: dict[str, Any],
        mutation: dict[str, dict[str, Any]],
        *,
        upsert: bool,
    ) -> None:
        """Apply the store's simplified MongoDB upsert.

        Args:
            lookup (dict[str, Any]): Fields copied into a new document.
            mutation (dict[str, dict[str, Any]]): Set and insert-only values.
            upsert (bool): Whether a missing document may be created.

        Raises:
            AssertionError: When registration disables upsert behavior.

        Returns:
            None.

        Side Effects:
            Creates or refreshes the in-memory document.
        """
        assert upsert
        existing = self.document or {**lookup, **mutation["$setOnInsert"]}
        self.document = {**existing, **mutation["$set"]}

    async def delete_one(self, lookup: dict[str, Any]) -> _DeleteResult:
        """Delete the stored document when every lookup field matches.

        Args:
            lookup (dict[str, Any]): Account, digest, and endpoint values.

        Returns:
            _DeleteResult: One when deleted, otherwise zero.

        Side Effects:
            Clears a matching in-memory document.
        """
        matches = bool(
            self.document
            and all(self.document.get(key) == value for key, value in lookup.items())
        )
        if matches:
            self.document = None
        return _DeleteResult(deleted_count=int(matches))


class MongoDBHandler:
    """Expose a MongoDB-shaped database mapping to provider detection."""

    def __init__(self, collection: _MongoCollection) -> None:
        """Bind the fake collection under the configured storage name.

        Args:
            collection (_MongoCollection): In-memory collection to expose.

        Returns:
            None.

        Side Effects:
            Creates a database mapping consumed by the store.
        """
        self.database = {"test_web_push": collection}


class _SqlResult:
    """Represent scalar and row-count output from fake SQL execution."""

    def __init__(self, *, scalar: Optional[int] = None, rowcount: int = 0) -> None:
        """Create one fake SQL result.

        Args:
            scalar (Optional[int]): Existing row identifier, defaulting to None.
            rowcount (int): Mutation count, defaulting to zero.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Optional[int]:
        """Return the configured optional scalar value.

        Returns:
            Optional[int]: Existing fake primary key or None.
        """
        return self.scalar


class _SqlSession:
    """Emulate the asynchronous SQLAlchemy session used by the store."""

    def __init__(self) -> None:
        """Create an empty account/endpoint row state.

        Returns:
            None.

        Side Effects:
            Initializes mutable in-memory provider state.
        """
        self.exists = False
        self.params: Optional[dict[str, Any]] = None

    async def __aenter__(self) -> "_SqlSession":
        """Enter the fake asynchronous session context.

        Returns:
            _SqlSession: This reusable fake session.
        """
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Exit without suppressing an active exception.

        Args:
            exc_type: Optional exception type.
            exc: Optional exception instance.
            traceback: Optional exception traceback.

        Returns:
            None.

        Side Effects:
            None.
        """
        return None

    async def execute(self, statement, params: dict[str, Any]) -> _SqlResult:
        """Apply one recognized SQL store statement.

        Args:
            statement: SQLAlchemy text clause emitted by the shared store.
            params (dict[str, Any]): Bound owner and subscription values.

        Returns:
            _SqlResult: Scalar lookup or mutation row count.

        Raises:
            AssertionError: When the store emits an unexpected statement.

        Side Effects:
            Updates the in-memory row state and last parameter snapshot.
        """
        sql = str(statement).strip().upper()
        self.params = dict(params)
        if sql.startswith("SELECT"):
            return _SqlResult(scalar=1 if self.exists else None)
        if sql.startswith("INSERT"):
            self.exists = True
            return _SqlResult(rowcount=1)
        if sql.startswith("UPDATE"):
            return _SqlResult(rowcount=int(self.exists))
        if sql.startswith("DELETE"):
            deleted = int(self.exists)
            self.exists = False
            return _SqlResult(rowcount=deleted)
        raise AssertionError(f"Unexpected SQL statement: {sql}")

    async def commit(self) -> None:
        """Commit no external transaction.

        Returns:
            None.

        Side Effects:
            None.
        """

    async def rollback(self) -> None:
        """Roll back no external transaction.

        Returns:
            None.

        Side Effects:
            None.
        """


class SQLHandler:
    """Expose a SQLAlchemy-shaped async session factory."""

    def __init__(self, session: _SqlSession) -> None:
        """Bind the reusable in-memory SQL session.

        Args:
            session (_SqlSession): In-memory SQL session to reuse.

        Returns:
            None.

        Side Effects:
            Creates the session factory consumed by the shared store.
        """
        self.AsyncSessionLocal = lambda: session


class _Neo4jResult:
    """Wrap one optional Neo4j result record."""

    def __init__(self, record: Optional[dict[str, Any]]) -> None:
        """Create a result returning the supplied record.

        Args:
            record (Optional[dict[str, Any]]): Optional query result record.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.record = record

    def single(self) -> Optional[dict[str, Any]]:
        """Return the configured optional result record.

        Returns:
            Optional[dict[str, Any]]: Configured record or None.
        """
        return self.record


class _Neo4jSession:
    """Emulate the synchronous Neo4j session used in a worker thread."""

    def __init__(self) -> None:
        """Create an empty account/endpoint node state.

        Returns:
            None.

        Side Effects:
            Initializes mutable in-memory provider state.
        """
        self.nodes: dict[tuple[str, str], dict[str, Any]] = {}

    def __enter__(self) -> "_Neo4jSession":
        """Enter the synchronous fake session context.

        Returns:
            _Neo4jSession: This reusable fake session.
        """
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Exit without suppressing an active exception.

        Args:
            exc_type: Optional exception type.
            exc: Optional exception instance.
            traceback: Optional exception traceback.

        Returns:
            None.

        Side Effects:
            None.
        """
        return None

    def run(self, query: str, **params: Any) -> _Neo4jResult:
        """Apply constraint, merge, or delete Cypher emitted by the store.

        Args:
            query (str): Cypher statement emitted by the shared store.
            **params (Any): Bound owner and subscription values.

        Returns:
            _Neo4jResult: Optional created/deleted boolean record.

        Raises:
            AssertionError: When the store emits unexpected Cypher.

        Side Effects:
            Creates, refreshes, or deletes one in-memory node.
        """
        normalized = " ".join(query.split()).upper()
        if normalized.startswith("CREATE CONSTRAINT"):
            return _Neo4jResult(None)
        key = (params["user_id"], params["endpoint_hash"])
        if normalized.startswith("MERGE"):
            created = key not in self.nodes
            self.nodes[key] = dict(params)
            return _Neo4jResult({"created": created})
        if normalized.startswith("MATCH"):
            existing = self.nodes.get(key)
            deleted = bool(existing and existing["endpoint"] == params["endpoint"])
            if deleted:
                del self.nodes[key]
            return _Neo4jResult({"deleted": deleted})
        raise AssertionError(f"Unexpected Cypher statement: {normalized}")


class _Neo4jDriver:
    """Expose one reusable fake Neo4j session."""

    def __init__(self, session: _Neo4jSession) -> None:
        """Bind the in-memory Neo4j session.

        Args:
            session (_Neo4jSession): In-memory Neo4j session.

        Returns:
            None.

        Side Effects:
            None.
        """
        self._session = session

    def session(self) -> _Neo4jSession:
        """Return the reusable fake session.

        Returns:
            _Neo4jSession: In-memory Neo4j session.
        """
        return self._session


class Neo4jHandler:
    """Expose a Neo4j-shaped driver to provider detection."""

    def __init__(self, session: _Neo4jSession) -> None:
        """Bind the fake session through a Neo4j driver.

        Args:
            session (_Neo4jSession): In-memory Neo4j session.

        Returns:
            None.

        Side Effects:
            Creates the driver consumed by the shared store.
        """
        self.driver = _Neo4jDriver(session)


def test_storage_identifiers_reject_dynamic_query_injection() -> None:
    """Ensure app-owned dynamic identifiers cannot contain query syntax.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="Unsafe Web Push sql_table"):
        WebPushStorageNames(
            sql_table="records; DROP TABLE users",
            mongo_collection="records",
            neo4j_label="Records",
            neo4j_constraint="records_owner_endpoint",
        )


def test_mongodb_store_upserts_and_deletes_with_owner_digest() -> None:
    """Ensure MongoDB registration is idempotent and owner scoped.

    Returns:
        None.
    """
    collection = _MongoCollection()
    store = WebPushSubscriptionStore(
        _storage_names(),
        handler=MongoDBHandler(collection),
    )

    assert asyncio.run(store.upsert("user-a", _subscription())) is True
    assert asyncio.run(store.upsert("user-a", _subscription())) is False
    assert collection.document is not None
    assert len(collection.document["endpoint_hash"]) == 64
    assert collection.index_keys == [("user_id", 1), ("endpoint_hash", 1)]
    assert asyncio.run(store.delete("user-b", _subscription().endpoint)) is False
    assert asyncio.run(store.delete("user-a", _subscription().endpoint)) is True


def test_sql_store_upserts_and_deletes_idempotently() -> None:
    """Ensure SQL registration refreshes one fixed-width owner record.

    Returns:
        None.
    """
    session = _SqlSession()
    store = WebPushSubscriptionStore(
        _storage_names(),
        handler=SQLHandler(session),
    )

    assert asyncio.run(store.upsert("user-a", _subscription())) is True
    assert asyncio.run(store.upsert("user-a", _subscription())) is False
    assert session.params is not None
    assert len(session.params["endpoint_hash"]) == 64
    assert asyncio.run(store.delete("user-a", _subscription().endpoint)) is True
    assert asyncio.run(store.delete("user-a", _subscription().endpoint)) is False


def test_neo4j_store_upserts_and_deletes_idempotently() -> None:
    """Ensure Neo4j registration merges one owner/digest node.

    Returns:
        None.
    """
    session = _Neo4jSession()
    store = WebPushSubscriptionStore(
        _storage_names(),
        handler=Neo4jHandler(session),
    )

    assert asyncio.run(store.upsert("user-a", _subscription())) is True
    assert asyncio.run(store.upsert("user-a", _subscription())) is False
    assert asyncio.run(store.delete("user-b", _subscription().endpoint)) is False
    assert asyncio.run(store.delete("user-a", _subscription().endpoint)) is True
