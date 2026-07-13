"""Provider-boundary coverage for durable Web Push dispatch storage."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from backend.shared_services.web_push_dispatch import WebPushDispatchDraft
from backend.shared_services.web_push_dispatch_store import (
    WebPushDispatchStorageNames,
    WebPushDispatchStore,
)

_NOW = datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc)


@dataclass
class _MutationResult:
    """Represent MongoDB mutation counts used by the adapter.

    Attributes:
        matched_count (int): Documents matching an update filter.
        modified_count (int): Documents changed by an update.
        deleted_count (int): Documents removed by a deletion.
    """

    matched_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0


class _MongoCollection:
    """Emulate replacement operations for one MongoDB dispatch document."""

    def __init__(self, document: dict[str, Any] | None = None) -> None:
        """Create one optional in-memory dispatch document.

        Args:
            document (dict[str, Any] | None): Initial provider document.

        Returns:
            None.

        Side Effects:
            Copies initial state for later mutation assertions.
        """
        self.document = dict(document) if document else None
        self.index_names: list[str] = []
        self.insertions = 0

    async def create_index(
        self,
        keys: list[tuple[str, int]],
        *,
        name: str,
        unique: bool = False,
    ) -> str:
        """Record an idempotent MongoDB index request.

        Args:
            keys (list[tuple[str, int]]): Ordered index fields.
            name (str): Stable index name.
            unique (bool): Whether the index enforces uniqueness.

        Returns:
            str: Supplied index name.

        Side Effects:
            Records the index name; fields and uniqueness need no emulation.
        """
        del keys, unique
        self.index_names.append(name)
        return name

    async def delete_many(self, lookup: dict[str, Any]) -> _MutationResult:
        """Return no obsolete rows for the focused lease-preservation case.

        Args:
            lookup (dict[str, Any]): Owner/key/lease deletion filter.

        Returns:
            _MutationResult: Zero deletions.

        Side Effects:
            None.
        """
        del lookup
        return _MutationResult()

    async def update_one(
        self,
        lookup: dict[str, Any],
        mutation: dict[str, dict[str, Any]],
        *,
        upsert: bool,
    ) -> _MutationResult:
        """Apply an update only when the fake document's lease is available.

        Args:
            lookup (dict[str, Any]): Owner/key and available-lease filter.
            mutation (dict[str, dict[str, Any]]): Adapter reset values.
            upsert (bool): Whether update may insert; expected to be False.

        Returns:
            _MutationResult: Match/change counts.

        Raises:
            AssertionError: When replacement requests an unsafe update upsert.

        Side Effects:
            Mutates an available matching document.
        """
        assert upsert is False
        if not self.document:
            return _MutationResult()
        identity_matches = all(
            self.document.get(key) == value
            for key, value in lookup.items()
            if key != "$or"
        )
        now_text = lookup["$or"][1]["lease_until"]["$lte"]
        lease_until = self.document.get("lease_until")
        available = lease_until is None or lease_until <= now_text
        if not identity_matches or not available:
            return _MutationResult()
        self.document.update(mutation["$set"])
        return _MutationResult(matched_count=1, modified_count=1)

    async def find_one(
        self,
        lookup: dict[str, Any],
        projection: dict[str, int],
    ) -> dict[str, Any] | None:
        """Return a matching owner/key document.

        Args:
            lookup (dict[str, Any]): Owner/key identity filter.
            projection (dict[str, int]): Requested fields, ignored by the fake.

        Returns:
            dict[str, Any] | None: Copy of a matching document.

        Side Effects:
            None.
        """
        del projection
        if self.document and all(
            self.document.get(key) == value for key, value in lookup.items()
        ):
            return dict(self.document)
        return None

    async def insert_one(self, document: dict[str, Any]) -> None:
        """Insert one new fake MongoDB document.

        Args:
            document (dict[str, Any]): Complete provider document.

        Returns:
            None.

        Side Effects:
            Stores the document and increments the insertion count.
        """
        self.document = dict(document)
        self.insertions += 1


class MongoDBHandler:
    """Expose a MongoDB-named handler for provider-family detection."""

    def __init__(self, collection: _MongoCollection) -> None:
        """Bind the fake collection to the expected storage name.

        Args:
            collection (_MongoCollection): In-memory provider collection.

        Returns:
            None.
        """
        self.database = {"dispatch_jobs": collection}


class _SqlResult:
    """Expose mapping and mutation result methods used by SQL storage."""

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        rowcount: int = 0,
    ) -> None:
        """Create one fake SQL result.

        Args:
            rows (list[dict[str, Any]] | None): Selected mappings.
            rowcount (int): Mutation count, defaulting to zero.

        Returns:
            None.
        """
        self.rows = list(rows or [])
        self.rowcount = rowcount

    def mappings(self) -> "_SqlResult":
        """Return this object as a mapping-result facade.

        Returns:
            _SqlResult: This result.
        """
        return self

    def all(self) -> list[dict[str, Any]]:
        """Return every configured mapping.

        Returns:
            list[dict[str, Any]]: Copied mappings.
        """
        return list(self.rows)

    def one_or_none(self) -> dict[str, Any] | None:
        """Return the only configured mapping or None.

        Returns:
            dict[str, Any] | None: Single mapping when present.

        Raises:
            AssertionError: When the fake contains more than one mapping.
        """
        assert len(self.rows) <= 1
        return dict(self.rows[0]) if self.rows else None


class _SqlSession:
    """Emulate replacement queries against one actively leased SQL row."""

    def __init__(self) -> None:
        """Create an empty SQL query and mutation log.

        Returns:
            None.
        """
        self.queries: list[str] = []
        self.mutations = 0

    async def __aenter__(self) -> "_SqlSession":
        """Enter the reusable async SQL session.

        Returns:
            _SqlSession: This fake session.
        """
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """Exit without suppressing an exception.

        Args:
            exc_type: Optional exception type.
            exc: Optional exception instance.
            traceback: Optional exception traceback.

        Returns:
            None.
        """
        return None

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any],
    ) -> _SqlResult:
        """Return deterministic rows for the adapter's replacement queries.

        Args:
            statement (Any): SQLAlchemy text statement.
            params (dict[str, Any]): Bound query values.

        Returns:
            _SqlResult: Existing schedule or active-lease mapping.

        Side Effects:
            Records normalized SQL and any unexpected mutation.
        """
        del params
        query = " ".join(str(statement).split())
        self.queries.append(query)
        if query.startswith("SELECT schedule_key"):
            return _SqlResult([{"schedule_key": "same"}])
        if query.startswith("SELECT job_id, lease_until"):
            return _SqlResult(
                [{"job_id": "job-1", "lease_until": _NOW + timedelta(minutes=2)}]
            )
        self.mutations += 1
        return _SqlResult(rowcount=1)

    async def commit(self) -> None:
        """Commit no external transaction.

        Returns:
            None.
        """


class SQLHandler:
    """Expose a SQL-named async session factory for provider detection."""

    def __init__(self, session: _SqlSession) -> None:
        """Bind one reusable fake SQL session.

        Args:
            session (_SqlSession): In-memory query facade.

        Returns:
            None.
        """
        self._session = session

    def AsyncSessionLocal(self) -> _SqlSession:
        """Return the reusable fake async SQL session.

        Returns:
            _SqlSession: In-memory query facade.
        """
        return self._session


class _Neo4jResult:
    """Return one optional aggregate Neo4j result record."""

    def __init__(self, record: dict[str, Any] | None = None) -> None:
        """Create one fake Neo4j result.

        Args:
            record (dict[str, Any] | None): Optional single record.

        Returns:
            None.
        """
        self.record = record

    def single(self) -> dict[str, Any] | None:
        """Return the configured single record.

        Returns:
            dict[str, Any] | None: Configured record.
        """
        return self.record


class _Neo4jSession:
    """Capture replacement Cypher for lease-guard assertions."""

    def __init__(self) -> None:
        """Create an empty Cypher observation list.

        Returns:
            None.
        """
        self.queries: list[str] = []

    def __enter__(self) -> "_Neo4jSession":
        """Enter the reusable Neo4j session.

        Returns:
            _Neo4jSession: This fake session.
        """
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        """Exit without suppressing an exception.

        Args:
            exc_type: Optional exception type.
            exc: Optional exception instance.
            traceback: Optional exception traceback.

        Returns:
            None.
        """
        return None

    def run(self, query: str, **params: Any) -> _Neo4jResult:
        """Record one Cypher statement and return replacement aggregates.

        Args:
            query (str): Adapter Cypher statement.
            **params (Any): Bound values, ignored by this query-shape fake.

        Returns:
            _Neo4jResult: Removed count for the obsolete-row query.

        Side Effects:
            Records normalized query text.
        """
        del params
        normalized = " ".join(query.split())
        self.queries.append(normalized)
        if "RETURN size(obsolete) AS removed" in normalized:
            return _Neo4jResult({"removed": 0})
        return _Neo4jResult()


class Neo4jHandler:
    """Expose a Neo4j-named driver for provider detection."""

    def __init__(self, session: _Neo4jSession) -> None:
        """Bind one reusable fake Neo4j session.

        Args:
            session (_Neo4jSession): In-memory query facade.

        Returns:
            None.
        """
        self.driver = _Neo4jDriver(session)


class _Neo4jDriver:
    """Return one reusable fake Neo4j session."""

    def __init__(self, session: _Neo4jSession) -> None:
        """Store the session returned by ``session``.

        Args:
            session (_Neo4jSession): Query facade.

        Returns:
            None.
        """
        self._session = session

    def session(self) -> _Neo4jSession:
        """Return the configured fake session.

        Returns:
            _Neo4jSession: Query facade.
        """
        return self._session


def _names() -> WebPushDispatchStorageNames:
    """Return deterministic valid provider identifiers.

    Returns:
        WebPushDispatchStorageNames: Test storage names.
    """
    return WebPushDispatchStorageNames(
        sql_table="dispatch_jobs",
        mongo_collection="dispatch_jobs",
        neo4j_label="DispatchJob",
        neo4j_constraint="dispatch_owner_key",
    )


def _draft() -> WebPushDispatchDraft:
    """Return one deterministic desired dispatch occurrence.

    Returns:
        WebPushDispatchDraft: Future schedule draft.
    """
    return WebPushDispatchDraft(
        schedule_key="same",
        payload='{"kind":"checkin","locale":"en"}',
        due_at=_NOW + timedelta(hours=1),
        expires_at=_NOW + timedelta(days=1),
    )


def test_storage_names_reject_dynamic_query_syntax() -> None:
    """Ensure app-owned identifiers cannot inject provider query text.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="Unsafe Web Push dispatch sql_table"):
        WebPushDispatchStorageNames(
            sql_table="jobs; DROP TABLE users",
            mongo_collection="jobs",
            neo4j_label="Jobs",
            neo4j_constraint="jobs_owner_key",
        )


def test_mongodb_replacement_preserves_active_worker_lease() -> None:
    """Ensure schedule replacement cannot reset an in-flight MongoDB job.

    Returns:
        None.
    """
    original = {
        "job_id": "job-1",
        "user_id": "user-a",
        "schedule_key": "same",
        "payload": "original",
        "lease_token": "worker-a",
        "lease_until": "2026-07-13T20:02:00Z",
    }
    collection = _MongoCollection(original)
    store = WebPushDispatchStore(_names(), handler=MongoDBHandler(collection))

    result = asyncio.run(store.replace_user_schedule("user-a", [_draft()], now=_NOW))

    assert result.scheduled == 1
    assert collection.document == original
    assert collection.insertions == 0
    assert len(collection.index_names) == 2


def test_sql_replacement_locks_and_preserves_active_worker_lease() -> None:
    """Ensure SQL replacement row-locks and skips an active worker lease.

    Returns:
        None.
    """
    session = _SqlSession()
    store = WebPushDispatchStore(_names(), handler=SQLHandler(session))

    result = asyncio.run(store.replace_user_schedule("user-a", [_draft()], now=_NOW))

    assert result.scheduled == 1
    assert session.mutations == 0
    assert any("SELECT job_id, lease_until" in query for query in session.queries)
    assert any("FOR UPDATE" in query for query in session.queries)


def test_neo4j_replacement_guards_active_worker_lease() -> None:
    """Ensure Neo4j merge resets only missing or elapsed leases.

    Returns:
        None.
    """
    session = _Neo4jSession()
    store = WebPushDispatchStore(_names(), handler=Neo4jHandler(session))

    result = asyncio.run(store.replace_user_schedule("user-a", [_draft()], now=_NOW))

    merge = next(query for query in session.queries if query.startswith("MERGE"))
    assert result.scheduled == 1
    assert "WHERE j.lease_until IS NULL OR j.lease_until <= $now" in merge
