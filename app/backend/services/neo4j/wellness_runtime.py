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
    normalize_metric_values,
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
            "CREATE INDEX wellness_activity_category_lookup IF NOT EXISTS FOR (n:WellnessActivityCategory) ON (n.user_id, n.key)",
            "CREATE INDEX wellness_sync_tombstone_lookup IF NOT EXISTS FOR (n:WellnessSyncTombstone) ON (n.user_id, n.entity_type, n.entity_id)",
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

    async def _record_tombstone(self, user_id: str, entity_type: str, entity_id: str) -> None:
        """Create or refresh an incremental deletion marker node."""
        with self.driver.session() as session:
            session.run("MERGE (t:WellnessSyncTombstone {user_id: $user_id, entity_type: $entity_type, entity_id: $entity_id}) SET t.deleted_at = $deleted_at", user_id=user_id, entity_type=entity_type, entity_id=entity_id, deleted_at=iso_utc(now_utc())).consume()

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
            if check_result.single() is None:
                for sort_order, item in enumerate(starter_activities(user_id)):
                    item.update({"activity_reminder": None, "harmful": False, "tags": [], "sort_order": sort_order})
                    session.run("CREATE (a:WellnessActivity) SET a = $props", props=item)
            category_result = session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id}) RETURN c.key AS key LIMIT 1", user_id=user_id)
            if category_result.single() is None:
                activities = [dict(record["item"]) for record in session.run("MATCH (a:WellnessActivity {user_id: $user_id}) RETURN properties(a) AS item", user_id=user_id)]
                now = iso_utc(now_utc())
                for sort_order, category in enumerate(build_activity_categories(activities)):
                    props = {"user_id": user_id, **category, "title": None, "description": None, "icon_key": {"calm": "self_improvement", "focus": "center_focus_strong", "energy": "bolt"}.get(category["key"], "category"), "sort_order": sort_order, "created_at": now, "updated_at": now}
                    session.run("CREATE (c:WellnessActivityCategory) SET c = $props", props=props)

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
                session.run("MATCH (n:WellnessActivityCategory {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
                session.run("MATCH (n:WellnessSyncTombstone {user_id: $user_id}) DETACH DELETE n", user_id=user_id)

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
            query = "MATCH (a:WellnessActivity {user_id: $user_id}) RETURN properties(a) AS activity ORDER BY a.favorite DESC, a.sort_order ASC, a.title_key ASC"
            category_query = "MATCH (c:WellnessActivityCategory {user_id: $user_id}) RETURN properties(c) AS category ORDER BY c.sort_order ASC, c.key ASC"
            with self.driver.session() as session:
                items = [dict(record["activity"]) for record in session.run(query, user_id=user_id)]
                categories = []
                for record in session.run(category_query, user_id=user_id):
                    category = dict(record["category"])
                    category["item_count"] = sum(1 for item in items if category.get("key") in (item.get("category_keys") or []))
                    categories.append(category)
            return {"status": "success", "data": {"categories": categories, "items": items}}
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
            activities_query = "MATCH (a:WellnessActivity {user_id: $user_id}) RETURN properties(a) AS item ORDER BY a.favorite DESC, a.sort_order ASC, a.title_key ASC"
            categories_query = "MATCH (c:WellnessActivityCategory {user_id: $user_id}) RETURN properties(c) AS item ORDER BY c.sort_order ASC, c.key ASC"
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
                .tag_keys, .metrics, .activity_id, .note, .created_at, .updated_at
            } AS item
            ORDER BY c.recorded_at DESC
            LIMIT $limit
            """
            with self.driver.session() as session:
                activities = [dict(record["item"]) for record in session.run(activities_query, user_id=user_id)]
                categories = [dict(record["item"]) for record in session.run(categories_query, user_id=user_id)]
                diary_entries = [
                    await build_diary_item(self.driver, user_id=user_id, entry=dict(record["item"]))
                    for record in session.run(diary_query, user_id=user_id, limit=diary_limit)
                ]
                checkins = [dict(record["item"]) for record in session.run(checkins_query, user_id=user_id, limit=checkin_limit)]

            return {
                "status": "success",
                "data": {
                    "server_timestamp": iso_utc(now_utc()),
                    "activity_categories": categories,
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
                "wellness_activity_category": "WellnessActivityCategory",
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
                    ORDER BY n.updated_at ASC, coalesce(n.id, n.key) ASC
                    LIMIT $limit
                    """
                    for record in session.run(
                        query,
                        user_id=user_id,
                        cursor=iso_utc(cursor_dt) if cursor_dt else None,
                        limit=query_limit,
                    ):
                        changes.append(await build_sync_change(self.driver, user_id=user_id, entity_type=selected_type, payload=dict(record["item"])))
                tombstone_query = """
                MATCH (t:WellnessSyncTombstone {user_id: $user_id})
                WHERE ($entity_type IS NULL OR t.entity_type = $entity_type)
                  AND ($cursor IS NULL OR t.deleted_at > $cursor)
                RETURN t.entity_type AS entity_type, t.entity_id AS entity_id,
                       t.deleted_at AS updated_at
                ORDER BY t.deleted_at ASC
                LIMIT $limit
                """
                for record in session.run(tombstone_query, user_id=user_id, entity_type=entity_type, cursor=iso_utc(cursor_dt) if cursor_dt else None, limit=query_limit):
                    changes.append({"entity_type": record["entity_type"], "entity_id": record["entity_id"], "action": "delete", "updated_at": record["updated_at"], "payload": {}})

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

    @staticmethod
    def _clean_keys(values: object) -> List[str]:
        """Normalize identifier lists while preserving order."""
        if not isinstance(values, list):
            return []
        result: List[str] = []
        for value in values:
            key = str(value).strip()
            if key and key not in result:
                result.append(key)
        return result

    async def _validate_category_keys(self, user_id: str, values: object) -> List[str]:
        """Validate category references for one activity mutation."""
        keys = self._clean_keys(values)
        if not keys:
            raise ValueError("Activity requires at least one category")
        with self.driver.session() as session:
            existing = {record["key"] for record in session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id}) WHERE c.key IN $keys RETURN c.key AS key", user_id=user_id, keys=keys)}
        missing = [key for key in keys if key not in existing]
        if missing:
            raise ValueError(f"Unknown activity categories: {', '.join(missing)}")
        return keys

    @staticmethod
    def _activity_patch(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Select mutable fields accepted by the activity catalogue."""
        supported = {"icon_key", "title_key", "title", "summary_key", "summary", "activity_reminder", "duration_minutes", "favorite", "harmful", "tags", "sort_order", "energy_impact"}
        patch = {key: value for key, value in payload.items() if key in supported}
        if patch.get("icon_key") is None:
            patch.pop("icon_key", None)
        if "duration_minutes" in patch:
            patch["duration_minutes"] = max(0, int(patch["duration_minutes"]))
        if "sort_order" in patch:
            patch["sort_order"] = int(patch["sort_order"])
        if "tags" in patch:
            patch["tags"] = WellnessService._clean_keys(patch["tags"])
        return patch

    async def create_activity(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one user-owned activity node."""
        try:
            await self._ensure_seed_data(user_id)
            activity_id = str(payload.get("id") or uuid4()).strip()
            if not str(payload.get("title") or payload.get("title_key") or "").strip():
                return {"status": "error", "message": "Activity title is required", "data": None}
            now = iso_utc(now_utc())
            props = {"id": activity_id, "user_id": user_id, "icon_key": "auto_awesome", "title_key": None, "title": None, "summary_key": None, "summary": None, "activity_reminder": None, "duration_minutes": 0, "favorite": False, "harmful": False, "category_keys": await self._validate_category_keys(user_id, payload.get("category_keys")), "tags": [], "sort_order": 0, "energy_impact": None, "created_at": now, "updated_at": now, **self._activity_patch(payload)}
            with self.driver.session() as session:
                if session.run("MATCH (a:WellnessActivity {user_id: $user_id, id: $id}) RETURN a.id AS id", user_id=user_id, id=activity_id).single():
                    return {"status": "error", "message": "Activity already exists", "data": None}
                record = session.run("CREATE (a:WellnessActivity) SET a = $props RETURN properties(a) AS activity", props=props).single()
            return {"status": "success", "message": "Activity created successfully", "data": dict(record["activity"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity: {str(exc)}", "data": None}

    async def update_activity(self, user_id: str, activity_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch one user-owned activity node."""
        try:
            await self._ensure_seed_data(user_id)
            update = self._activity_patch(patch)
            if "category_keys" in patch:
                update["category_keys"] = await self._validate_category_keys(user_id, patch["category_keys"])
            update["updated_at"] = iso_utc(now_utc())
            with self.driver.session() as session:
                record = session.run("MATCH (a:WellnessActivity {user_id: $user_id, id: $activity_id}) SET a += $patch RETURN properties(a) AS activity", user_id=user_id, activity_id=activity_id, patch=update).single()
            if record is None:
                return {"status": "error", "message": "Activity not found", "data": None}
            return {"status": "success", "message": "Activity updated successfully", "data": dict(record["activity"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity: {str(exc)}", "data": None}

    async def delete_activity(self, user_id: str, activity_id: str) -> Dict[str, Any]:
        """Delete one activity node idempotently."""
        try:
            await self._record_tombstone(user_id, "wellness_activity", activity_id)
            with self.driver.session() as session:
                session.run("MATCH (a:WellnessActivity {user_id: $user_id, id: $activity_id}) DETACH DELETE a", user_id=user_id, activity_id=activity_id).consume()
            return {"status": "success", "message": "Activity deleted successfully", "data": {"id": activity_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting activity: {str(exc)}", "data": None}

    async def create_activity_category(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one persisted activity category node."""
        try:
            await self._ensure_seed_data(user_id)
            key = str(payload.get("key") or uuid4()).strip()
            if not str(payload.get("title") or payload.get("title_key") or "").strip():
                return {"status": "error", "message": "Activity category title is required", "data": None}
            now = iso_utc(now_utc())
            props = {"user_id": user_id, "key": key, "title_key": payload.get("title_key"), "title": payload.get("title"), "description_key": payload.get("description_key"), "description": payload.get("description"), "icon_key": payload.get("icon_key") or "category", "sort_order": int(payload.get("sort_order") or 0), "item_count": 0, "created_at": now, "updated_at": now}
            with self.driver.session() as session:
                if session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id, key: $key}) RETURN c.key AS key", user_id=user_id, key=key).single():
                    return {"status": "error", "message": "Activity category already exists", "data": None}
                record = session.run("CREATE (c:WellnessActivityCategory) SET c = $props RETURN properties(c) AS category", props=props).single()
            return {"status": "success", "message": "Activity category created successfully", "data": dict(record["category"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity category: {str(exc)}", "data": None}

    async def update_activity_category(self, user_id: str, category_key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch one persisted activity category node."""
        try:
            supported = {"title_key", "title", "description_key", "description", "icon_key", "sort_order"}
            update = {key: value for key, value in patch.items() if key in supported}
            if update.get("icon_key") is None:
                update.pop("icon_key", None)
            update["updated_at"] = iso_utc(now_utc())
            with self.driver.session() as session:
                record = session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id, key: $key}) SET c += $patch RETURN properties(c) AS category", user_id=user_id, key=category_key, patch=update).single()
            if record is None:
                return {"status": "error", "message": "Activity category not found", "data": None}
            return {"status": "success", "message": "Activity category updated successfully", "data": dict(record["category"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity category: {str(exc)}", "data": None}

    async def delete_activity_category(self, user_id: str, category_key: str) -> Dict[str, Any]:
        """Delete a category only when no activity references it."""
        try:
            with self.driver.session() as session:
                in_use = session.run("MATCH (a:WellnessActivity {user_id: $user_id}) WHERE $key IN coalesce(a.category_keys, []) RETURN a.id AS id LIMIT 1", user_id=user_id, key=category_key).single()
                if in_use:
                    return {"status": "error", "message": "Activity category is still in use", "data": None}
                await self._record_tombstone(user_id, "wellness_activity_category", category_key)
                session.run("MATCH (c:WellnessActivityCategory {user_id: $user_id, key: $key}) DETACH DELETE c", user_id=user_id, key=category_key).consume()
            return {"status": "success", "message": "Activity category deleted successfully", "data": {"key": category_key}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting activity category: {str(exc)}", "data": None}

    async def create_checkin(
        self,
        user_id: str,
        mood_score: int,
        stress_score: int,
        energy_score: int,
        note: Optional[str] = None,
        recorded_at: Optional[str] = None,
        tag_keys: Optional[List[str]] = None,
        metrics: Optional[Dict[str, int]] = None,
        activity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new check-in node for the authenticated user.

        Args:
            user_id (str): Authenticated user identifier.
            mood_score (int): Mood score to store.
            stress_score (int): Stress score to store.
            energy_score (int): Energy score to store.
            note (Optional[str]): Optional free-text note.
            recorded_at (Optional[str]): Optional ISO occurrence timestamp.
            tag_keys (Optional[List[str]]): Semantic tags to store.
            metrics (Optional[Dict[str, int]]): Captured flexible metrics.
            activity_id (Optional[str]): Optional linked activity identifier.

        Returns:
            Dict[str, Any]: Created check-in payload.
        """
        try:
            await self._ensure_seed_data(user_id)
            now_dt = now_utc()
            now = iso_utc(now_dt)
            occurred_at = parse_iso(recorded_at) if recorded_at else now_dt
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "recorded_at": iso_utc(occurred_at or now_dt),
                "mood_score": int(mood_score),
                "stress_score": int(stress_score),
                "energy_score": int(energy_score),
                "tag_keys": normalize_tag_keys(tag_keys or []),
                "metrics": normalize_metric_values(metrics),
                "activity_id": str(activity_id).strip() if isinstance(activity_id, str) and activity_id.strip() else None,
                "note": str(note).strip() if isinstance(note, str) and note.strip() else None,
                "created_at": now,
                "updated_at": now,
            }
            with self.driver.session() as session:
                session.run("CREATE (c:WellnessCheckIn) SET c = $props", props=payload)
            return {"status": "success", "message": "Check-in created successfully", "data": build_latest_checkin_payload(payload)}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating check-in: {str(exc)}", "data": None}

    async def update_checkin(
        self,
        user_id: str,
        checkin_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one existing check-in node.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.
            patch (Dict[str, Any]): Mutable check-in fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            update_payload: Dict[str, Any] = {"updated_at": iso_utc(now_utc())}
            if patch.get("recorded_at"):
                parsed = parse_iso(str(patch["recorded_at"]))
                if parsed is not None:
                    update_payload["recorded_at"] = iso_utc(parsed)
            for field in ("mood_score", "stress_score", "energy_score"):
                if field in patch and patch[field] is not None:
                    update_payload[field] = int(patch[field])
            if "note" in patch:
                note = patch["note"]
                update_payload["note"] = str(note).strip() if isinstance(note, str) and note.strip() else None
            if "activity_id" in patch:
                activity_id = patch["activity_id"]
                update_payload["activity_id"] = str(activity_id).strip() if isinstance(activity_id, str) and activity_id.strip() else None
            if isinstance(patch.get("tag_keys"), list):
                update_payload["tag_keys"] = normalize_tag_keys([str(item) for item in patch["tag_keys"]])
            if isinstance(patch.get("metrics"), dict):
                update_payload["metrics"] = normalize_metric_values(patch["metrics"])

            query = """
            MATCH (c:WellnessCheckIn {user_id: $user_id, id: $checkin_id})
            SET c += $patch
            RETURN c {
                .id, .recorded_at, .mood_score, .stress_score, .energy_score,
                .tag_keys, .metrics, .activity_id, .note, .created_at, .updated_at
            } AS item
            """
            with self.driver.session() as session:
                record = session.run(
                    query,
                    user_id=user_id,
                    checkin_id=checkin_id,
                    patch=update_payload,
                ).single()
            if record is None:
                return {"status": "error", "message": "Check-in not found", "data": None}
            await self._record_tombstone(user_id, "wellness_checkin", checkin_id)
            return {"status": "success", "message": "Check-in updated successfully", "data": dict(record["item"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating check-in: {str(exc)}", "data": None}

    async def delete_checkin(self, user_id: str, checkin_id: str) -> Dict[str, Any]:
        """Delete one existing check-in node.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            query = """
            MATCH (c:WellnessCheckIn {user_id: $user_id, id: $checkin_id})
            WITH c, c.id AS deleted_id
            DETACH DELETE c
            RETURN deleted_id
            """
            with self.driver.session() as session:
                record = session.run(
                    query,
                    user_id=user_id,
                    checkin_id=checkin_id,
                ).single()
            if record is None:
                return {"status": "error", "message": "Check-in not found", "data": None}
            return {"status": "success", "message": "Check-in deleted successfully", "data": {"id": checkin_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting check-in: {str(exc)}", "data": None}

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

    async def update_diary_entry(
        self,
        user_id: str,
        entry_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one existing diary entry node.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.
            patch (Dict[str, Any]): Mutable diary fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            update_payload: Dict[str, Any] = {"updated_at": iso_utc(now_utc())}
            if isinstance(patch.get("title"), str):
                update_payload["title"] = patch["title"].strip()
                update_payload["title_key"] = None
            if isinstance(patch.get("summary"), str):
                update_payload["summary"] = patch["summary"].strip()
                update_payload["summary_key"] = None
            if "mood_score" in patch and patch["mood_score"] is not None:
                update_payload["mood_score"] = int(patch["mood_score"])
                update_payload["mood_state_key"] = metric_state_key("mood", int(patch["mood_score"]))
            if isinstance(patch.get("tag_keys"), list):
                update_payload["tag_keys"] = normalize_tag_keys([str(item) for item in patch["tag_keys"]])
            if "related_activity_id" in patch:
                related_activity_id = patch["related_activity_id"]
                normalized_activity_id = str(related_activity_id).strip() if isinstance(related_activity_id, str) and related_activity_id.strip() else None
                if normalized_activity_id and await find_activity_doc(self.driver, user_id=user_id, activity_id=normalized_activity_id) is None:
                    return {"status": "error", "message": "Related activity not found", "data": None}
                update_payload["related_activity_id"] = normalized_activity_id

            query = """
            MATCH (d:WellnessDiaryEntry {user_id: $user_id, id: $entry_id})
            SET d += $patch
            RETURN d {
                .id, .title_key, .title, .summary_key, .summary, .mood_state_key,
                .mood_score, .tag_keys, .related_activity_id, .created_at, .updated_at
            } AS item
            """
            with self.driver.session() as session:
                record = session.run(
                    query,
                    user_id=user_id,
                    entry_id=entry_id,
                    patch=update_payload,
                ).single()
            if record is None:
                return {"status": "error", "message": "Diary entry not found", "data": None}
            await self._record_tombstone(user_id, "wellness_diary_entry", entry_id)
            payload = await build_diary_item(self.driver, user_id=user_id, entry=dict(record["item"]))
            return {"status": "success", "message": "Diary entry updated successfully", "data": payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating diary entry: {str(exc)}", "data": None}

    async def delete_diary_entry(self, user_id: str, entry_id: str) -> Dict[str, Any]:
        """Delete one existing diary entry node.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            query = """
            MATCH (d:WellnessDiaryEntry {user_id: $user_id, id: $entry_id})
            WITH d, d.id AS deleted_id
            DETACH DELETE d
            RETURN deleted_id
            """
            with self.driver.session() as session:
                record = session.run(
                    query,
                    user_id=user_id,
                    entry_id=entry_id,
                ).single()
            if record is None:
                return {"status": "error", "message": "Diary entry not found", "data": None}
            return {"status": "success", "message": "Diary entry deleted successfully", "data": {"id": entry_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting diary entry: {str(exc)}", "data": None}
