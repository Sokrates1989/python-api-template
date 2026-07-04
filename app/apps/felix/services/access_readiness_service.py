"""Felix access-readiness persistence service.

The service stores setup completion, legal acceptance, and setupPayload feature
preferences globally for authenticated users. It mirrors the PWA
AccessReadinessRepository contract while staying provider-aware for MongoDB,
SQL, and Neo4j deployments.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from sqlalchemy import text

from apps.felix.services.access_readiness_state import (
    normalize_access_readiness_patch,
    normalize_access_readiness_state,
)
from backend.database import get_database_handler


class FelixAccessReadinessService:
    """Persist and retrieve Felix access-readiness state for one user."""

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

    async def get_access_readiness_state(self, user_id: str) -> Dict[str, Any]:
        """Return the user's persisted access-readiness state.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Success or error payload containing the canonical
            PWA-compatible readiness state.

        Side Effects:
            Creates a default readiness row/document/node when none exists.
        """
        try:
            if self._uses_mongodb_handler():
                state = await self._get_mongodb_state(user_id)
            elif self._uses_sql_handler():
                state = await self._get_sql_state(user_id)
            elif self._uses_neo4j_handler():
                state = await self._get_neo4j_state(user_id)
            else:
                return {
                    "status": "error",
                    "message": "Unsupported database type for Felix access readiness",
                    "data": None,
                }
            return {"status": "success", "data": state}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading Felix access readiness: {str(exc)}", "data": None}

    async def update_access_readiness_state(self, user_id: str, patch: Mapping[str, Any]) -> Dict[str, Any]:
        """Patch the user's persisted access-readiness state.

        Args:
            user_id (str): Authenticated user identifier.
            patch (Mapping[str, Any]): Partial readiness update using the PWA
                camelCase contract.

        Returns:
            Dict[str, Any]: Success or error payload containing the updated
            readiness state.

        Side Effects:
            Writes the merged readiness state to the active database backend.
        """
        try:
            current_result = await self.get_access_readiness_state(user_id)
            if current_result.get("status") != "success":
                return current_result
            next_state = normalize_access_readiness_patch(patch, current_state=current_result.get("data"))
            if self._uses_mongodb_handler():
                state = await self._set_mongodb_state(user_id, next_state)
            elif self._uses_sql_handler():
                state = await self._set_sql_state(user_id, next_state)
            elif self._uses_neo4j_handler():
                state = await self._set_neo4j_state(user_id, next_state)
            else:
                return {
                    "status": "error",
                    "message": "Unsupported database type for Felix access readiness",
                    "data": None,
                }
            return {"status": "success", "message": "Felix access readiness updated successfully", "data": state}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating Felix access readiness: {str(exc)}", "data": None}

    def _handler_type_name(self) -> str:
        """Return the active database handler class name.

        Args:
            None.

        Returns:
            str: Runtime class name for the configured database handler.

        Side Effects:
            None.
        """
        return type(self.handler).__name__

    def _uses_mongodb_handler(self) -> bool:
        """Return whether the active handler is MongoDB-backed.

        Args:
            None.

        Returns:
            bool: True when the runtime handler is ``MongoDBHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "MongoDBHandler"

    def _uses_sql_handler(self) -> bool:
        """Return whether the active handler is SQL-backed.

        Args:
            None.

        Returns:
            bool: True when the runtime handler is ``SQLHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "SQLHandler"

    def _uses_neo4j_handler(self) -> bool:
        """Return whether the active handler is Neo4j-backed.

        Args:
            None.

        Returns:
            bool: True when the runtime handler is ``Neo4jHandler``.

        Side Effects:
            None.
        """
        return self._handler_type_name() == "Neo4jHandler"

    async def _get_mongodb_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the MongoDB access-readiness document.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical readiness dictionary.

        Side Effects:
            Creates indexes and inserts default state when absent.
        """
        collection = self.handler.database["felix_access_readiness"]
        await collection.create_index([("user_id", 1)], unique=True, name="idx_felix_access_readiness_user_id")
        document = await collection.find_one({"user_id": user_id}, {"_id": 0})
        if document is None:
            now = _iso_now()
            document = {"user_id": user_id, **normalize_access_readiness_state(None), "created_at": now, "updated_at": now}
            await collection.insert_one(document)
        return normalize_access_readiness_state(document)

    async def _set_mongodb_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist access-readiness state to MongoDB.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical readiness state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Upserts the MongoDB readiness document.
        """
        collection = self.handler.database["felix_access_readiness"]
        now = _iso_now()
        payload = {**normalize_access_readiness_state(state), "updated_at": now}
        await collection.update_one(
            {"user_id": user_id},
            {"$set": payload, "$setOnInsert": {"user_id": user_id, "created_at": now}},
            upsert=True,
        )
        return await self._get_mongodb_state(user_id)

    async def _get_sql_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the SQL access-readiness row.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical readiness dictionary.

        Side Effects:
            Inserts a default SQL row when absent.
        """
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT setup_completed, setup_completed_at,
                           legal_accepted_version, legal_accepted_at,
                           setup_payload
                    FROM felix_access_readiness
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            row = result.mappings().one_or_none()
            if row is None:
                state = normalize_access_readiness_state(None)
                await self._insert_sql_state(session, user_id, state)
                await session.commit()
                return state
            return _state_from_sql_row(row)

    async def _set_sql_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist access-readiness state to SQL storage.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical readiness state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Inserts or updates the SQL readiness row.
        """
        normalized = normalize_access_readiness_state(state)
        async with self.handler.AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT pk FROM felix_access_readiness WHERE user_id = :user_id"),
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
        """Insert a SQL access-readiness row.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical readiness state.

        Returns:
            None.

        Side Effects:
            Adds one row to ``felix_access_readiness``.
        """
        await session.execute(
            text(
                """
                INSERT INTO felix_access_readiness (
                    user_id, setup_completed, setup_completed_at,
                    legal_accepted_version, legal_accepted_at, setup_payload
                ) VALUES (
                    :user_id, :setup_completed, :setup_completed_at,
                    :legal_accepted_version, :legal_accepted_at, :setup_payload
                )
                """
            ),
            _sql_params(user_id, state),
        )

    async def _update_sql_state_row(self, session: Any, user_id: str, state: Mapping[str, Any]) -> None:
        """Update a SQL access-readiness row.

        Args:
            session (Any): Active SQLAlchemy async session.
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical readiness state.

        Returns:
            None.

        Side Effects:
            Updates one row in ``felix_access_readiness``.
        """
        await session.execute(
            text(
                """
                UPDATE felix_access_readiness
                SET setup_completed = :setup_completed,
                    setup_completed_at = :setup_completed_at,
                    legal_accepted_version = :legal_accepted_version,
                    legal_accepted_at = :legal_accepted_at,
                    setup_payload = :setup_payload,
                    updated_at = :updated_at
                WHERE user_id = :user_id
                """
            ),
            _sql_params(user_id, state),
        )

    async def _get_neo4j_state(self, user_id: str) -> Dict[str, Any]:
        """Load or create the Neo4j access-readiness node.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Canonical readiness dictionary.

        Side Effects:
            Creates a Neo4j index and default node when absent.
        """
        self._ensure_neo4j_index()
        with self.handler.driver.session() as session:
            record = session.run(
                """
                MERGE (r:FelixAccessReadiness {user_id: $user_id})
                ON CREATE SET r.created_at = $now,
                              r.updated_at = $now,
                              r.setupCompleted = false,
                              r.setupCompletedAt = null,
                              r.legalAcceptedVersion = null,
                              r.legalAcceptedAt = null,
                              r.setupPayload = null
                RETURN r AS state
                """,
                user_id=user_id,
                now=_iso_now(),
            ).single()
        return _state_from_neo4j_properties(dict(record["state"]))

    async def _set_neo4j_state(self, user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        """Persist access-readiness state to Neo4j.

        Args:
            user_id (str): Authenticated user identifier.
            state (Mapping[str, Any]): Canonical readiness state.

        Returns:
            Dict[str, Any]: Canonical state after persistence.

        Side Effects:
            Updates or creates one ``FelixAccessReadiness`` node.
        """
        normalized = normalize_access_readiness_state(state)
        with self.handler.driver.session() as session:
            session.run(
                """
                MERGE (r:FelixAccessReadiness {user_id: $user_id})
                ON CREATE SET r.created_at = $now
                SET r.updated_at = $now,
                    r.setupCompleted = $setup_completed,
                    r.setupCompletedAt = $setup_completed_at,
                    r.legalAcceptedVersion = $legal_accepted_version,
                    r.legalAcceptedAt = $legal_accepted_at,
                    r.setupPayload = $setup_payload
                """,
                user_id=user_id,
                now=_iso_now(),
                setup_completed=normalized["setupCompleted"],
                setup_completed_at=normalized["setupCompletedAt"],
                legal_accepted_version=normalized["legalAcceptedVersion"],
                legal_accepted_at=normalized["legalAcceptedAt"],
                setup_payload=_encode_json_or_none(normalized["setupPayload"]),
            )
        return await self._get_neo4j_state(user_id)

    def _ensure_neo4j_index(self) -> None:
        """Ensure the Neo4j readiness lookup index exists.

        Args:
            None.

        Returns:
            None.

        Side Effects:
            Creates an index in Neo4j when missing.
        """
        with self.handler.driver.session() as session:
            session.run(
                "CREATE INDEX felix_access_readiness_user_id IF NOT EXISTS "
                "FOR (n:FelixAccessReadiness) ON (n.user_id)"
            )


def _sql_params(user_id: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    """Build SQL parameters for one access-readiness write.

    Args:
        user_id (str): Authenticated user identifier.
        state (Mapping[str, Any]): Canonical readiness state.

    Returns:
        Dict[str, Any]: SQL parameter mapping.

    Side Effects:
        None.
    """
    normalized = normalize_access_readiness_state(state)
    return {
        "user_id": user_id,
        "setup_completed": normalized["setupCompleted"],
        "setup_completed_at": _datetime_or_none(normalized["setupCompletedAt"]),
        "legal_accepted_version": normalized["legalAcceptedVersion"],
        "legal_accepted_at": _datetime_or_none(normalized["legalAcceptedAt"]),
        "setup_payload": _encode_json_or_none(normalized["setupPayload"]),
        "updated_at": datetime.now(timezone.utc),
    }


def _state_from_sql_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a SQL access-readiness row to canonical state.

    Args:
        row (Mapping[str, Any]): SQLAlchemy row mapping.

    Returns:
        Dict[str, Any]: Canonical readiness dictionary.

    Side Effects:
        None.
    """
    return normalize_access_readiness_state(
        {
            "setup_completed": row.get("setup_completed"),
            "setup_completed_at": row.get("setup_completed_at"),
            "legal_accepted_version": row.get("legal_accepted_version"),
            "legal_accepted_at": row.get("legal_accepted_at"),
            "setup_payload": _decode_json(row.get("setup_payload"), None),
        }
    )


def _state_from_neo4j_properties(properties: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert Neo4j node properties to canonical readiness state.

    Args:
        properties (Mapping[str, Any]): Neo4j node property mapping.

    Returns:
        Dict[str, Any]: Canonical readiness dictionary.

    Side Effects:
        None.
    """
    return normalize_access_readiness_state(
        {
            **dict(properties),
            "setupPayload": _decode_json(properties.get("setupPayload"), None),
        }
    )


def _encode_json_or_none(value: Any) -> Optional[str]:
    """Encode a JSON-compatible value or preserve null.

    Args:
        value (Any): JSON-compatible payload.

    Returns:
        Optional[str]: Compact JSON text or null.

    Side Effects:
        None.
    """
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))


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


def _datetime_or_none(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp for SQL DateTime columns.

    Args:
        value (Any): ISO timestamp text or datetime.

    Returns:
        Optional[datetime]: Parsed timezone-aware datetime or null.

    Side Effects:
        None.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
