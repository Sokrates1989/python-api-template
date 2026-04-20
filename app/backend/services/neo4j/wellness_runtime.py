"""Runtime implementation of the Neo4j wellness service.

This module hosts the concrete Neo4j wellness logic while keeping shared data
shaping helpers in smaller dedicated modules to satisfy repository size and
maintainability rules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.database import get_database_handler
from backend.database.neo4j_handler import Neo4jHandler
from backend.services.neo4j.common import (
    build_activity_categories,
    build_latest_checkin_payload,
    build_weekly_trend,
    iso_utc,
    metric_state_key,
    normalize_tag_keys,
    now_utc,
    parse_iso,
    starter_activities,
)
from backend.services.neo4j.wellness_query_helpers import build_diary_item, build_sync_change, find_activity_doc


class WellnessService:
    """Serve the wellness reference slice from Neo4j."""

    def __init__(self) -> None:
        """Bind the service to the configured Neo4j handler.

        Raises:
            ValueError: If the configured database handler is not Neo4j.
        """
        handler = get_database_handler()
        if not isinstance(handler, Neo4jHandler):
            raise ValueError("Neo4j WellnessService requires Neo4j database")

        self.handler = handler
        self.driver = handler.driver
        self._indexes_initialized = False

    async def _ensure_indexes(self) -> None:
        """Create the indexes used by the wellness reference slice."""
        if self._indexes_initialized:
            return

        statements = [
            "CREATE INDEX wellness_activity_user_id IF NOT EXISTS FOR (n:WellnessActivity) ON (n.user_id)",
            "CREATE INDEX wellness_activity_lookup IF NOT EXISTS FOR (n:WellnessActivity) ON (n.user_id, n.id)",
            "CREATE INDEX wellness_diary_user_id IF NOT EXISTS FOR (n:WellnessDiaryEntry) ON (n.user_id)",
            "CREATE INDEX wellness_diary_lookup IF NOT EXISTS FOR (n:WellnessDiaryEntry) ON (n.user_id, n.id)",
            "CREATE INDEX wellness_diary_created_at IF NOT EXISTS FOR (n:WellnessDiaryEntry) ON (n.user_id, n.created_at)",
            "CREATE INDEX wellness_checkin_user_id IF NOT EXISTS FOR (n:WellnessCheckIn) ON (n.user_id)",
            "CREATE INDEX wellness_checkin_lookup IF NOT EXISTS FOR (n:WellnessCheckIn) ON (n.user_id, n.id)",
            "CREATE INDEX wellness_checkin_recorded_at IF NOT EXISTS FOR (n:WellnessCheckIn) ON (n.user_id, n.recorded_at)",
            "CREATE INDEX sync_operation_log_lookup IF NOT EXISTS FOR (n:SyncOperationLog) ON (n.user_id, n.op_id)",
            "CREATE INDEX sync_conflict_log_user_id IF NOT EXISTS FOR (n:SyncConflictLog) ON (n.user_id, n.detected_at)",
        ]
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement)
        self._indexes_initialized = True

    async def _ensure_user_exists(self, user_id: str) -> None:
        """Ensure the authenticated user node exists before serving wellness data.

        Args:
            user_id (str): Authenticated user identifier.

        Raises:
            ValueError: If the user node cannot be found.
        """
        query = "MATCH (u:User {id: $user_id}) RETURN u.id AS user_id LIMIT 1"
        with self.driver.session() as session:
            result = session.run(query, user_id=user_id)
            if result.single() is None:
                raise ValueError("User not found")

    async def _ensure_seed_data(self, user_id: str) -> None:
        """Ensure starter activities exist for the requested user.

        Args:
            user_id (str): Authenticated user identifier.
        """
        await self._ensure_indexes()
        await self._ensure_user_exists(user_id)

        with self.driver.session() as session:
            check_result = session.run(
                "MATCH (a:WellnessActivity {user_id: $user_id}) RETURN a.id AS id LIMIT 1",
                user_id=user_id,
            )
            if check_result.single() is not None:
                return

            for item in starter_activities(user_id):
                session.run(
                    """
                    CREATE (a:WellnessActivity)
                    SET a = $props
                    """,
                    props=item,
                )

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True) -> Dict[str, Any]:
        """Delete the user's wellness content and optionally restore starter activities.

        Args:
            user_id (str): Authenticated user identifier.
            keep_activity_catalog (bool): Whether to restore the starter activities after reset.

        Returns:
            Dict[str, Any]: Reset summary payload.
        """
        try:
            await self._ensure_indexes()
            await self._ensure_user_exists(user_id)
            with self.driver.session() as session:
                diary_count = session.run(
                    "MATCH (n:WellnessDiaryEntry {user_id: $user_id}) RETURN count(n) AS count",
                    user_id=user_id,
                ).single()["count"]
                checkin_count = session.run(
                    "MATCH (n:WellnessCheckIn {user_id: $user_id}) RETURN count(n) AS count",
                    user_id=user_id,
                ).single()["count"]
                operation_count = session.run(
                    "MATCH (n:SyncOperationLog {user_id: $user_id}) RETURN count(n) AS count",
                    user_id=user_id,
                ).single()["count"]
                conflict_count = session.run(
                    "MATCH (n:SyncConflictLog {user_id: $user_id}) RETURN count(n) AS count",
                    user_id=user_id,
                ).single()["count"]
                session.run("MATCH (n:WellnessDiaryEntry {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
                session.run("MATCH (n:WellnessCheckIn {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
                session.run("MATCH (n:SyncOperationLog {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
                session.run("MATCH (n:SyncConflictLog {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
                session.run("MATCH (n:WellnessActivity {user_id: $user_id}) DETACH DELETE n", user_id=user_id)

            activity_count = 0
            if keep_activity_catalog:
                await self._ensure_seed_data(user_id)
                with self.driver.session() as session:
                    activity_count = session.run(
                        "MATCH (n:WellnessActivity {user_id: $user_id}) RETURN count(n) AS count",
                        user_id=user_id,
                    ).single()["count"]

            return {
                "status": "success",
                "message": "Wellness data reset successfully",
                "data": {
                    "activities": int(activity_count or 0),
                    "deleted_diary_entries": int(diary_count or 0),
                    "deleted_checkins": int(checkin_count or 0),
                    "deleted_sync_operation_logs": int(operation_count or 0),
                    "deleted_sync_conflicts": int(conflict_count or 0),
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error resetting wellness data: {str(exc)}",
                "data": None,
            }

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Return the current dashboard summary for the authenticated user.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Dashboard payload with latest check-in and weekly trend.
        """
        try:
            await self._ensure_seed_data(user_id)
            latest_query = """
            MATCH (c:WellnessCheckIn {user_id: $user_id})
            RETURN c {
                .id, .recorded_at, .mood_score, .stress_score, .energy_score,
                .note, .created_at, .updated_at
            } AS checkin
            ORDER BY c.recorded_at DESC
            LIMIT 1
            """
            trend_query = """
            MATCH (c:WellnessCheckIn {user_id: $user_id})
            RETURN c.recorded_at AS recorded_at, c.mood_score AS mood_score
            ORDER BY c.recorded_at DESC
            LIMIT 90
            """
            with self.driver.session() as session:
                latest_record = session.run(latest_query, user_id=user_id).single()
                trend_records = [dict(item) for item in session.run(trend_query, user_id=user_id)]

            latest_payload = build_latest_checkin_payload(dict(latest_record["checkin"])) if latest_record else None
            weekly_trend = build_weekly_trend(trend_records)
            return {"status": "success", "data": {"latest_checkin": latest_payload, "weekly_trend": weekly_trend}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading dashboard: {str(exc)}", "data": None}

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        """Return the starter activity catalog plus favorite state.

        Args:
            user_id (str): Authenticated user identifier.

        Returns:
            Dict[str, Any]: Activity categories and items for the user.
        """
        try:
            await self._ensure_seed_data(user_id)
            query = """
            MATCH (a:WellnessActivity {user_id: $user_id})
            RETURN a {
                .id, .user_id, .icon_key, .title_key, .title, .summary_key, .summary,
                .duration_minutes, .favorite, .category_keys, .energy_impact,
                .created_at, .updated_at
            } AS activity
            ORDER BY a.favorite DESC, a.duration_minutes ASC, a.title_key ASC
            """
            with self.driver.session() as session:
                items = [dict(record["activity"]) for record in session.run(query, user_id=user_id)]
            return {"status": "success", "data": {"categories": build_activity_categories(items), "items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading activities: {str(exc)}", "data": None}

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50) -> Dict[str, Any]:
        """Return the combined wellness snapshot used for first local hydration.

        Args:
            user_id (str): Authenticated user identifier.
            diary_limit (int): Maximum diary entries to include.
            checkin_limit (int): Maximum check-ins to include.

        Returns:
            Dict[str, Any]: Bootstrap payload for offline hydration.
        """
        try:
            await self._ensure_seed_data(user_id)
            activities_query = """
            MATCH (a:WellnessActivity {user_id: $user_id})
            RETURN a {
                .id, .user_id, .icon_key, .title_key, .title, .summary_key, .summary,
                .duration_minutes, .favorite, .category_keys, .energy_impact,
                .created_at, .updated_at
            } AS item
            ORDER BY a.favorite DESC, a.duration_minutes ASC, a.title_key ASC
            """
            diary_query = """
            MATCH (d:WellnessDiaryEntry {user_id: $user_id})
            RETURN d {
                .id, .title_key, .title, .summary_key, .summary, .mood_state_key,
                .mood_score, .tag_keys, .related_activity_id, .created_at, .updated_at
            } AS item
            ORDER BY d.created_at DESC
            LIMIT $limit
            """
            checkins_query = """
            MATCH (c:WellnessCheckIn {user_id: $user_id})
            RETURN c {
                .id, .recorded_at, .mood_score, .stress_score, .energy_score,
                .note, .created_at, .updated_at
            } AS item
            ORDER BY c.recorded_at DESC
            LIMIT $limit
            """
            with self.driver.session() as session:
                activities = [dict(record["item"]) for record in session.run(activities_query, user_id=user_id)]
                diary_entries = [
                    await build_diary_item(self.driver, user_id=user_id, entry=dict(record["item"]))
                    for record in session.run(diary_query, user_id=user_id, limit=diary_limit)
                ]
                checkins = [dict(record["item"]) for record in session.run(checkins_query, user_id=user_id, limit=checkin_limit)]

            return {
                "status": "success",
                "data": {
                    "server_timestamp": iso_utc(now_utc()),
                    "activities": activities,
                    "diary_entries": diary_entries,
                    "checkins": checkins,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync bootstrap: {str(exc)}", "data": None}

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None) -> Dict[str, Any]:
        """Return incremental wellness changes after the provided cursor.

        Args:
            user_id (str): Authenticated user identifier.
            cursor (Optional[str]): Last seen update cursor.
            limit (int): Maximum change items to return.
            entity_type (Optional[str]): Optional entity type filter.

        Returns:
            Dict[str, Any]: Incremental change payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            allowed_entity_types = {
                "wellness_activity": "WellnessActivity",
                "wellness_diary_entry": "WellnessDiaryEntry",
                "wellness_checkin": "WellnessCheckIn",
            }
            if entity_type and entity_type not in allowed_entity_types:
                return {"status": "error", "message": f"Unsupported entity_type: {entity_type}", "data": None}

            cursor_dt = parse_iso(cursor) if cursor else None
            selected_types = [entity_type] if entity_type else list(allowed_entity_types.keys())
            query_limit = max(limit * 2, 100)
            changes: List[Dict[str, Any]] = []

            with self.driver.session() as session:
                for selected_type in selected_types:
                    label = allowed_entity_types[selected_type]
                    query = f"""
                    MATCH (n:{label} {{user_id: $user_id}})
                    WHERE $cursor IS NULL OR n.updated_at > $cursor
                    RETURN n AS item
                    ORDER BY n.updated_at ASC, n.id ASC
                    LIMIT $limit
                    """
                    for record in session.run(
                        query,
                        user_id=user_id,
                        cursor=iso_utc(cursor_dt) if cursor_dt else None,
                        limit=query_limit,
                    ):
                        changes.append(await build_sync_change(self.driver, user_id=user_id, entity_type=selected_type, payload=dict(record["item"])))

            changes.sort(key=lambda item: (item.get("updated_at") or "", item.get("entity_type") or "", item.get("entity_id") or ""))
            selected_changes = changes[:limit]
            next_cursor = selected_changes[-1]["updated_at"] if selected_changes else cursor
            return {
                "status": "success",
                "data": {
                    "server_timestamp": iso_utc(now_utc()),
                    "changes": selected_changes,
                    "next_cursor": next_cursor,
                    "has_more": len(changes) > limit,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync changes: {str(exc)}", "data": None}

    async def update_activity(self, user_id: str, activity_id: str, favorite: Optional[bool] = None) -> Dict[str, Any]:
        """Update mutable activity state for one user-scoped activity.

        Args:
            user_id (str): Authenticated user identifier.
            activity_id (str): Activity identifier to update.
            favorite (Optional[bool]): Updated favorite state.

        Returns:
            Dict[str, Any]: Updated activity payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            if favorite is None:
                return {"status": "error", "message": "Activity update requires at least one mutable field", "data": None}
            updated_at = iso_utc(now_utc())
            query = """
            MATCH (a:WellnessActivity {user_id: $user_id, id: $activity_id})
            SET a.favorite = $favorite,
                a.updated_at = $updated_at
            RETURN a {
                .id, .user_id, .icon_key, .title_key, .title, .summary_key, .summary,
                .duration_minutes, .favorite, .category_keys, .energy_impact,
                .created_at, .updated_at
            } AS activity
            """
            with self.driver.session() as session:
                record = session.run(
                    query,
                    user_id=user_id,
                    activity_id=activity_id,
                    favorite=bool(favorite),
                    updated_at=updated_at,
                ).single()
            if record is None:
                return {"status": "error", "message": "Activity not found", "data": None}
            return {"status": "success", "message": "Activity updated successfully", "data": dict(record["activity"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity: {str(exc)}", "data": None}

    async def create_checkin(self, user_id: str, mood_score: int, stress_score: int, energy_score: int, note: Optional[str] = None) -> Dict[str, Any]:
        """Create a new check-in node for the authenticated user.

        Args:
            user_id (str): Authenticated user identifier.
            mood_score (int): Mood score to store.
            stress_score (int): Stress score to store.
            energy_score (int): Energy score to store.
            note (Optional[str]): Optional free-text note.

        Returns:
            Dict[str, Any]: Created check-in payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            now = iso_utc(now_utc())
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "recorded_at": now,
                "mood_score": int(mood_score),
                "stress_score": int(stress_score),
                "energy_score": int(energy_score),
                "note": str(note).strip() if isinstance(note, str) and note.strip() else None,
                "created_at": now,
                "updated_at": now,
            }
            with self.driver.session() as session:
                session.run("CREATE (c:WellnessCheckIn) SET c = $props", props=payload)
            return {"status": "success", "message": "Check-in created successfully", "data": build_latest_checkin_payload(payload)}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating check-in: {str(exc)}", "data": None}

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """Return the authenticated user's diary entries.

        Args:
            user_id (str): Authenticated user identifier.
            limit (int): Maximum entries to return.

        Returns:
            Dict[str, Any]: Diary entry list payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            query = """
            MATCH (d:WellnessDiaryEntry {user_id: $user_id})
            RETURN d {
                .id, .title_key, .title, .summary_key, .summary, .mood_state_key,
                .mood_score, .tag_keys, .related_activity_id, .created_at, .updated_at
            } AS item
            ORDER BY d.created_at DESC
            LIMIT $limit
            """
            with self.driver.session() as session:
                items = [await build_diary_item(self.driver, user_id=user_id, entry=dict(record["item"])) for record in session.run(query, user_id=user_id, limit=limit)]
            return {"status": "success", "data": {"items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading diary entries: {str(exc)}", "data": None}

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a diary entry node for the authenticated user.

        Args:
            user_id (str): Authenticated user identifier.
            title (str): Diary entry title.
            summary (str): Diary entry summary text.
            mood_score (int): Mood score linked to the entry.
            tag_keys (List[str]): Raw tag keys from the client.
            related_activity_id (Optional[str]): Optional related activity identifier.

        Returns:
            Dict[str, Any]: Created diary entry payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            related_activity = await find_activity_doc(self.driver, user_id=user_id, activity_id=related_activity_id)
            if related_activity_id and related_activity is None:
                return {"status": "error", "message": "Related activity not found", "data": None}
            now = iso_utc(now_utc())
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "title_key": None,
                "title": title.strip(),
                "summary_key": None,
                "summary": summary.strip(),
                "mood_state_key": metric_state_key("mood", int(mood_score)),
                "mood_score": int(mood_score),
                "tag_keys": normalize_tag_keys(tag_keys),
                "related_activity_id": related_activity_id,
                "created_at": now,
                "updated_at": now,
            }
            with self.driver.session() as session:
                session.run("CREATE (d:WellnessDiaryEntry) SET d = $props", props=payload)
            item = await build_diary_item(self.driver, user_id=user_id, entry=payload)
            return {"status": "success", "message": "Diary entry created successfully", "data": item}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating diary entry: {str(exc)}", "data": None}
