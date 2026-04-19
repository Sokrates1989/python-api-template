"""Neo4j-backed wellness content service for dashboard, activities, diary, and check-ins.

This service mirrors the MongoDB and SQL wellness reference slice using direct
Cypher queries against the configured Neo4j database. The implementation keeps
all wellness nodes user-scoped through a `user_id` property so the Flutter
client can switch backend providers without changing its API contract.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.database import get_database_handler
from backend.database.neo4j_handler import Neo4jHandler


class WellnessService:
    """Serve the wellness reference slice from Neo4j."""

    _WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    _CATEGORY_DEFINITIONS = {
        "calm": {
            "title_key": "app_shell.activities.category_calm",
            "description_key": "app_shell.activities.category_calm_desc",
        },
        "focus": {
            "title_key": "app_shell.activities.category_focus",
            "description_key": "app_shell.activities.category_focus_desc",
        },
        "energy": {
            "title_key": "app_shell.activities.category_energy",
            "description_key": "app_shell.activities.category_energy_desc",
        },
    }

    def __init__(self) -> None:
        """Bind the service to the configured Neo4j handler."""
        handler = get_database_handler()
        if not isinstance(handler, Neo4jHandler):
            raise ValueError("Neo4j WellnessService requires Neo4j database")

        self.handler = handler
        self.driver = handler.driver
        self._indexes_initialized = False

    @staticmethod
    def _now_utc() -> datetime:
        """Return the current UTC timestamp."""
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_dt(value: datetime) -> datetime:
        """Normalize an incoming datetime to UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _iso(cls, value: datetime) -> str:
        """Return a canonical Z-suffixed ISO timestamp."""
        return cls._normalize_dt(value).isoformat().replace("+00:00", "Z")

    @classmethod
    def _parse_iso(cls, value: str) -> datetime:
        """Parse an API timestamp back into a UTC datetime."""
        return cls._normalize_dt(datetime.fromisoformat(str(value).replace("Z", "+00:00")))

    @classmethod
    def _metric_state_key(cls, metric: str, score: int) -> str:
        """Convert a numeric wellness score into the shared UI state key."""
        if metric == "mood":
            if score <= 3:
                return "very_unhappy"
            if score <= 5:
                return "uneasy"
            if score <= 7:
                return "steady"
            return "happy"
        if metric == "stress":
            if score <= 3:
                return "calm"
            if score <= 5:
                return "balanced"
            if score <= 7:
                return "tense"
            return "overloaded"
        if score <= 3:
            return "drained"
        if score <= 5:
            return "low"
        if score <= 7:
            return "alert"
        return "energized"

    @staticmethod
    def _normalize_tag_keys(tag_keys: List[str]) -> List[str]:
        """Normalize diary tags into the shared lowercase underscore format."""
        normalized: List[str] = []
        for raw_tag in tag_keys:
            cleaned = str(raw_tag).strip().lower().replace(" ", "_")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= 6:
                break
        return normalized

    @staticmethod
    def _normalize_record(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return a plain dict copy for response payload shaping."""
        if not record:
            return None
        return dict(record)

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
        """Ensure the authenticated user node exists before serving wellness data."""
        query = "MATCH (u:User {id: $user_id}) RETURN u.id AS user_id LIMIT 1"
        with self.driver.session() as session:
            result = session.run(query, user_id=user_id)
            if result.single() is None:
                raise ValueError("User not found")

    def _starter_activities(self, user_id: str) -> List[Dict[str, Any]]:
        """Return the shared starter activity catalog for a new user."""
        now = self._now_utc().replace(hour=9, minute=0, second=0, microsecond=0)
        created_at = self._iso(now)
        payloads = [
            {"id": "breathe-reset", "icon_key": "air", "title_key": "app_shell.activities.seed_breathe_title", "summary_key": "app_shell.activities.seed_breathe_summary", "duration_minutes": 1, "favorite": True, "category_keys": ["calm", "focus"], "energy_impact": "reset"},
            {"id": "clarity-journal", "icon_key": "book", "title_key": "app_shell.activities.seed_journal_title", "summary_key": "app_shell.activities.seed_journal_summary", "duration_minutes": 8, "favorite": True, "category_keys": ["focus"], "energy_impact": "grounding"},
            {"id": "soft-stretch", "icon_key": "self_improvement", "title_key": "app_shell.activities.seed_stretch_title", "summary_key": "app_shell.activities.seed_stretch_summary", "duration_minutes": 6, "favorite": False, "category_keys": ["energy", "calm"], "energy_impact": "lift"},
            {"id": "focus-walk", "icon_key": "directions_walk", "title_key": "app_shell.activities.seed_walk_title", "summary_key": "app_shell.activities.seed_walk_summary", "duration_minutes": 12, "favorite": False, "category_keys": ["energy", "focus"], "energy_impact": "lift"},
            {"id": "pause-and-tea", "icon_key": "local_cafe", "title_key": "app_shell.activities.seed_tea_title", "summary_key": "app_shell.activities.seed_tea_summary", "duration_minutes": 10, "favorite": False, "category_keys": ["calm"], "energy_impact": "ease"},
        ]
        items: List[Dict[str, Any]] = []
        for item in payloads:
            items.append({
                "id": item["id"],
                "user_id": user_id,
                "icon_key": item["icon_key"],
                "title_key": item["title_key"],
                "title": None,
                "summary_key": item["summary_key"],
                "summary": None,
                "duration_minutes": item["duration_minutes"],
                "favorite": item["favorite"],
                "category_keys": list(item["category_keys"]),
                "energy_impact": item["energy_impact"],
                "created_at": created_at,
                "updated_at": created_at,
            })
        return items

    async def _ensure_seed_data(self, user_id: str) -> None:
        """Ensure starter activities exist for the requested user."""
        await self._ensure_indexes()
        await self._ensure_user_exists(user_id)

        with self.driver.session() as session:
            check_result = session.run(
                "MATCH (a:WellnessActivity {user_id: $user_id}) RETURN a.id AS id LIMIT 1",
                user_id=user_id,
            )
            if check_result.single() is not None:
                return

            for item in self._starter_activities(user_id):
                session.run(
                    """
                    CREATE (a:WellnessActivity)
                    SET a = $props
                    """,
                    props=item,
                )

    async def _find_activity_doc(self, user_id: str, activity_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return one activity payload for the given user-scoped id."""
        if not activity_id:
            return None
        query = """
        MATCH (a:WellnessActivity {user_id: $user_id, id: $activity_id})
        RETURN a {
            .id, .user_id, .icon_key, .title_key, .title, .summary_key, .summary,
            .duration_minutes, .favorite, .category_keys, .energy_impact,
            .created_at, .updated_at
        } AS activity
        LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(query, user_id=user_id, activity_id=activity_id).single()
        return self._normalize_record(record["activity"]) if record else None

    async def _build_diary_item(self, user_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Attach related activity metadata to a diary entry payload."""
        item = self._normalize_record(entry) or {}
        related_activity = await self._find_activity_doc(user_id, item.get("related_activity_id"))
        item["related_activity_title_key"] = related_activity.get("title_key") if related_activity else None
        item["related_activity_title"] = related_activity.get("title") if related_activity else None
        return item

    async def _build_sync_change(self, *, user_id: str, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a backend record into the shared sync change envelope."""
        normalized = self._normalize_record(payload) or {}
        shaped_payload = normalized
        if entity_type == "wellness_diary_entry":
            shaped_payload = await self._build_diary_item(user_id, normalized)
        return {
            "entity_type": entity_type,
            "entity_id": shaped_payload.get("id", ""),
            "action": "upsert",
            "updated_at": shaped_payload.get("updated_at") or shaped_payload.get("created_at"),
            "payload": shaped_payload,
        }

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True) -> Dict[str, Any]:
        """Delete the user's wellness content and optionally restore starter activities."""
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
        """Return the current dashboard summary for the authenticated user."""
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
                trend_records = list(session.run(trend_query, user_id=user_id))

            trend_by_date: Dict[date, List[int]] = {}
            for item in trend_records:
                recorded_at = self._parse_iso(item["recorded_at"]).date()
                trend_by_date.setdefault(recorded_at, []).append(int(item["mood_score"] or 0))

            today = self._now_utc().date()
            weekly_trend = []
            for offset in range(6, -1, -1):
                target_day = today - timedelta(days=offset)
                mood_values = trend_by_date.get(target_day, [])
                value = round(sum(mood_values) / len(mood_values), 1) if mood_values else None
                weekly_trend.append({
                    "day_key": self._WEEKDAY_KEYS[target_day.weekday()],
                    "value": value,
                })

            latest_payload = None
            if latest_record is not None:
                latest = dict(latest_record["checkin"])
                latest_payload = {
                    "recorded_at": latest["recorded_at"],
                    "mood": {
                        "state_key": self._metric_state_key("mood", int(latest.get("mood_score") or 0)),
                        "score": int(latest.get("mood_score") or 0),
                    },
                    "stress": {
                        "state_key": self._metric_state_key("stress", int(latest.get("stress_score") or 0)),
                        "score": int(latest.get("stress_score") or 0),
                    },
                    "energy": {
                        "state_key": self._metric_state_key("energy", int(latest.get("energy_score") or 0)),
                        "score": int(latest.get("energy_score") or 0),
                    },
                    "note": latest.get("note"),
                }

            return {"status": "success", "data": {"latest_checkin": latest_payload, "weekly_trend": weekly_trend}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading dashboard: {str(exc)}", "data": None}

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        """Return the starter activity catalog plus favorite state."""
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

            categories = []
            for category_key, definition in self._CATEGORY_DEFINITIONS.items():
                count = sum(1 for item in items if category_key in item.get("category_keys", []))
                categories.append({
                    "key": category_key,
                    "title_key": definition["title_key"],
                    "description_key": definition["description_key"],
                    "item_count": count,
                })

            return {"status": "success", "data": {"categories": categories, "items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading activities: {str(exc)}", "data": None}

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50) -> Dict[str, Any]:
        """Return the combined wellness snapshot used for first local hydration."""
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
                diary_entries = [await self._build_diary_item(user_id, dict(record["item"])) for record in session.run(diary_query, user_id=user_id, limit=diary_limit)]
                checkins = [dict(record["item"]) for record in session.run(checkins_query, user_id=user_id, limit=checkin_limit)]

            return {
                "status": "success",
                "data": {
                    "server_timestamp": self._iso(self._now_utc()),
                    "activities": activities,
                    "diary_entries": diary_entries,
                    "checkins": checkins,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync bootstrap: {str(exc)}", "data": None}

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None) -> Dict[str, Any]:
        """Return incremental wellness changes after the provided cursor."""
        try:
            await self._ensure_seed_data(user_id)
            allowed_entity_types = {
                "wellness_activity": "WellnessActivity",
                "wellness_diary_entry": "WellnessDiaryEntry",
                "wellness_checkin": "WellnessCheckIn",
            }
            if entity_type and entity_type not in allowed_entity_types:
                return {"status": "error", "message": f"Unsupported entity_type: {entity_type}", "data": None}

            cursor_dt = self._parse_iso(cursor) if cursor else None
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
                    for record in session.run(query, user_id=user_id, cursor=self._iso(cursor_dt) if cursor_dt else None, limit=query_limit):
                        changes.append(await self._build_sync_change(user_id=user_id, entity_type=selected_type, payload=dict(record["item"])))

            changes.sort(key=lambda item: (item.get("updated_at") or "", item.get("entity_type") or "", item.get("entity_id") or ""))
            selected_changes = changes[:limit]
            next_cursor = selected_changes[-1]["updated_at"] if selected_changes else cursor
            return {
                "status": "success",
                "data": {
                    "server_timestamp": self._iso(self._now_utc()),
                    "changes": selected_changes,
                    "next_cursor": next_cursor,
                    "has_more": len(changes) > limit,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync changes: {str(exc)}", "data": None}

    async def update_activity(self, user_id: str, activity_id: str, favorite: Optional[bool] = None) -> Dict[str, Any]:
        """Update mutable activity state for one user-scoped activity."""
        try:
            await self._ensure_seed_data(user_id)
            if favorite is None:
                return {"status": "error", "message": "Activity update requires at least one mutable field", "data": None}
            updated_at = self._iso(self._now_utc())
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
                record = session.run(query, user_id=user_id, activity_id=activity_id, favorite=bool(favorite), updated_at=updated_at).single()
            if record is None:
                return {"status": "error", "message": "Activity not found", "data": None}
            return {"status": "success", "message": "Activity updated successfully", "data": dict(record["activity"])}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity: {str(exc)}", "data": None}

    async def create_checkin(self, user_id: str, mood_score: int, stress_score: int, energy_score: int, note: Optional[str] = None) -> Dict[str, Any]:
        """Create a new check-in node for the authenticated user."""
        try:
            await self._ensure_seed_data(user_id)
            now = self._iso(self._now_utc())
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
            latest_payload = {
                "recorded_at": payload["recorded_at"],
                "mood": {"state_key": self._metric_state_key("mood", payload["mood_score"]), "score": payload["mood_score"]},
                "stress": {"state_key": self._metric_state_key("stress", payload["stress_score"]), "score": payload["stress_score"]},
                "energy": {"state_key": self._metric_state_key("energy", payload["energy_score"]), "score": payload["energy_score"]},
                "note": payload["note"],
            }
            return {"status": "success", "message": "Check-in created successfully", "data": latest_payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating check-in: {str(exc)}", "data": None}

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """Return the authenticated user's diary entries."""
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
                items = [await self._build_diary_item(user_id, dict(record["item"])) for record in session.run(query, user_id=user_id, limit=limit)]
            return {"status": "success", "data": {"items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading diary entries: {str(exc)}", "data": None}

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a diary entry node for the authenticated user."""
        try:
            await self._ensure_seed_data(user_id)
            related_activity = await self._find_activity_doc(user_id, related_activity_id)
            if related_activity_id and related_activity is None:
                return {"status": "error", "message": "Related activity not found", "data": None}
            now = self._iso(self._now_utc())
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "title_key": None,
                "title": title.strip(),
                "summary_key": None,
                "summary": summary.strip(),
                "mood_state_key": self._metric_state_key("mood", int(mood_score)),
                "mood_score": int(mood_score),
                "tag_keys": self._normalize_tag_keys(tag_keys),
                "related_activity_id": related_activity_id,
                "created_at": now,
                "updated_at": now,
            }
            with self.driver.session() as session:
                session.run("CREATE (d:WellnessDiaryEntry) SET d = $props", props=payload)
            item = await self._build_diary_item(user_id, payload)
            return {"status": "success", "message": "Diary entry created successfully", "data": item}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating diary entry: {str(exc)}", "data": None}
