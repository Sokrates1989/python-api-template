"""Felix rewards persistence service.

The service owns app-specific reward state such as unlocked catalog purchases,
spent suns, streak-saver stock, and reward media preferences. It talks directly
to the active database handler because the state is Felix-specific and should
not become part of the shared template wellness contract.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from sqlalchemy import text

from apps.felix.services.rewards_state import normalize_rewards_patch, normalize_rewards_state
from backend.database import get_database_handler


class FelixRewardsService:
    """Persist and retrieve Felix rewards state for the authenticated user."""

    def __init__(self) -> None:
        """Bind the service to the currently configured database handler.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Resolves the global database handler for provider-specific storage.
        """
        self.handler = get_database_handler()

    async def get_rewards_state(self, user_id: str) -> Dict[str, Any]:
        """Return the user's persisted rewards state.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Success or error payload containing canonical Felix
            rewards state.

        Side Effects:
            Creates a default rewards-state row/document/node when none exists.
        """
        try:
            if self._uses_mongodb_handler():
                state = await self._get_mongodb_state(user_id)
            elif self._uses_sql_handler():
                state = await self._get_sql_state(user_id)
            elif self._uses_neo4j_handler():
                state = await self._get_neo4j_state(user_id)
            else:
                return {"status": "error", "message": "Unsupported database type for Felix rewards", "data": None}
            return {"status": "success", "data": state}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading Felix rewards: {str(exc)}", "data": None}

    async def update_rewards_state(self, user_id: str, patch: Mapping[str, Any]) -> Dict[str, Any]:
        """Patch the user's persisted rewards state.

        Args:
            user_id (str): Authenticated user identifier.
            patch (Mapping[str, Any]): Partial rewards-state patch.

        Returns:
            Dict[str, Any]: Success or error payload containing updated rewards
            state.

        Side Effects:
            Writes the merged rewards state to the active database backend.
        """
        try:
            current_result = await self.get_rewards_state(user_id)
            if current_result.get("status") != "success":
                return current_result
            next_state = normalize_rewards_patch(patch, current_state=current_result.get("data"))
            if self._uses_mongodb_handler():
                state = await self._set_mongodb_state(user_id, next_state)
            elif self._uses_sql_handler():
                state = await self._set_sql_state(user_id, next_state)
            elif self._uses_neo4j_handler():
                state = await self._set_neo4j_state(user_id, next_state)
            else:
                return {"status": "error", "message": "Unsupported database type for Felix rewards", "data": None}
            return {"status": "success", "message": "Felix rewards updated successfully", "data": state}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating Felix rewards: {str(exc)}", "data": None}

    def _handler_type_name(self) -> str:
        """Return the active database handler class name.

        Args:
            None.

        Returns:
            str: Runtime class name for the configured database handler.

        Side Effects:
            None.

        Note:
            This deliberately avoids importing optional provider handlers at
            module import time. Felix runs on PostgreSQL, so importing the
            Neo4j handler here would require the optional ``neo4j`` package
            before the SQL path is even selected.
        """
        return type(self.handler).__name__

    def _uses_mongodb_handler(self) -> bool:
        """Return whether the active handler is MongoDB-backed.

        Args:
            None.

        Returns:
            bool: ``True`` when the runtime handler is ``MongoDBHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "MongoDBHandler"

    def _uses_sql_handler(self) -> bool:
        """Return whether the active handler is SQL-backed.

        Args:
            None.

        Returns:
            bool: ``True`` when the runtime handler is ``SQLHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "SQLHandler"

    def _uses_neo4j_handler(self) -> bool:
        """Return whether the active handler is Neo4j-backed.

        Args:
            None.

        Returns:
            bool: ``True`` when the runtime handler is ``Neo4jHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "Neo4jHandler"

    async def _get_mongodb_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the MongoDB rewards-state document.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical rewards-state dictionary.

        Side Effects:
            Creates indexes and inserts default state when absent.
        """
        collection = self.handler.database["felix_rewards_state"]
        await collection.create_index([("user_id", 1)], unique=True, name="idx_felix_rewards_user_id")
        document = await collection.find_one({"user_id": user_id}, {"_id": 0})
        if document is None:
            now = _iso_now()
            document = {"user_id": user_id, **normalize_rewards_state(None), "created_at": now, "updated_at": now}
            await collection.insert_one(document)
        return normalize_rewards_state(document)

    async def _set_mongodb_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist rewards state to MongoDB.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical rewards state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Upserts the MongoDB rewards-state document.
        """
        collection = self.handler.database["felix_rewards_state"]
        now = _iso_now()
        payload = {**normalize_rewards_state(state), "updated_at": now}
        await collection.update_one(
            {"user_id": user_id},
            {"$set": payload, "$setOnInsert": {"user_id": user_id, "created_at": now}},
            upsert=True,
        )
        return await self._get_mongodb_state(user_id)

    async def _get_sql_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the SQL rewards-state row.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical rewards-state dictionary.

        Side Effects:
            Inserts a default SQL row when absent.
        """
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT purchases, spent_suns, last_seen_earned_suns,
                           last_celebrated_earned_suns, streak_savers_available,
                           streak_savers_max, streak_saver_used_day_keys,
                           last_streak_saver_grant_day_key, media_preferences
                    FROM felix_rewards_state
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            row = result.mappings().one_or_none()
            if row is None:
                state = normalize_rewards_state(None)
                await self._insert_sql_state(session, user_id, state)
                await session.commit()
                return state
            return _state_from_sql_row(row)

    async def _set_sql_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist rewards state to SQL storage.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical rewards state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Inserts or updates the SQL rewards-state row.
        """
        normalized = normalize_rewards_state(state)
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT pk FROM felix_rewards_state WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            exists = result.scalar_one_or_none() is not None
            if exists:
                await self._update_sql_state_row(session, user_id, normalized)
            else:
                await self._insert_sql_state(session, user_id, normalized)
            await session.commit()
        return await self._get_sql_state(user_id)

    async def _insert_sql_state(self, session: Any, user_id: str, state: Mapping[str, Any]) -> None:
        """Insert a SQL rewards-state row.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical rewards state.

        Returns:
            None.

        Side Effects:
            Adds one row to ``felix_rewards_state``.
        """
        await session.execute(
            text(
                """
                INSERT INTO felix_rewards_state (
                    user_id, purchases, spent_suns, last_seen_earned_suns,
                    last_celebrated_earned_suns, streak_savers_available,
                    streak_savers_max, streak_saver_used_day_keys,
                    last_streak_saver_grant_day_key, media_preferences
                ) VALUES (
                    :user_id, :purchases, :spent_suns, :last_seen_earned_suns,
                    :last_celebrated_earned_suns, :streak_savers_available,
                    :streak_savers_max, :streak_saver_used_day_keys,
                    :last_streak_saver_grant_day_key, :media_preferences
                )
                """
            ),
            _sql_params(user_id, state),
        )

    async def _update_sql_state_row(self, session: Any, user_id: str, state: Mapping[str, Any]) -> None:
        """Update a SQL rewards-state row.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical rewards state.

        Returns:
            None.

        Side Effects:
            Updates one row in ``felix_rewards_state``.
        """
        await session.execute(
            text(
                """
                UPDATE felix_rewards_state
                SET purchases = :purchases,
                    spent_suns = :spent_suns,
                    last_seen_earned_suns = :last_seen_earned_suns,
                    last_celebrated_earned_suns = :last_celebrated_earned_suns,
                    streak_savers_available = :streak_savers_available,
                    streak_savers_max = :streak_savers_max,
                    streak_saver_used_day_keys = :streak_saver_used_day_keys,
                    last_streak_saver_grant_day_key = :last_streak_saver_grant_day_key,
                    media_preferences = :media_preferences,
                    updated_at = :updated_at
                WHERE user_id = :user_id
                """
            ),
            _sql_params(user_id, state),
        )

    async def _get_neo4j_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the Neo4j rewards-state node.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical rewards-state dictionary.

        Side Effects:
            Creates a Neo4j index and default node when absent.
        """
        self._ensure_neo4j_index()
        with self.handler.driver.session() as session:
            record = session.run(
                """
                MERGE (r:FelixRewardsState {user_id: $user_id})
                ON CREATE SET r.created_at = $now,
                              r.updated_at = $now,
                              r.purchases = [],
                              r.spent_suns = 0,
                              r.last_seen_earned_suns = 0,
                              r.last_celebrated_earned_suns = 0,
                              r.streak_savers_available = 0,
                              r.streak_savers_max = 1,
                              r.streak_saver_used_day_keys = [],
                              r.last_streak_saver_grant_day_key = null,
                              r.media_preferences = $media_preferences
                RETURN r AS state
                """,
                user_id=user_id,
                now=_iso_now(),
                media_preferences=json.dumps(normalize_rewards_state(None)["media_preferences"], separators=(",", ":")),
            ).single()
        return _state_from_neo4j_properties(dict(record["state"]))

    async def _set_neo4j_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist rewards state to Neo4j.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical rewards state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Updates or creates one ``FelixRewardsState`` node.
        """
        normalized = normalize_rewards_state(state)
        with self.handler.driver.session() as session:
            session.run(
                """
                MERGE (r:FelixRewardsState {user_id: $user_id})
                ON CREATE SET r.created_at = $now
                SET r.updated_at = $now,
                    r.purchases = $purchases,
                    r.spent_suns = $spent_suns,
                    r.last_seen_earned_suns = $last_seen_earned_suns,
                    r.last_celebrated_earned_suns = $last_celebrated_earned_suns,
                    r.streak_savers_available = $streak_savers_available,
                    r.streak_savers_max = $streak_savers_max,
                    r.streak_saver_used_day_keys = $streak_saver_used_day_keys,
                    r.last_streak_saver_grant_day_key = $last_streak_saver_grant_day_key,
                    r.media_preferences = $media_preferences
                """,
                user_id=user_id,
                now=_iso_now(),
                purchases=normalized["purchases"],
                spent_suns=normalized["spent_suns"],
                last_seen_earned_suns=normalized["last_seen_earned_suns"],
                last_celebrated_earned_suns=normalized["last_celebrated_earned_suns"],
                streak_savers_available=normalized["streak_savers_available"],
                streak_savers_max=normalized["streak_savers_max"],
                streak_saver_used_day_keys=normalized["streak_saver_used_day_keys"],
                last_streak_saver_grant_day_key=normalized["last_streak_saver_grant_day_key"],
                media_preferences=json.dumps(normalized["media_preferences"], separators=(",", ":")),
            )
        return await self._get_neo4j_state(user_id)

    def _ensure_neo4j_index(self) -> None:
        """Ensure the Neo4j rewards-state lookup index exists.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Creates an index in Neo4j when missing.
        """
        with self.handler.driver.session() as session:
            session.run(
                "CREATE INDEX felix_rewards_state_user_id IF NOT EXISTS "
                "FOR (n:FelixRewardsState) ON (n.user_id)"
            )


def _sql_params(user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    """Build SQL parameters for one rewards-state write.

    Args:
        user_id (str): Authenticated user identifier.
        state (Mapping[str, Any]): Canonical rewards state.

    Returns:
        Dict[str, Any]: SQL parameter mapping.

    Side Effects:
        None.
    """
    normalized = normalize_rewards_state(state)
    return {
        "user_id": user_id,
        "purchases": json.dumps(normalized["purchases"], separators=(",", ":")),
        "spent_suns": normalized["spent_suns"],
        "last_seen_earned_suns": normalized["last_seen_earned_suns"],
        "last_celebrated_earned_suns": normalized["last_celebrated_earned_suns"],
        "streak_savers_available": normalized["streak_savers_available"],
        "streak_savers_max": normalized["streak_savers_max"],
        "streak_saver_used_day_keys": json.dumps(normalized["streak_saver_used_day_keys"], separators=(",", ":")),
        "last_streak_saver_grant_day_key": normalized["last_streak_saver_grant_day_key"],
        "media_preferences": json.dumps(normalized["media_preferences"], separators=(",", ":")),
        "updated_at": datetime.now(timezone.utc),
    }


def _state_from_sql_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a SQL rewards-state row to canonical state.

    Args:
        row (Mapping[str, Any]): SQLAlchemy row mapping.

    Returns:
        Dict[str, Any]: Canonical rewards-state dictionary.

    Side Effects:
        None.
    """
    return normalize_rewards_state(
        {
            "purchases": _decode_json(row.get("purchases"), []),
            "spent_suns": row.get("spent_suns"),
            "last_seen_earned_suns": row.get("last_seen_earned_suns"),
            "last_celebrated_earned_suns": row.get("last_celebrated_earned_suns"),
            "streak_savers_available": row.get("streak_savers_available"),
            "streak_savers_max": row.get("streak_savers_max"),
            "streak_saver_used_day_keys": _decode_json(row.get("streak_saver_used_day_keys"), []),
            "last_streak_saver_grant_day_key": row.get("last_streak_saver_grant_day_key"),
            "media_preferences": _decode_json(row.get("media_preferences"), {}),
        }
    )


def _state_from_neo4j_properties(properties: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert Neo4j node properties to canonical rewards state.

    Args:
        properties (Mapping[str, Any]): Neo4j node property mapping.

    Returns:
        Dict[str, Any]: Canonical rewards-state dictionary.

    Side Effects:
        None.
    """
    return normalize_rewards_state(
        {
            **dict(properties),
            "media_preferences": _decode_json(properties.get("media_preferences"), {}),
        }
    )


def _decode_json(value: Any, fallback: Any) -> Any:
    """Decode a JSON string with a fallback.

    Args:
        value (Any): Raw JSON value.
        fallback (Any): Value returned when decoding fails.

    Returns:
        Any: Decoded JSON value or fallback.

    Side Effects:
        None.
    """
    if not isinstance(value, str):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _iso_now() -> str:
    """Return the current UTC timestamp as ISO text.

    Args:
        None.

    Returns:
        str: UTC ISO-8601 timestamp.

    Side Effects:
        None.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
