"""SQL wellness catalog seeding and exact legacy-seed replacement.

This module owns the SQL-specific transaction, parent-row lock, tombstone
checks, ORM payload construction, and verification needed by first-request
catalog bootstrap. General wellness CRUD remains in ``wellness_service``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from sqlalchemy import and_, delete, select
from sqlalchemy.exc import IntegrityError

from backend.services.wellness_starter_catalog import (
    LEGACY_STARTER_ACTIVITY_IDS,
    LEGACY_STARTER_CATEGORY_KEYS,
    STARTER_ACTIVITY_IDS,
    STARTER_CATEGORY_KEYS,
    build_starter_activity_payloads,
    build_starter_category_payloads,
    should_seed_starter_group,
)
from models.sql.user import User
from models.sql.wellness import (
    WellnessActivity,
    WellnessActivityCategory,
    WellnessSyncTombstone,
)


class SQLWellnessCatalogSeeder:
    """Seed and narrowly upgrade one user's SQL wellness catalog."""

    def __init__(self, handler: Any) -> None:
        """Bind the seeder to a SQL database handler.

        Args:
            handler (Any): SQL handler exposing ``AsyncSessionLocal``.

        Returns:
            None.

        Side Effects:
            None.
        """
        self.handler = handler

    @staticmethod
    async def ensure_user_exists(
        session: Any,
        user_id: str,
        *,
        lock_for_update: bool = False,
    ) -> None:
        """Require the parent user and optionally lock it for catalog work.

        Args:
            session (Any): Active SQLAlchemy asynchronous session.
            user_id (str): Authenticated owner identifier.
            lock_for_update (bool): Whether to hold a row-level write lock.
                Defaults to ``False``.

        Returns:
            None: Returns only when the parent row exists.

        Raises:
            ValueError: When the application user row does not exist.

        Side Effects:
            Executes a user lookup and may hold its lock for the transaction.
        """
        statement = select(User.id).where(User.id == user_id)
        if lock_for_update:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        if result.scalar_one_or_none() is None:
            raise ValueError("User not found")

    @staticmethod
    async def _catalog_identifiers(
        session: Any,
        user_id: str,
    ) -> tuple[set[str], set[str]]:
        """Return all activity ids and category keys for one SQL owner.

        Args:
            session (Any): Active SQLAlchemy asynchronous session.
            user_id (str): Authenticated owner identifier.

        Returns:
            tuple[set[str], set[str]]: Activity ids followed by category keys.

        Side Effects:
            Executes two owner-scoped read-only catalog queries.
        """
        activity_result = await session.execute(
            select(WellnessActivity.id).where(WellnessActivity.user_id == user_id)
        )
        category_result = await session.execute(
            select(WellnessActivityCategory.key).where(
                WellnessActivityCategory.user_id == user_id
            )
        )
        return (
            {str(item) for item in activity_result.scalars().all()},
            {str(item) for item in category_result.scalars().all()},
        )

    @staticmethod
    async def _has_group_tombstones(
        session: Any,
        user_id: str,
        entity_type: str,
    ) -> bool:
        """Return whether user deletions exist for one catalog group.

        Args:
            session (Any): Active SQLAlchemy asynchronous session.
            user_id (str): Authenticated owner identifier.
            entity_type (str): Tombstone entity discriminator.

        Returns:
            bool: Whether at least one matching deletion marker exists.

        Side Effects:
            Executes one bounded tombstone lookup.
        """
        result = await session.execute(
            select(WellnessSyncTombstone.pk)
            .where(
                and_(
                    WellnessSyncTombstone.user_id == user_id,
                    WellnessSyncTombstone.entity_type == entity_type,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _seed_decisions(
        self,
        session: Any,
        user_id: str,
    ) -> tuple[set[str], set[str], bool, bool]:
        """Classify SQL groups for empty seed or exact legacy replacement.

        Args:
            session (Any): Active SQLAlchemy asynchronous session.
            user_id (str): Authenticated owner identifier.

        Returns:
            tuple[set[str], set[str], bool, bool]: Stored identifiers followed
            by activity/category seed decisions.

        Side Effects:
            Reads catalog identifiers and candidate-group tombstones.
        """
        activity_ids, category_keys = await self._catalog_identifiers(
            session,
            user_id,
        )
        activity_candidate = (
            not activity_ids or activity_ids == LEGACY_STARTER_ACTIVITY_IDS
        )
        category_candidate = (
            not category_keys or category_keys == LEGACY_STARTER_CATEGORY_KEYS
        )
        activity_tombstones = activity_candidate and await self._has_group_tombstones(
            session,
            user_id,
            "wellness_activity",
        )
        category_tombstones = category_candidate and await self._has_group_tombstones(
            session,
            user_id,
            "wellness_activity_category",
        )
        return (
            activity_ids,
            category_keys,
            should_seed_starter_group(
                activity_ids,
                legacy_identifiers=LEGACY_STARTER_ACTIVITY_IDS,
                has_tombstones=activity_tombstones,
            ),
            should_seed_starter_group(
                category_keys,
                legacy_identifiers=LEGACY_STARTER_CATEGORY_KEYS,
                has_tombstones=category_tombstones,
            ),
        )

    @staticmethod
    def starter_activities(user_id: str) -> List[WellnessActivity]:
        """Build canonical detached SQL activity rows for one owner.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            List[WellnessActivity]: Detached ORM rows ready for insertion.

        Side Effects:
            Reads the current time once for consistent seed timestamps.
        """
        now = datetime.now(timezone.utc).replace(
            hour=9,
            minute=0,
            second=0,
            microsecond=0,
        )
        activities: List[WellnessActivity] = []
        for item in build_starter_activity_payloads(user_id):
            activity = WellnessActivity(
                user_id=user_id,
                id=item["id"],
                icon_key=item["icon_key"],
                title_key=item["title_key"],
                title=item["title"],
                summary_key=item["summary_key"],
                summary=item["summary"],
                activity_reminder=item["activity_reminder"],
                duration_minutes=item["duration_minutes"],
                favorite=item["favorite"],
                harmful=item["harmful"],
                sort_order=item["sort_order"],
                energy_impact=item["energy_impact"],
                created_at=now,
                updated_at=now,
            )
            activity.category_keys = list(item["category_keys"])
            activity.tags = list(item["tags"])
            activities.append(activity)
        return activities

    @staticmethod
    def starter_categories(user_id: str) -> List[WellnessActivityCategory]:
        """Build canonical detached SQL category rows for one owner.

        Args:
            user_id (str): Owner identifier applied to every category.

        Returns:
            List[WellnessActivityCategory]: Ordered category rows.

        Side Effects:
            None.
        """
        return [
            WellnessActivityCategory(
                user_id=user_id,
                key=item["key"],
                title_key=item["title_key"],
                title=item["title"],
                description_key=item["description_key"],
                description=item["description"],
                icon_key=item["icon_key"],
                sort_order=item["sort_order"],
            )
            for item in build_starter_category_payloads(user_id)
        ]

    async def ensure(self, user_id: str) -> None:
        """Seed empty groups or replace exact obsolete groups atomically.

        Args:
            user_id (str): Authenticated owner identifier.

        Returns:
            None.

        Raises:
            ValueError: When the application user row does not exist.
            RuntimeError: When a requested seed group fails verification.
            SQLAlchemyError: When catalog reads or writes fail.

        Side Effects:
            May replace eligible groups and commit one SQL transaction.
        """
        async with self.handler.AsyncSessionLocal() as probe_session:
            await self.ensure_user_exists(probe_session, user_id)
            probe = await self._seed_decisions(probe_session, user_id)
        if not probe[2] and not probe[3]:
            return

        async with self.handler.AsyncSessionLocal() as session:
            await self.ensure_user_exists(session, user_id, lock_for_update=True)
            activity_ids, category_keys, seed_activities, seed_categories = (
                await self._seed_decisions(session, user_id)
            )
            if seed_activities:
                if activity_ids:
                    await session.execute(
                        delete(WellnessActivity).where(
                            WellnessActivity.user_id == user_id
                        )
                    )
                session.add_all(self.starter_activities(user_id))
            if seed_categories:
                if category_keys:
                    await session.execute(
                        delete(WellnessActivityCategory).where(
                            WellnessActivityCategory.user_id == user_id
                        )
                    )
                session.add_all(self.starter_categories(user_id))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

        async with self.handler.AsyncSessionLocal() as verification_session:
            await self.ensure_user_exists(verification_session, user_id)
            verified_activities, verified_categories = await self._catalog_identifiers(
                verification_session,
                user_id,
            )
        if seed_activities and verified_activities != STARTER_ACTIVITY_IDS:
            raise RuntimeError("Wellness starter activities could not be fully seeded")
        if seed_categories and verified_categories != STARTER_CATEGORY_KEYS:
            raise RuntimeError("Wellness starter categories could not be fully seeded")
