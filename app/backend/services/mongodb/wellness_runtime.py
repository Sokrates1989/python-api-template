"""Runtime implementation of the MongoDB wellness service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.database import get_database_handler
from backend.database.mongodb_handler import MongoDBHandler
from backend.services.mongodb.common import (
    build_activity_categories,
    build_latest_checkin_payload,
    build_weekly_trend,
    iso_utc,
    looks_like_legacy_seed_checkins,
    metric_state_key,
    normalize_document,
    normalize_metric_values,
    normalize_tag_keys,
    now_utc,
    parse_iso,
    starter_activities,
)
from backend.services.mongodb.query_helpers import build_diary_item, build_sync_change, find_activity_doc


class WellnessService:
    """Serve the wellness reference slice from MongoDB."""

    def __init__(self) -> None:
        """Bind the service to the configured MongoDB handler."""
        handler = get_database_handler()
        if not isinstance(handler, MongoDBHandler):
            raise ValueError("MongoDB WellnessService requires MongoDB database")
        self.handler = handler
        self.activities_collection = handler.database["wellness_activities"]
        self.categories_collection = handler.database["wellness_activity_categories"]
        self.tombstones_collection = handler.database["wellness_sync_tombstones"]
        self.diary_collection = handler.database["wellness_diary_entries"]
        self.checkins_collection = handler.database["wellness_checkins"]
        self.operation_log_collection = handler.database["sync_operation_log"]
        self.conflict_log_collection = handler.database["sync_conflicts"]
        self._indexes_initialized = False

    async def _ensure_indexes(self) -> None:
        """Create the indexes used by the wellness reference slice."""
        if self._indexes_initialized:
            return
        await self.activities_collection.create_index([("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_activities_user_id_id")
        await self.activities_collection.create_index([("user_id", 1), ("favorite", 1)], name="idx_wellness_activities_user_favorite")
        await self.categories_collection.create_index([("user_id", 1), ("key", 1)], unique=True, name="idx_wellness_activity_categories_user_key")
        await self.categories_collection.create_index([("user_id", 1), ("sort_order", 1)], name="idx_wellness_activity_categories_user_order")
        await self.tombstones_collection.create_index([("user_id", 1), ("entity_type", 1), ("entity_id", 1)], unique=True, name="idx_wellness_sync_tombstones_entity")
        await self.tombstones_collection.create_index([("user_id", 1), ("deleted_at", 1)], name="idx_wellness_sync_tombstones_user_deleted")
        await self.diary_collection.create_index([("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_diary_user_id_id")
        await self.diary_collection.create_index([("user_id", 1), ("created_at", -1)], name="idx_wellness_diary_user_created_at")
        await self.checkins_collection.create_index([("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_checkins_user_id_id")
        await self.checkins_collection.create_index([("user_id", 1), ("recorded_at", -1)], name="idx_wellness_checkins_user_recorded_at")
        self._indexes_initialized = True

    async def _purge_legacy_seed_data(self, user_id: str) -> None:
        """Remove legacy seeded diary and check-in data for the user."""
        await self.diary_collection.delete_many(
            {
                "user_id": user_id,
                "$or": [
                    {"title_key": {"$regex": r"^app_shell\.diary\.seed_entry_"}},
                    {"summary_key": {"$regex": r"^app_shell\.diary\.seed_entry_"}},
                ],
            }
        )
        checkin_docs = await self.checkins_collection.find(
            {"user_id": user_id},
            {"_id": 0, "recorded_at": 1, "created_at": 1, "updated_at": 1, "note": 1},
        ).to_list(length=20)
        if checkin_docs and looks_like_legacy_seed_checkins(checkin_docs):
            await self.checkins_collection.delete_many({"user_id": user_id})

    async def _record_tombstone(self, user_id: str, entity_type: str, entity_id: str) -> None:
        """Create or refresh an incremental deletion marker."""
        await self.tombstones_collection.update_one(
            {"user_id": user_id, "entity_type": entity_type, "entity_id": entity_id},
            {"$set": {"deleted_at": iso_utc(now_utc())}},
            upsert=True,
        )

    async def _ensure_seed_data(self, user_id: str) -> None:
        """Ensure starter activities exist for the requested user."""
        await self._ensure_indexes()
        await self._purge_legacy_seed_data(user_id)
        if not await self.activities_collection.find_one({"user_id": user_id}, {"_id": 1}):
            activities = starter_activities(user_id)
            for sort_order, activity in enumerate(activities):
                activity.setdefault("activity_reminder", None)
                activity.setdefault("harmful", False)
                activity.setdefault("tags", [])
                activity.setdefault("sort_order", sort_order)
            await self.activities_collection.insert_many(activities)
        if not await self.categories_collection.find_one({"user_id": user_id}, {"_id": 1}):
            now = iso_utc(now_utc())
            categories = build_activity_categories([item async for item in self.activities_collection.find({"user_id": user_id}, {"_id": 0})])
            await self.categories_collection.insert_many([
                {
                    "user_id": user_id,
                    **category,
                    "title": None,
                    "description": None,
                    "icon_key": {"calm": "self_improvement", "focus": "center_focus_strong", "energy": "bolt"}.get(category["key"], "category"),
                    "sort_order": sort_order,
                    "created_at": now,
                    "updated_at": now,
                }
                for sort_order, category in enumerate(categories)
            ])

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True) -> Dict[str, Any]:
        """Delete the user's wellness content and optionally restore starter activities."""
        try:
            await self._ensure_indexes()
            diary_result = await self.diary_collection.delete_many({"user_id": user_id})
            checkin_result = await self.checkins_collection.delete_many({"user_id": user_id})
            operation_log_result = await self.operation_log_collection.delete_many({"user_id": user_id})
            conflict_log_result = await self.conflict_log_collection.delete_many({"user_id": user_id})
            await self.activities_collection.delete_many({"user_id": user_id})
            await self.categories_collection.delete_many({"user_id": user_id})
            await self.tombstones_collection.delete_many({"user_id": user_id})

            activity_count = 0
            if keep_activity_catalog:
                await self._ensure_seed_data(user_id)
                activity_count = await self.activities_collection.count_documents({"user_id": user_id})

            return {
                "status": "success",
                "message": "Wellness data reset successfully",
                "data": {
                    "activities": activity_count,
                    "deleted_diary_entries": diary_result.deleted_count,
                    "deleted_checkins": checkin_result.deleted_count,
                    "deleted_sync_operation_logs": operation_log_result.deleted_count,
                    "deleted_sync_conflicts": conflict_log_result.deleted_count,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error resetting wellness data: {str(exc)}", "data": None}

    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Return the current dashboard summary for the authenticated user."""
        try:
            await self._ensure_seed_data(user_id)
            latest_doc = await self.checkins_collection.find_one({"user_id": user_id}, sort=[("recorded_at", -1)])
            trend_docs = await self.checkins_collection.find(
                {"user_id": user_id},
                {"_id": 0, "recorded_at": 1, "mood_score": 1},
            ).to_list(length=90)
            return {
                "status": "success",
                "data": {
                    "latest_checkin": build_latest_checkin_payload(normalize_document(latest_doc)),
                    "weekly_trend": build_weekly_trend(trend_docs),
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading dashboard: {str(exc)}", "data": None}

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        """Return the starter activity catalog plus favorite state."""
        try:
            await self._ensure_seed_data(user_id)
            activity_docs = await self.activities_collection.find(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("favorite", -1), ("sort_order", 1), ("title_key", 1)],
            ).to_list(length=200)
            activities = [normalize_document(doc) for doc in activity_docs]
            activities = [item for item in activities if item is not None]
            category_docs = await self.categories_collection.find({"user_id": user_id}, {"_id": 0, "user_id": 0}, sort=[("sort_order", 1), ("key", 1)]).to_list(length=200)
            categories = []
            for document in category_docs:
                item = normalize_document(document) or {}
                item["item_count"] = sum(1 for activity in activities if item.get("key") in activity.get("category_keys", []))
                categories.append(item)
            return {"status": "success", "data": {"categories": categories, "items": activities}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading activities: {str(exc)}", "data": None}

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50) -> Dict[str, Any]:
        """Return the full bootstrap payload for hybrid sync clients."""
        try:
            await self._ensure_seed_data(user_id)
            activities_result = await self.list_activities(user_id)
            if activities_result.get("status") != "success":
                return activities_result
            diary_result = await self.list_diary_entries(user_id, limit=diary_limit)
            if diary_result.get("status") != "success":
                return diary_result
            checkin_docs = await self.checkins_collection.find(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("recorded_at", -1)],
            ).to_list(length=checkin_limit)
            checkins = [normalize_document(doc) for doc in checkin_docs]
            checkins = [item for item in checkins if item is not None]
            return {
                "status": "success",
                "data": {
                    "server_timestamp": iso_utc(now_utc()),
                    "activity_categories": activities_result["data"]["categories"],
                    "activities": activities_result["data"]["items"],
                    "diary_entries": diary_result["data"]["items"],
                    "checkins": checkins,
                },
            }
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync bootstrap: {str(exc)}", "data": None}

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None) -> Dict[str, Any]:
        """Return incremental sync changes for the requested user."""
        try:
            await self._ensure_seed_data(user_id)
            allowed_entity_types = {
                "wellness_activity": self.activities_collection,
                "wellness_activity_category": self.categories_collection,
                "wellness_diary_entry": self.diary_collection,
                "wellness_checkin": self.checkins_collection,
            }
            if entity_type and entity_type not in allowed_entity_types:
                return {"status": "error", "message": f"Unsupported entity_type: {entity_type}", "data": None}

            cursor_filter: Dict[str, Any] = {}
            if cursor:
                cursor_filter["updated_at"] = {"$gt": cursor}

            changes: List[Dict[str, Any]] = []
            selected_types = [entity_type] if entity_type else list(allowed_entity_types.keys())
            query_limit = max(limit * 2, 100)
            for selected_type in selected_types:
                collection = allowed_entity_types[selected_type]
                docs = await collection.find(
                    {"user_id": user_id, **cursor_filter},
                    {"_id": 0},
                    sort=[("updated_at", 1), ("id", 1)],
                ).to_list(length=query_limit)
                for doc in docs:
                    changes.append(
                        await build_sync_change(
                            self.activities_collection,
                            user_id=user_id,
                            entity_type=selected_type,
                            payload=doc,
                        )
                    )
            tombstone_filter: Dict[str, Any] = {"user_id": user_id}
            if entity_type:
                tombstone_filter["entity_type"] = entity_type
            if cursor:
                tombstone_filter["deleted_at"] = {"$gt": cursor}
            tombstones = await self.tombstones_collection.find(tombstone_filter, {"_id": 0, "user_id": 0}, sort=[("deleted_at", 1)]).to_list(length=query_limit)
            changes.extend({"entity_type": item["entity_type"], "entity_id": item["entity_id"], "action": "delete", "updated_at": item["deleted_at"], "payload": {}} for item in tombstones)
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
        """Normalize a list of identifiers while preserving order."""
        if not isinstance(values, list):
            return []
        result: List[str] = []
        for value in values:
            key = str(value).strip()
            if key and key not in result:
                result.append(key)
        return result

    async def _validate_category_keys(self, user_id: str, values: object) -> List[str]:
        """Validate that at least one persisted category is referenced."""
        keys = self._clean_keys(values)
        if not keys:
            raise ValueError("Activity requires at least one category")
        docs = await self.categories_collection.find({"user_id": user_id, "key": {"$in": keys}}, {"key": 1}).to_list(length=len(keys))
        existing = {str(item.get("key")) for item in docs}
        missing = [key for key in keys if key not in existing]
        if missing:
            raise ValueError(f"Unknown activity categories: {', '.join(missing)}")
        return keys

    @staticmethod
    def _activity_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
        """Select and normalize mutable activity document fields."""
        supported = {"icon_key", "title_key", "title", "summary_key", "summary", "activity_reminder", "duration_minutes", "favorite", "harmful", "tags", "sort_order", "energy_impact"}
        result = {key: value for key, value in patch.items() if key in supported}
        if result.get("icon_key") is None:
            result.pop("icon_key", None)
        if "duration_minutes" in result:
            result["duration_minutes"] = max(0, int(result["duration_minutes"]))
        if "sort_order" in result:
            result["sort_order"] = int(result["sort_order"])
        if "tags" in result:
            result["tags"] = WellnessService._clean_keys(result["tags"])
        return result

    async def create_activity(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one user-owned activity document."""
        try:
            await self._ensure_seed_data(user_id)
            activity_id = str(payload.get("id") or uuid4()).strip()
            if await find_activity_doc(self.activities_collection, user_id=user_id, activity_id=activity_id):
                return {"status": "error", "message": "Activity already exists", "data": None}
            if not str(payload.get("title") or payload.get("title_key") or "").strip():
                return {"status": "error", "message": "Activity title is required", "data": None}
            now = iso_utc(now_utc())
            document = {"id": activity_id, "user_id": user_id, "icon_key": "auto_awesome", "title_key": None, "title": None, "summary_key": None, "summary": None, "activity_reminder": None, "duration_minutes": 0, "favorite": False, "harmful": False, "category_keys": await self._validate_category_keys(user_id, payload.get("category_keys")), "tags": [], "sort_order": 0, "energy_impact": None, "created_at": now, "updated_at": now, **self._activity_patch(payload)}
            await self.activities_collection.insert_one(document)
            return {"status": "success", "message": "Activity created successfully", "data": normalize_document(document)}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity: {str(exc)}", "data": None}

    async def update_activity(self, user_id: str, activity_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Update one activity for the requested user."""
        try:
            await self._ensure_seed_data(user_id)
            existing = await find_activity_doc(self.activities_collection, user_id=user_id, activity_id=activity_id)
            if existing is None:
                return {"status": "error", "message": "Activity not found", "data": None}
            update_payload: Dict[str, Any] = {**self._activity_patch(patch), "updated_at": iso_utc(now_utc())}
            if "category_keys" in patch:
                update_payload["category_keys"] = await self._validate_category_keys(user_id, patch["category_keys"])
            await self.activities_collection.update_one({"user_id": user_id, "id": activity_id}, {"$set": update_payload})
            updated = await find_activity_doc(self.activities_collection, user_id=user_id, activity_id=activity_id)
            return {"status": "success", "message": "Activity updated successfully", "data": updated}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity: {str(exc)}", "data": None}

    async def delete_activity(self, user_id: str, activity_id: str) -> Dict[str, Any]:
        """Delete one activity document idempotently."""
        try:
            await self._record_tombstone(user_id, "wellness_activity", activity_id)
            await self.activities_collection.delete_one({"user_id": user_id, "id": activity_id})
            return {"status": "success", "message": "Activity deleted successfully", "data": {"id": activity_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting activity: {str(exc)}", "data": None}

    async def create_activity_category(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one persisted activity category document."""
        try:
            await self._ensure_seed_data(user_id)
            key = str(payload.get("key") or uuid4()).strip()
            if await self.categories_collection.find_one({"user_id": user_id, "key": key}):
                return {"status": "error", "message": "Activity category already exists", "data": None}
            if not str(payload.get("title") or payload.get("title_key") or "").strip():
                return {"status": "error", "message": "Activity category title is required", "data": None}
            now = iso_utc(now_utc())
            document = {"user_id": user_id, "key": key, "title_key": payload.get("title_key"), "title": payload.get("title"), "description_key": payload.get("description_key"), "description": payload.get("description"), "icon_key": payload.get("icon_key") or "category", "sort_order": int(payload.get("sort_order") or 0), "item_count": 0, "created_at": now, "updated_at": now}
            await self.categories_collection.insert_one(document)
            return {"status": "success", "message": "Activity category created successfully", "data": normalize_document(document)}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity category: {str(exc)}", "data": None}

    async def update_activity_category(self, user_id: str, category_key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Patch one persisted activity category document."""
        try:
            supported = {"title_key", "title", "description_key", "description", "icon_key", "sort_order"}
            update = {key: value for key, value in patch.items() if key in supported}
            if update.get("icon_key") is None:
                update.pop("icon_key", None)
            update["updated_at"] = iso_utc(now_utc())
            result = await self.categories_collection.update_one({"user_id": user_id, "key": category_key}, {"$set": update})
            if result.matched_count == 0:
                return {"status": "error", "message": "Activity category not found", "data": None}
            document = await self.categories_collection.find_one({"user_id": user_id, "key": category_key}, {"_id": 0, "user_id": 0})
            return {"status": "success", "message": "Activity category updated successfully", "data": normalize_document(document)}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity category: {str(exc)}", "data": None}

    async def delete_activity_category(self, user_id: str, category_key: str) -> Dict[str, Any]:
        """Delete one category only when no activity references it."""
        try:
            if await self.activities_collection.find_one({"user_id": user_id, "category_keys": category_key}, {"_id": 1}):
                return {"status": "error", "message": "Activity category is still in use", "data": None}
            await self._record_tombstone(user_id, "wellness_activity_category", category_key)
            await self.categories_collection.delete_one({"user_id": user_id, "key": category_key})
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
        """Create a new wellness check-in."""
        try:
            await self._ensure_seed_data(user_id)
            now = now_utc()
            occurred_at = parse_iso(recorded_at) if recorded_at else now
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "recorded_at": iso_utc(occurred_at),
                "mood_score": mood_score,
                "stress_score": stress_score,
                "energy_score": energy_score,
                "tag_keys": normalize_tag_keys(tag_keys or []),
                "metrics": normalize_metric_values(metrics),
                "activity_id": activity_id.strip() if isinstance(activity_id, str) and activity_id.strip() else None,
                "note": note.strip() if isinstance(note, str) and note.strip() else None,
                "created_at": iso_utc(now),
                "updated_at": iso_utc(now),
            }
            await self.checkins_collection.insert_one(payload)
            return {"status": "success", "message": "Check-in created successfully", "data": build_latest_checkin_payload(payload)}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating check-in: {str(exc)}", "data": None}

    async def update_checkin(
        self,
        user_id: str,
        checkin_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one existing check-in document.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.
            patch (Dict[str, Any]): Mutable check-in fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            existing = await self.checkins_collection.find_one(
                {"user_id": user_id, "id": checkin_id},
                {"_id": 0},
            )
            if existing is None:
                return {"status": "error", "message": "Check-in not found", "data": None}

            update_payload: Dict[str, Any] = {"updated_at": iso_utc(now_utc())}
            if patch.get("recorded_at"):
                update_payload["recorded_at"] = iso_utc(parse_iso(str(patch["recorded_at"])))
            for field in ("mood_score", "stress_score", "energy_score"):
                if field in patch and patch[field] is not None:
                    update_payload[field] = int(patch[field])
            if "note" in patch:
                note = patch["note"]
                update_payload["note"] = note.strip() if isinstance(note, str) and note.strip() else None
            if "activity_id" in patch:
                activity_id = patch["activity_id"]
                update_payload["activity_id"] = activity_id.strip() if isinstance(activity_id, str) and activity_id.strip() else None
            if isinstance(patch.get("tag_keys"), list):
                update_payload["tag_keys"] = normalize_tag_keys([str(item) for item in patch["tag_keys"]])
            if isinstance(patch.get("metrics"), dict):
                update_payload["metrics"] = normalize_metric_values(patch["metrics"])

            await self.checkins_collection.update_one(
                {"user_id": user_id, "id": checkin_id},
                {"$set": update_payload},
            )
            updated = await self.checkins_collection.find_one(
                {"user_id": user_id, "id": checkin_id},
                {"_id": 0},
            )
            return {"status": "success", "message": "Check-in updated successfully", "data": updated}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating check-in: {str(exc)}", "data": None}

    async def delete_checkin(self, user_id: str, checkin_id: str) -> Dict[str, Any]:
        """Delete one existing check-in document.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            result = await self.checkins_collection.delete_one(
                {"user_id": user_id, "id": checkin_id},
            )
            if result.deleted_count == 0:
                return {"status": "error", "message": "Check-in not found", "data": None}
            await self._record_tombstone(user_id, "wellness_checkin", checkin_id)
            return {"status": "success", "message": "Check-in deleted successfully", "data": {"id": checkin_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting check-in: {str(exc)}", "data": None}

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """Return the most recent diary entries for the requested user."""
        try:
            await self._ensure_seed_data(user_id)
            diary_docs = await self.diary_collection.find(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("created_at", -1)],
            ).to_list(length=limit)
            items = []
            for doc in diary_docs:
                items.append(await build_diary_item(self.activities_collection, user_id=user_id, entry=doc))
            return {"status": "success", "data": {"items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading diary entries: {str(exc)}", "data": None}

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new diary entry."""
        try:
            await self._ensure_seed_data(user_id)
            related_activity = await find_activity_doc(self.activities_collection, user_id=user_id, activity_id=related_activity_id)
            if related_activity_id and related_activity is None:
                return {"status": "error", "message": "Related activity not found", "data": None}

            now = now_utc()
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "title": title.strip(),
                "summary": summary.strip(),
                "title_key": None,
                "summary_key": None,
                "mood_state_key": metric_state_key("mood", mood_score),
                "mood_score": mood_score,
                "tag_keys": normalize_tag_keys(tag_keys),
                "related_activity_id": related_activity_id,
                "created_at": iso_utc(now),
                "updated_at": iso_utc(now),
            }
            await self.diary_collection.insert_one(payload)
            created = await build_diary_item(self.activities_collection, user_id=user_id, entry=payload)
            return {"status": "success", "message": "Diary entry created successfully", "data": created}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating diary entry: {str(exc)}", "data": None}

    async def update_diary_entry(
        self,
        user_id: str,
        entry_id: str,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update one existing diary entry document.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.
            patch (Dict[str, Any]): Mutable diary fields to replace.

        Returns:
            Dict[str, Any]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            existing = await self.diary_collection.find_one(
                {"user_id": user_id, "id": entry_id},
                {"_id": 0},
            )
            if existing is None:
                return {"status": "error", "message": "Diary entry not found", "data": None}

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
                normalized_activity_id = related_activity_id.strip() if isinstance(related_activity_id, str) and related_activity_id.strip() else None
                if normalized_activity_id and await find_activity_doc(self.activities_collection, user_id=user_id, activity_id=normalized_activity_id) is None:
                    return {"status": "error", "message": "Related activity not found", "data": None}
                update_payload["related_activity_id"] = normalized_activity_id

            await self.diary_collection.update_one(
                {"user_id": user_id, "id": entry_id},
                {"$set": update_payload},
            )
            updated = await self.diary_collection.find_one(
                {"user_id": user_id, "id": entry_id},
                {"_id": 0},
            )
            payload = await build_diary_item(self.activities_collection, user_id=user_id, entry=updated)
            return {"status": "success", "message": "Diary entry updated successfully", "data": payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating diary entry: {str(exc)}", "data": None}

    async def delete_diary_entry(self, user_id: str, entry_id: str) -> Dict[str, Any]:
        """Delete one existing diary entry document.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.

        Returns:
            Dict[str, Any]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            result = await self.diary_collection.delete_one(
                {"user_id": user_id, "id": entry_id},
            )
            if result.deleted_count == 0:
                return {"status": "error", "message": "Diary entry not found", "data": None}
            await self._record_tombstone(user_id, "wellness_diary_entry", entry_id)
            return {"status": "success", "message": "Diary entry deleted successfully", "data": {"id": entry_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting diary entry: {str(exc)}", "data": None}
