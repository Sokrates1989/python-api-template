"""Neo4j wellness catalog seeding and exact legacy-seed replacement.

This module owns the provider-specific managed transaction used to serialize
first-request catalog initialization. It seeds only empty catalog groups or
groups containing the exact obsolete starter identifiers, and it preserves
groups that have deletion tombstones or any custom/partial contents.
"""

from __future__ import annotations

from typing import Any

from backend.services.neo4j.common import starter_activities, starter_categories
from backend.services.wellness_starter_catalog import (
    LEGACY_STARTER_ACTIVITY_IDS,
    LEGACY_STARTER_CATEGORY_KEYS,
    should_seed_starter_group,
)


class Neo4jWellnessCatalogSeeder:
    """Atomically initialize or narrowly upgrade one Neo4j catalog."""

    def __init__(self, driver: Any) -> None:
        """Bind the seeder to a Neo4j driver.

        Args:
            driver (Any): Neo4j driver exposing synchronous sessions and
                managed write transactions.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.driver = driver

    @staticmethod
    def _catalog_identifiers(
        transaction: Any,
        user_id: str,
    ) -> tuple[set[str], set[str]]:
        """Read complete activity and category identifier sets.

        Args:
            transaction (Any): Active Neo4j managed transaction.
            user_id (str): Authenticated owner identifier.

        Returns:
            tuple[set[str], set[str]]: Activity ids followed by category keys.

        Side Effects:
            Executes two owner-scoped read queries in the active transaction.
        """
        activity_record = transaction.run(
            "MATCH (a:WellnessActivity {user_id: $user_id}) "
            "RETURN collect(a.id) AS identifiers",
            user_id=user_id,
        ).single()
        category_record = transaction.run(
            "MATCH (c:WellnessActivityCategory {user_id: $user_id}) "
            "RETURN collect(c.key) AS identifiers",
            user_id=user_id,
        ).single()
        return (
            {str(item) for item in activity_record["identifiers"]},
            {str(item) for item in category_record["identifiers"]},
        )

    @staticmethod
    def _has_group_tombstones(
        transaction: Any,
        user_id: str,
        entity_type: str,
    ) -> bool:
        """Return whether one catalog group has deletion markers.

        Args:
            transaction (Any): Active Neo4j managed transaction.
            user_id (str): Authenticated owner identifier.
            entity_type (str): Tombstone entity discriminator.

        Returns:
            bool: Whether at least one matching tombstone exists.

        Side Effects:
            Executes one bounded owner-scoped tombstone query.
        """
        record = transaction.run(
            "MATCH (t:WellnessSyncTombstone {user_id: $user_id, "
            "entity_type: $entity_type}) RETURN count(t) > 0 AS present",
            user_id=user_id,
            entity_type=entity_type,
        ).single()
        return bool(record["present"])

    @staticmethod
    def _replace_activities(transaction: Any, user_id: str) -> None:
        """Replace the eligible activity group with canonical nodes.

        Args:
            transaction (Any): Active Neo4j managed transaction.
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Side Effects:
            Deletes the eligible group and creates all canonical activities in
            the same transaction, so failures roll back both operations.
        """
        transaction.run(
            "MATCH (a:WellnessActivity {user_id: $user_id}) DETACH DELETE a",
            user_id=user_id,
        ).consume()
        transaction.run(
            "UNWIND $items AS props CREATE (a:WellnessActivity) SET a = props",
            items=starter_activities(user_id),
        ).consume()

    @staticmethod
    def _replace_categories(transaction: Any, user_id: str) -> None:
        """Replace the eligible category group with canonical nodes.

        Args:
            transaction (Any): Active Neo4j managed transaction.
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Side Effects:
            Deletes the eligible group and creates all canonical categories in
            the same transaction, so failures roll back both operations.
        """
        transaction.run(
            "MATCH (c:WellnessActivityCategory {user_id: $user_id}) "
            "DETACH DELETE c",
            user_id=user_id,
        ).consume()
        transaction.run(
            "UNWIND $items AS props "
            "CREATE (c:WellnessActivityCategory) SET c = props",
            items=starter_categories(user_id),
        ).consume()

    def seed_catalog_transaction(self, transaction: Any, user_id: str) -> None:
        """Seed or upgrade eligible groups in one serialized transaction.

        The temporary parent-node write acquires an exclusive lock until the
        managed transaction finishes. A concurrent first request therefore
        evaluates its seed decisions only after the winning write commits.

        Args:
            transaction (Any): Neo4j managed write transaction.
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Raises:
            ValueError: When the parent user node does not exist.
            Neo4jError: When a catalog read or write fails.

        Side Effects:
            May atomically replace eligible activity and category groups.
        """
        lock_record = transaction.run(
            "MATCH (u:User {id: $user_id}) "
            "SET u.__wellness_seed_lock = true "
            "REMOVE u.__wellness_seed_lock "
            "RETURN u.id AS user_id",
            user_id=user_id,
        ).single()
        if lock_record is None:
            raise ValueError("User not found")

        activity_ids, category_keys = self._catalog_identifiers(
            transaction,
            user_id,
        )
        activity_candidate = (
            not activity_ids or activity_ids == LEGACY_STARTER_ACTIVITY_IDS
        )
        category_candidate = (
            not category_keys or category_keys == LEGACY_STARTER_CATEGORY_KEYS
        )

        # Tombstones are queried only for groups otherwise eligible to change.
        activity_tombstones = activity_candidate and self._has_group_tombstones(
            transaction,
            user_id,
            "wellness_activity",
        )
        category_tombstones = category_candidate and self._has_group_tombstones(
            transaction,
            user_id,
            "wellness_activity_category",
        )
        seed_activities = should_seed_starter_group(
            activity_ids,
            legacy_identifiers=LEGACY_STARTER_ACTIVITY_IDS,
            has_tombstones=activity_tombstones,
        )
        seed_categories = should_seed_starter_group(
            category_keys,
            legacy_identifiers=LEGACY_STARTER_CATEGORY_KEYS,
            has_tombstones=category_tombstones,
        )

        if seed_activities:
            self._replace_activities(transaction, user_id)
        if seed_categories:
            self._replace_categories(transaction, user_id)

    async def ensure(self, user_id: str) -> None:
        """Run the serialized Neo4j catalog seed workflow.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Raises:
            ValueError: When the parent user node does not exist.
            Neo4jError: When the managed transaction fails.

        Side Effects:
            Opens a session and may atomically initialize or upgrade catalog
            groups.
        """
        with self.driver.session() as session:
            session.execute_write(self.seed_catalog_transaction, user_id)
