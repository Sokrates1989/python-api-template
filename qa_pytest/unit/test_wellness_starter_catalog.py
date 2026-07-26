"""Focused provider contracts for canonical wellness catalog bootstrap.

The tests align SQL, MongoDB, and Neo4j payload builders with the shared Felix
catalog. They also protect exact legacy replacement, deletion tombstones,
custom/partial data, and concurrent first-request rechecks.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.mongodb.common import (
    starter_activities as mongodb_starter_activities,
)
from backend.services.mongodb.common import (
    starter_categories as mongodb_starter_categories,
)
from backend.services.neo4j.common import starter_activities as neo4j_starter_activities
from backend.services.neo4j.common import starter_categories as neo4j_starter_categories
from backend.services.neo4j.wellness_catalog_seed import Neo4jWellnessCatalogSeeder
from backend.services.sql.wellness_catalog_seed import SQLWellnessCatalogSeeder
from backend.services.wellness_starter_catalog import (
    LEGACY_STARTER_ACTIVITY_IDS,
    LEGACY_STARTER_CATEGORY_KEYS,
    STARTER_ACTIVITY_IDS,
    STARTER_CATEGORY_KEYS,
    build_starter_activity_payloads,
    build_starter_category_payloads,
    should_seed_starter_group,
)


class _DatabaseResult:
    """Expose result accessors consumed by provider seed test doubles."""

    def __init__(self, value: Any) -> None:
        """Store the value returned by scalar or record access.

        Args:
            value (Any): Result value returned by the configured accessor.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.value = value

    def scalar_one_or_none(self) -> Any:
        """Return the configured SQL scalar result.

        Args:
            None.

        Returns:
            Any: Configured scalar value, including ``None`` for no row.

        Side Effects:
            None.
        """
        return self.value

    def scalars(self) -> _DatabaseResult:
        """Return this fake as a SQL scalar-result view.

        Returns:
            _DatabaseResult: This result wrapper.
        """
        return self

    def all(self) -> list[Any]:
        """Return the configured SQL scalar sequence as a list.

        Returns:
            list[Any]: Configured values copied into a list.
        """
        return list(self.value)

    def single(self) -> Any:
        """Return the configured Neo4j single-record result.

        Args:
            None.

        Returns:
            Any: Configured record value, including ``None`` for no node.

        Side Effects:
            None.
        """
        return self.value

    def consume(self) -> None:
        """Consume a fake Neo4j write result without external work.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            None.
        """
        return None

    def __getitem__(self, key: str) -> Any:
        """Read one field from the configured record.

        Args:
            key (str): Record field name.

        Returns:
            Any: Stored field value.
        """
        return self.value[key]


class _NeoTransaction:
    """Simulate catalog state transitions used by the Neo4j seeder."""

    def __init__(
        self,
        activity_ids: set[str],
        category_keys: set[str],
        tombstone_types: set[str] | None = None,
    ) -> None:
        """Initialize owner-scoped fake graph state.

        Args:
            activity_ids (set[str]): Persisted activity identifiers.
            category_keys (set[str]): Persisted category identifiers.
            tombstone_types (set[str] | None): Entity types with deletion
                markers. Defaults to no tombstones.
        """
        self.activity_ids = set(activity_ids)
        self.category_keys = set(category_keys)
        self.tombstone_types = set(tombstone_types or set())
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **parameters: Any) -> _DatabaseResult:
        """Interpret the bounded Cypher statements emitted by the seeder.

        Args:
            query (str): Cypher statement under test.
            **parameters (Any): Named Cypher parameters.

        Returns:
            _DatabaseResult: Query-specific fake result.

        Raises:
            AssertionError: When the seeder emits an unexpected query.

        Side Effects:
            Applies delete/create statements to the fake catalog state.
        """
        statement = " ".join(query.split())
        self.calls.append((statement, parameters))
        if "__wellness_seed_lock" in statement:
            return _DatabaseResult({"user_id": parameters["user_id"]})
        if "collect(a.id)" in statement:
            return _DatabaseResult({"identifiers": list(self.activity_ids)})
        if "collect(c.key)" in statement:
            return _DatabaseResult({"identifiers": list(self.category_keys)})
        if "count(t) > 0" in statement:
            return _DatabaseResult(
                {"present": parameters["entity_type"] in self.tombstone_types}
            )
        if "DETACH DELETE a" in statement:
            self.activity_ids.clear()
            return _DatabaseResult(None)
        if "DETACH DELETE c" in statement:
            self.category_keys.clear()
            return _DatabaseResult(None)
        if "UNWIND" in statement and "WellnessActivityCategory" in statement:
            self.category_keys = {item["key"] for item in parameters["items"]}
            return _DatabaseResult(None)
        if "UNWIND" in statement and "WellnessActivity" in statement:
            self.activity_ids = {item["id"] for item in parameters["items"]}
            return _DatabaseResult(None)
        raise AssertionError(f"Unexpected Cypher in seed test: {statement}")


def _mock_async_session(*results: _DatabaseResult) -> MagicMock:
    """Build an asynchronous SQL session with ordered execute results.

    Args:
        *results (_DatabaseResult): Values returned by successive ``execute``
            calls.

    Returns:
        MagicMock: Async-context-compatible session test double.

    Side Effects:
        None.
    """
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(side_effect=list(results))
    session.add_all = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _without_timestamps(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove provider timestamp fields before catalog payload comparisons.

    Args:
        items (list[dict[str, Any]]): Provider-specific seed payloads.

    Returns:
        list[dict[str, Any]]: Fresh payload copies without timestamp fields.

    Side Effects:
        None.
    """
    return [
        {
            key: value
            for key, value in item.items()
            if key not in {"created_at", "updated_at"}
        }
        for item in items
    ]


def test_shared_catalog_is_complete_and_provider_helpers_match() -> None:
    """Keep SQL, MongoDB, and Neo4j seed payloads on the canonical 34/16 set."""
    user_id = "catalog-owner"
    activities = build_starter_activity_payloads(user_id)
    categories = build_starter_category_payloads(user_id)
    category_keys = {item["key"] for item in categories}

    assert len(activities) == 34
    assert len(categories) == 16
    assert {item["id"] for item in activities} == STARTER_ACTIVITY_IDS
    assert category_keys == STARTER_CATEGORY_KEYS
    assert all(set(item["category_keys"]) <= category_keys for item in activities)
    assert [item["sort_order"] for item in activities] == [5, *range(10, 331, 10)]
    assert {item["id"] for item in activities if item["harmful"]} == {
        "doom-scrolling",
        "late-screen-spiral",
        "skip-breaks",
    }

    assert _without_timestamps(mongodb_starter_activities(user_id)) == activities
    assert _without_timestamps(neo4j_starter_activities(user_id)) == activities
    assert _without_timestamps(mongodb_starter_categories(user_id)) == categories
    assert _without_timestamps(neo4j_starter_categories(user_id)) == categories

    sql_activities = SQLWellnessCatalogSeeder.starter_activities(user_id)
    sql_categories = SQLWellnessCatalogSeeder.starter_categories(user_id)
    assert {item.id for item in sql_activities} == STARTER_ACTIVITY_IDS
    assert {item.key for item in sql_categories} == STARTER_CATEGORY_KEYS


@pytest.mark.parametrize(
    ("persisted", "has_tombstones", "expected"),
    [
        (set(), False, True),
        (set(), True, False),
        (set(LEGACY_STARTER_ACTIVITY_IDS), False, True),
        (set(LEGACY_STARTER_ACTIVITY_IDS), True, False),
        ({"breathe-reset"}, False, False),
        ({"custom-activity"}, False, False),
        (set(STARTER_ACTIVITY_IDS), False, False),
    ],
)
def test_seed_eligibility_is_empty_or_exact_legacy_without_tombstones(
    persisted: set[str],
    has_tombstones: bool,
    expected: bool,
) -> None:
    """Reject tombstoned, partial, custom, and current catalog groups.

    Args:
        persisted (set[str]): Complete persisted identifier set.
        has_tombstones (bool): Whether the group records user deletions.
        expected (bool): Expected seed eligibility.

    Returns:
        None.
    """
    assert (
        should_seed_starter_group(
            persisted,
            legacy_identifiers=LEGACY_STARTER_ACTIVITY_IDS,
            has_tombstones=has_tombstones,
        )
        is expected
    )


def test_sql_seed_replaces_exact_legacy_groups_under_user_lock() -> None:
    """Replace only the exact SQL legacy signatures in one locked write."""
    probe_session = _mock_async_session()
    write_session = _mock_async_session(_DatabaseResult(None), _DatabaseResult(None))
    verification_session = _mock_async_session()
    handler = MagicMock()
    handler.AsyncSessionLocal = MagicMock(
        side_effect=[probe_session, write_session, verification_session]
    )
    seeder = SQLWellnessCatalogSeeder(handler)
    seeder.ensure_user_exists = AsyncMock()
    seeder._seed_decisions = AsyncMock(
        side_effect=[
            (
                set(LEGACY_STARTER_ACTIVITY_IDS),
                set(LEGACY_STARTER_CATEGORY_KEYS),
                True,
                True,
            ),
            (
                set(LEGACY_STARTER_ACTIVITY_IDS),
                set(LEGACY_STARTER_CATEGORY_KEYS),
                True,
                True,
            ),
        ]
    )
    seeder._catalog_identifiers = AsyncMock(
        return_value=(set(STARTER_ACTIVITY_IDS), set(STARTER_CATEGORY_KEYS))
    )

    asyncio.run(seeder.ensure("catalog-owner"))

    assert [len(call.args[0]) for call in write_session.add_all.call_args_list] == [
        34,
        16,
    ]
    assert write_session.execute.await_count == 2
    write_session.commit.assert_awaited_once()
    assert any(
        call.kwargs.get("lock_for_update") is True
        for call in seeder.ensure_user_exists.await_args_list
    )


def test_sql_seed_recheck_skips_groups_completed_by_concurrent_winner() -> None:
    """Recheck SQL state after locking and avoid duplicate first-request rows."""
    probe_session = _mock_async_session()
    write_session = _mock_async_session()
    verification_session = _mock_async_session()
    handler = MagicMock()
    handler.AsyncSessionLocal = MagicMock(
        side_effect=[probe_session, write_session, verification_session]
    )
    seeder = SQLWellnessCatalogSeeder(handler)
    seeder.ensure_user_exists = AsyncMock()
    seeder._seed_decisions = AsyncMock(
        side_effect=[
            (set(), set(), True, True),
            (
                set(STARTER_ACTIVITY_IDS),
                set(STARTER_CATEGORY_KEYS),
                False,
                False,
            ),
        ]
    )
    seeder._catalog_identifiers = AsyncMock(
        return_value=(set(STARTER_ACTIVITY_IDS), set(STARTER_CATEGORY_KEYS))
    )

    asyncio.run(seeder.ensure("catalog-owner"))

    write_session.add_all.assert_not_called()
    write_session.execute.assert_not_awaited()
    assert any(
        call.kwargs.get("lock_for_update") is True
        for call in seeder.ensure_user_exists.await_args_list
    )


def test_mongodb_seed_replaces_exact_legacy_groups_after_lock_recheck() -> None:
    """Replace both exact MongoDB legacy signatures under the owner lock."""
    pytest.importorskip("motor")
    from backend.services.mongodb.wellness_catalog_seed import (
        MongoWellnessCatalogSeeder,
    )

    activities = MagicMock()
    categories = MagicMock()
    tombstones = MagicMock()
    seed_locks = MagicMock()
    seed_locks.find_one = AsyncMock(return_value=None)
    seeder = MongoWellnessCatalogSeeder(
        activities_collection=activities,
        categories_collection=categories,
        tombstones_collection=tombstones,
        seed_locks_collection=seed_locks,
    )
    seeder.ensure_indexes = AsyncMock()
    seeder._catalog_seed_decisions = AsyncMock(
        side_effect=[
            (
                set(LEGACY_STARTER_ACTIVITY_IDS),
                set(LEGACY_STARTER_CATEGORY_KEYS),
                True,
                True,
            ),
            (
                set(LEGACY_STARTER_ACTIVITY_IDS),
                set(LEGACY_STARTER_CATEGORY_KEYS),
                True,
                True,
            ),
        ]
    )
    seeder._acquire_seed_lock = AsyncMock(return_value="test-lock")
    seeder._release_seed_lock = AsyncMock()
    seeder._seed_document_group = AsyncMock()

    asyncio.run(seeder.ensure("catalog-owner"))

    assert seeder._seed_document_group.await_count == 2
    assert seeder._seed_document_group.await_args_list[0].kwargs[
        "previous_identifiers"
    ] == LEGACY_STARTER_ACTIVITY_IDS
    assert seeder._seed_document_group.await_args_list[1].kwargs[
        "previous_identifiers"
    ] == LEGACY_STARTER_CATEGORY_KEYS
    seeder._acquire_seed_lock.assert_awaited_once_with("catalog-owner")
    seeder._release_seed_lock.assert_awaited_once_with(
        "catalog-owner",
        "test-lock",
    )


def test_mongodb_seed_recheck_skips_concurrent_winner() -> None:
    """Avoid partial or duplicate MongoDB rows after another request wins."""
    pytest.importorskip("motor")
    from backend.services.mongodb.wellness_catalog_seed import (
        MongoWellnessCatalogSeeder,
    )

    seed_locks = MagicMock()
    seed_locks.find_one = AsyncMock(return_value=None)
    seeder = MongoWellnessCatalogSeeder(
        activities_collection=MagicMock(),
        categories_collection=MagicMock(),
        tombstones_collection=MagicMock(),
        seed_locks_collection=seed_locks,
    )
    seeder.ensure_indexes = AsyncMock()
    seeder._catalog_seed_decisions = AsyncMock(
        side_effect=[
            (set(), set(), True, True),
            (
                set(STARTER_ACTIVITY_IDS),
                set(STARTER_CATEGORY_KEYS),
                False,
                False,
            ),
        ]
    )
    seeder._acquire_seed_lock = AsyncMock(return_value="test-lock")
    seeder._release_seed_lock = AsyncMock()
    seeder._seed_document_group = AsyncMock()

    asyncio.run(seeder.ensure("catalog-owner"))

    seeder._seed_document_group.assert_not_awaited()
    seeder._release_seed_lock.assert_awaited_once_with(
        "catalog-owner",
        "test-lock",
    )


@pytest.mark.parametrize(
    (
        "activity_ids",
        "category_keys",
        "tombstone_types",
        "expected_activities",
        "expected_categories",
    ),
    [
        (
            set(LEGACY_STARTER_ACTIVITY_IDS),
            set(LEGACY_STARTER_CATEGORY_KEYS),
            set(),
            set(STARTER_ACTIVITY_IDS),
            set(STARTER_CATEGORY_KEYS),
        ),
        (
            {"custom-activity"},
            {"custom-category"},
            set(),
            {"custom-activity"},
            {"custom-category"},
        ),
        (
            set(LEGACY_STARTER_ACTIVITY_IDS),
            set(LEGACY_STARTER_CATEGORY_KEYS),
            {"wellness_activity"},
            set(LEGACY_STARTER_ACTIVITY_IDS),
            set(STARTER_CATEGORY_KEYS),
        ),
    ],
)
def test_neo4j_seed_migrates_only_eligible_groups(
    activity_ids: set[str],
    category_keys: set[str],
    tombstone_types: set[str],
    expected_activities: set[str],
    expected_categories: set[str],
) -> None:
    """Migrate exact Neo4j legacy groups while preserving user-owned state.

    Args:
        activity_ids (set[str]): Initial activity identifiers.
        category_keys (set[str]): Initial category identifiers.
        tombstone_types (set[str]): Groups with deletion markers.
        expected_activities (set[str]): Expected final activity identifiers.
        expected_categories (set[str]): Expected final category identifiers.

    Returns:
        None.
    """
    transaction = _NeoTransaction(
        activity_ids,
        category_keys,
        tombstone_types,
    )
    seeder = Neo4jWellnessCatalogSeeder(MagicMock())

    seeder.seed_catalog_transaction(transaction, "catalog-owner")

    assert transaction.activity_ids == expected_activities
    assert transaction.category_keys == expected_categories
    assert "__wellness_seed_lock" in transaction.calls[0][0]


def test_neo4j_seed_uses_one_managed_transaction_for_empty_catalog() -> None:
    """Serialize concurrent Neo4j first requests before catalog inspection."""
    transaction = _NeoTransaction(set(), set())
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value

    def execute_write(callback: Any, user_id: str) -> None:
        """Invoke the managed callback against the fake transaction.

        Args:
            callback (Any): Seeder transaction callback.
            user_id (str): Owner identifier passed by the seeder.

        Returns:
            None.

        Side Effects:
            Applies callback writes to ``transaction``.
        """
        callback(transaction, user_id)

    session.execute_write.side_effect = execute_write
    seeder = Neo4jWellnessCatalogSeeder(driver)

    asyncio.run(seeder.ensure("catalog-owner"))

    session.execute_write.assert_called_once()
    assert transaction.activity_ids == STARTER_ACTIVITY_IDS
    assert transaction.category_keys == STARTER_CATEGORY_KEYS
    assert "__wellness_seed_lock" in transaction.calls[0][0]
