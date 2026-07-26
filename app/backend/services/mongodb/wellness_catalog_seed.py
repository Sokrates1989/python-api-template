"""Initialize the MongoDB wellness catalog safely for one user.

This module owns the provider-specific catalog seed workflow: unique indexes,
legacy-signature detection, tombstone-aware eligibility, distributed locking,
and failure-safe installation of the shared canonical starter documents.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic
from typing import Any, Dict, List
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.services.mongodb.common import (
    now_utc,
    starter_activities,
    starter_categories,
)
from backend.services.wellness_starter_catalog import (
    LEGACY_STARTER_ACTIVITY_IDS,
    LEGACY_STARTER_CATEGORY_KEYS,
    should_seed_starter_group,
)


class MongoWellnessCatalogSeeder:
    """Install canonical MongoDB catalog groups without reviving deletions.

    Attributes:
        activities_collection (Any): User-owned wellness activity collection.
        categories_collection (Any): User-owned activity category collection.
        tombstones_collection (Any): Deletion markers used to suppress reseeds.
        seed_locks_collection (Any): Distributed per-user initialization locks.
    """

    def __init__(
        self,
        *,
        activities_collection: Any,
        categories_collection: Any,
        tombstones_collection: Any,
        seed_locks_collection: Any,
    ) -> None:
        """Bind the seeder to its MongoDB collections.

        Args:
            activities_collection (Any): Collection containing activity rows.
            categories_collection (Any): Collection containing category rows.
            tombstones_collection (Any): Collection containing deletion markers.
            seed_locks_collection (Any): Collection used for distributed locks.

        Returns:
            None.

        Side Effects:
            Stores collection references; no database operation is performed.
        """
        self.activities_collection = activities_collection
        self.categories_collection = categories_collection
        self.tombstones_collection = tombstones_collection
        self.seed_locks_collection = seed_locks_collection
        self._indexes_initialized = False

    async def ensure_indexes(self) -> None:
        """Create catalog uniqueness and distributed-lock indexes.

        Returns:
            None.

        Raises:
            PyMongoError: When MongoDB cannot create or validate an index.

        Side Effects:
            Creates six catalog indexes and marks this seeder initialized.
        """
        if self._indexes_initialized:
            return
        await self.activities_collection.create_index(
            [("user_id", 1), ("id", 1)],
            unique=True,
            name="idx_wellness_activities_user_id_id",
        )
        await self.activities_collection.create_index(
            [("user_id", 1), ("favorite", 1)],
            name="idx_wellness_activities_user_favorite",
        )
        await self.categories_collection.create_index(
            [("user_id", 1), ("key", 1)],
            unique=True,
            name="idx_wellness_activity_categories_user_key",
        )
        await self.categories_collection.create_index(
            [("user_id", 1), ("sort_order", 1)],
            name="idx_wellness_activity_categories_user_order",
        )
        await self.seed_locks_collection.create_index(
            [("user_id", 1)],
            unique=True,
            name="idx_wellness_catalog_seed_locks_user",
        )
        await self.seed_locks_collection.create_index(
            [("expires_at", 1)],
            expireAfterSeconds=0,
            name="idx_wellness_catalog_seed_locks_expiry",
        )
        self._indexes_initialized = True

    async def _catalog_identifiers(self, user_id: str) -> tuple[set[str], set[str]]:
        """Return all persisted activity ids and category keys for one owner.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            tuple[set[str], set[str]]: Activity ids followed by category keys.

        Raises:
            PyMongoError: When either distinct-value query fails.

        Side Effects:
            Executes two owner-scoped MongoDB reads.
        """
        activity_ids = await self.activities_collection.distinct(
            "id",
            {"user_id": user_id},
        )
        category_keys = await self.categories_collection.distinct(
            "key",
            {"user_id": user_id},
        )
        return (
            {str(item) for item in activity_ids},
            {str(item) for item in category_keys},
        )

    async def _has_group_tombstones(
        self,
        user_id: str,
        entity_type: str,
    ) -> bool:
        """Return whether a catalog group has any deletion marker.

        Args:
            user_id (str): Authenticated owner identifier.
            entity_type (str): Tombstone entity type for the catalog group.

        Returns:
            bool: ``True`` when at least one matching marker exists.

        Raises:
            PyMongoError: When the tombstone lookup fails.

        Side Effects:
            Executes one owner-scoped MongoDB read.
        """
        tombstone = await self.tombstones_collection.find_one(
            {"user_id": user_id, "entity_type": entity_type},
            {"_id": 1},
        )
        return tombstone is not None

    async def _catalog_seed_decisions(
        self,
        user_id: str,
    ) -> tuple[set[str], set[str], bool, bool]:
        """Classify catalog groups for empty seed or exact-legacy replacement.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            tuple[set[str], set[str], bool, bool]: Stored activity ids, stored
            category keys, activity seed decision, and category seed decision.

        Raises:
            PyMongoError: When identifier or tombstone reads fail.

        Side Effects:
            Reads both catalog groups and tombstones for eligible signatures.
        """
        activity_ids, category_keys = await self._catalog_identifiers(user_id)
        activity_candidate = (
            not activity_ids or activity_ids == LEGACY_STARTER_ACTIVITY_IDS
        )
        category_candidate = (
            not category_keys or category_keys == LEGACY_STARTER_CATEGORY_KEYS
        )
        activity_tombstones = (
            await self._has_group_tombstones(user_id, "wellness_activity")
            if activity_candidate
            else False
        )
        category_tombstones = (
            await self._has_group_tombstones(
                user_id,
                "wellness_activity_category",
            )
            if category_candidate
            else False
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
        return activity_ids, category_keys, seed_activities, seed_categories

    async def _acquire_seed_lock(self, user_id: str) -> str:
        """Acquire the distributed MongoDB seed lock for one owner.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            str: Opaque token required to release the acquired lock.

        Raises:
            TimeoutError: When another initializer holds the lock for ten
                seconds. Abandoned locks expire after two minutes.
            PyMongoError: When the lock collection cannot be read or written.

        Side Effects:
            Creates a short-lived lock document or waits for its current owner.
        """
        token = str(uuid4())
        deadline = monotonic() + 10.0
        while monotonic() < deadline:
            expires_at = now_utc() + timedelta(minutes=2)
            try:
                document = await self.seed_locks_collection.find_one_and_update(
                    {"user_id": user_id},
                    {
                        "$setOnInsert": {
                            "user_id": user_id,
                            "token": token,
                            "expires_at": expires_at,
                        }
                    },
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
            except DuplicateKeyError:
                document = None
            if document and document.get("token") == token:
                return token
            await asyncio.sleep(0.01)
        raise TimeoutError("Timed out waiting for wellness catalog seed lock")

    async def _release_seed_lock(self, user_id: str, token: str) -> None:
        """Release a seed lock only when this seeder owns its token.

        Args:
            user_id (str): Authenticated owner identifier.
            token (str): Opaque token returned by ``_acquire_seed_lock``.

        Returns:
            None.

        Raises:
            PyMongoError: When the owned lock document cannot be deleted.

        Side Effects:
            Deletes the matching short-lived lock document.
        """
        await self.seed_locks_collection.delete_one(
            {"user_id": user_id, "token": token},
        )

    @staticmethod
    async def _upsert_seed_documents(
        collection: Any,
        documents: List[Dict[str, Any]],
        *,
        key_field: str,
    ) -> None:
        """Insert a canonical batch without overwriting concurrent rows.

        Args:
            collection (Any): Motor collection receiving the documents.
            documents (List[Dict[str, Any]]): Canonical seed documents.
            key_field (str): Owner-scoped unique identifier field.

        Returns:
            None.

        Raises:
            PyMongoError: When a write other than a duplicate-key race fails.

        Side Effects:
            Performs one idempotent upsert per canonical document.
        """
        for document in documents:
            lookup = {
                "user_id": document["user_id"],
                key_field: document[key_field],
            }
            try:
                await collection.update_one(
                    lookup,
                    {"$setOnInsert": document},
                    upsert=True,
                )
            except DuplicateKeyError:
                # The winner's canonical row satisfies this initializer.
                continue

    @classmethod
    async def _seed_document_group(
        cls,
        collection: Any,
        documents: List[Dict[str, Any]],
        *,
        key_field: str,
        previous_identifiers: set[str],
    ) -> None:
        """Install one canonical group while preserving recoverable state.

        Canonical rows are written before exact legacy rows are removed. If a
        non-concurrency insert fails, newly inserted canonical ids are removed
        so a later request still sees the original empty or legacy signature.

        Args:
            collection (Any): Motor collection receiving the documents.
            documents (List[Dict[str, Any]]): Complete canonical seed payloads.
            key_field (str): Owner-scoped unique identifier field.
            previous_identifiers (set[str]): Empty or exact legacy signature.

        Returns:
            None.

        Raises:
            Exception: When a non-duplicate database write fails.

        Side Effects:
            Inserts canonical rows, then removes only the exact legacy ids.
        """
        canonical_identifiers = [item[key_field] for item in documents]
        user_id = str(documents[0]["user_id"])
        try:
            await cls._upsert_seed_documents(
                collection,
                documents,
                key_field=key_field,
            )
        except Exception:
            await collection.delete_many(
                {
                    "user_id": user_id,
                    key_field: {"$in": canonical_identifiers},
                }
            )
            raise
        if previous_identifiers:
            await collection.delete_many(
                {
                    "user_id": user_id,
                    key_field: {"$in": list(previous_identifiers)},
                }
            )

    async def ensure(self, user_id: str) -> None:
        """Seed eligible groups under a distributed owner lock and recheck.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Raises:
            TimeoutError: When a concurrent initializer does not finish in time.
            PyMongoError: When index, lookup, lock, or seed operations fail.

        Side Effects:
            Seeds empty groups or replaces exact legacy signatures. Partial,
            custom, and tombstoned groups remain untouched.
        """
        await self.ensure_indexes()
        probe = await self._catalog_seed_decisions(user_id)
        active_lock = await self.seed_locks_collection.find_one(
            {"user_id": user_id},
            {"_id": 1},
        )
        if not probe[2] and not probe[3] and active_lock is None:
            return

        token = await self._acquire_seed_lock(user_id)
        try:
            activity_ids, category_keys, seed_activities, seed_categories = (
                await self._catalog_seed_decisions(user_id)
            )
            if seed_activities:
                await self._seed_document_group(
                    self.activities_collection,
                    starter_activities(user_id),
                    key_field="id",
                    previous_identifiers=activity_ids,
                )
            if seed_categories:
                await self._seed_document_group(
                    self.categories_collection,
                    starter_categories(user_id),
                    key_field="key",
                    previous_identifiers=category_keys,
                )
        finally:
            await self._release_seed_lock(user_id, token)
