"""MongoDB-backed wellness content service for dashboard, activities, and diary."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.database import get_database_handler
from backend.database.mongodb_handler import MongoDBHandler


class WellnessService:
    """Service for MongoDB wellness content operations."""

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

    def __init__(self):
        handler = get_database_handler()
        if not isinstance(handler, MongoDBHandler):
            raise ValueError("MongoDB WellnessService requires MongoDB database")

        self.handler = handler
        self.activities_collection = handler.database["wellness_activities"]
        self.diary_collection = handler.database["wellness_diary_entries"]
        self.checkins_collection = handler.database["wellness_checkins"]
        self.operation_log_collection = handler.database["sync_operation_log"]
        self.conflict_log_collection = handler.database["sync_conflicts"]
        self._indexes_initialized = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_initialized:
            return

        await self.activities_collection.create_index(
            [("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_activities_user_id_id"
        )
        await self.activities_collection.create_index(
            [("user_id", 1), ("favorite", 1)], name="idx_wellness_activities_user_favorite"
        )
        await self.diary_collection.create_index(
            [("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_diary_user_id_id"
        )
        await self.diary_collection.create_index(
            [("user_id", 1), ("created_at", -1)], name="idx_wellness_diary_user_created_at"
        )
        await self.checkins_collection.create_index(
            [("user_id", 1), ("id", 1)], unique=True, name="idx_wellness_checkins_user_id_id"
        )
        await self.checkins_collection.create_index(
            [("user_id", 1), ("recorded_at", -1)], name="idx_wellness_checkins_user_recorded_at"
        )
        self._indexes_initialized = True

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _iso(cls, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @classmethod
    def _metric_state_key(cls, metric: str, score: int) -> str:
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
    def _normalize_document(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        data = dict(doc)
        data.pop("_id", None)
        return data

    @staticmethod
    def _normalize_tag_keys(tag_keys: List[str]) -> List[str]:
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

    async def _purge_legacy_seed_data(self, user_id: str) -> None:
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
        if checkin_docs and self._looks_like_legacy_seed_checkins(checkin_docs):
            await self.checkins_collection.delete_many({"user_id": user_id})

    def _looks_like_legacy_seed_checkins(self, checkin_docs: List[Dict[str, Any]]) -> bool:
        if len(checkin_docs) > 7:
            return False

        for item in checkin_docs:
            if item.get("note") not in (None, ""):
                return False

            recorded_at_raw = item.get("recorded_at")
            created_at_raw = item.get("created_at")
            updated_at_raw = item.get("updated_at")
            if not recorded_at_raw or not created_at_raw or not updated_at_raw:
                return False

            try:
                recorded_at = self._parse_iso(str(recorded_at_raw)).astimezone(timezone.utc)
                created_at = self._parse_iso(str(created_at_raw)).astimezone(timezone.utc)
                updated_at = self._parse_iso(str(updated_at_raw)).astimezone(timezone.utc)
            except Exception:
                return False

            if (
                recorded_at.hour != 8
                or recorded_at.minute != 30
                or recorded_at.second != 0
                or created_at != recorded_at
                or updated_at != recorded_at
            ):
                return False

        return True

    async def _find_activity_doc(self, user_id: str, activity_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not activity_id:
            return None
        return await self.activities_collection.find_one(
            {"user_id": user_id, "id": activity_id},
            {"_id": 0},
        )

    async def _build_diary_item(self, user_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        item = self._normalize_document(doc) or {}
        related_activity = await self._find_activity_doc(user_id, item.get("related_activity_id"))
        item["related_activity_title_key"] = (
            related_activity.get("title_key") if related_activity else None
        )
        item["related_activity_title"] = (
            related_activity.get("title") if related_activity else None
        )
        return item

    async def _build_sync_change(
        self,
        *,
        user_id: str,
        entity_type: str,
        doc: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = self._normalize_document(doc) or {}
        payload = normalized
        if entity_type == "wellness_diary_entry":
            payload = await self._build_diary_item(user_id, normalized)

        return {
            "entity_type": entity_type,
            "entity_id": normalized.get("id", ""),
            "action": "upsert",
            "updated_at": normalized.get("updated_at") or normalized.get("created_at"),
            "payload": payload,
        }

    async def _ensure_seed_data(self, user_id: str) -> None:
        await self._ensure_indexes()
        await self._purge_legacy_seed_data(user_id)

        if await self.activities_collection.find_one({"user_id": user_id}, {"_id": 1}):
            return

        now = self._now_utc().replace(hour=9, minute=0, second=0, microsecond=0)
        activities = [
            {
                "id": "breathe-reset",
                "user_id": user_id,
                "icon_key": "air",
                "title_key": "app_shell.activities.seed_breathe_title",
                "summary_key": "app_shell.activities.seed_breathe_summary",
                "duration_minutes": 1,
                "favorite": True,
                "category_keys": ["calm", "focus"],
                "energy_impact": "reset",
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            },
            {
                "id": "clarity-journal",
                "user_id": user_id,
                "icon_key": "book",
                "title_key": "app_shell.activities.seed_journal_title",
                "summary_key": "app_shell.activities.seed_journal_summary",
                "duration_minutes": 8,
                "favorite": True,
                "category_keys": ["focus"],
                "energy_impact": "grounding",
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            },
            {
                "id": "soft-stretch",
                "user_id": user_id,
                "icon_key": "self_improvement",
                "title_key": "app_shell.activities.seed_stretch_title",
                "summary_key": "app_shell.activities.seed_stretch_summary",
                "duration_minutes": 6,
                "favorite": False,
                "category_keys": ["energy", "calm"],
                "energy_impact": "lift",
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            },
            {
                "id": "focus-walk",
                "user_id": user_id,
                "icon_key": "directions_walk",
                "title_key": "app_shell.activities.seed_walk_title",
                "summary_key": "app_shell.activities.seed_walk_summary",
                "duration_minutes": 12,
                "favorite": False,
                "category_keys": ["energy", "focus"],
                "energy_impact": "lift",
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            },
            {
                "id": "pause-and-tea",
                "user_id": user_id,
                "icon_key": "local_cafe",
                "title_key": "app_shell.activities.seed_tea_title",
                "summary_key": "app_shell.activities.seed_tea_summary",
                "duration_minutes": 10,
                "favorite": False,
                "category_keys": ["calm"],
                "energy_impact": "ease",
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            },
        ]
        await self.activities_collection.insert_many(activities)
        # Keep the starter activity catalog available for each authenticated user,
        # but do not fabricate diary history or wellness check-ins.

    async def reset_user_data(
        self,
        user_id: str,
        *,
        keep_activity_catalog: bool = True,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_indexes()

            diary_result = await self.diary_collection.delete_many({"user_id": user_id})
            checkin_result = await self.checkins_collection.delete_many({"user_id": user_id})
            operation_log_result = await self.operation_log_collection.delete_many({"user_id": user_id})
            conflict_log_result = await self.conflict_log_collection.delete_many({"user_id": user_id})

            activity_count = 0
            if keep_activity_catalog:
                await self.activities_collection.delete_many({"user_id": user_id})
                await self._ensure_seed_data(user_id)
                activity_count = await self.activities_collection.count_documents({"user_id": user_id})
            else:
                await self.activities_collection.delete_many({"user_id": user_id})

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
            return {
                "status": "error",
                "message": f"Error resetting wellness data: {str(exc)}",
                "data": None,
            }
    async def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            latest_doc = await self.checkins_collection.find_one(
                {"user_id": user_id},
                sort=[("recorded_at", -1)],
            )
            latest = self._normalize_document(latest_doc)

            trend_docs = await self.checkins_collection.find(
                {"user_id": user_id},
                {"_id": 0, "recorded_at": 1, "mood_score": 1},
            ).to_list(length=90)

            trend_by_date: Dict[date, List[int]] = {}
            for item in trend_docs:
                recorded_at = self._parse_iso(item["recorded_at"]).astimezone(timezone.utc).date()
                trend_by_date.setdefault(recorded_at, []).append(int(item.get("mood_score") or 0))

            today = self._now_utc().date()
            weekly_trend = []
            for offset in range(6, -1, -1):
                target_day = today - timedelta(days=offset)
                mood_values = trend_by_date.get(target_day, [])
                value = round(sum(mood_values) / len(mood_values), 1) if mood_values else None
                weekly_trend.append(
                    {
                        "day_key": self._WEEKDAY_KEYS[target_day.weekday()],
                        "value": value,
                    }
                )

            latest_payload = None
            if latest is not None:
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

            return {
                "status": "success",
                "data": {
                    "latest_checkin": latest_payload,
                    "weekly_trend": weekly_trend,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error loading dashboard: {str(exc)}",
                "data": None,
            }

    async def list_activities(self, user_id: str) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            activity_docs = await self.activities_collection.find(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("favorite", -1), ("duration_minutes", 1), ("title_key", 1)],
            ).to_list(length=200)

            activities = [self._normalize_document(doc) for doc in activity_docs]
            activities = [item for item in activities if item is not None]

            categories = []
            for category_key, definition in self._CATEGORY_DEFINITIONS.items():
                count = sum(1 for item in activities if category_key in item.get("category_keys", []))
                categories.append(
                    {
                        "key": category_key,
                        "title_key": definition["title_key"],
                        "description_key": definition["description_key"],
                        "item_count": count,
                    }
                )

            return {
                "status": "success",
                "data": {
                    "categories": categories,
                    "items": activities,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error loading activities: {str(exc)}",
                "data": None,
            }


    async def get_sync_bootstrap(
        self,
        user_id: str,
        diary_limit: int = 50,
        checkin_limit: int = 50,
    ) -> Dict[str, Any]:
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
            checkins = [self._normalize_document(doc) for doc in checkin_docs]
            checkins = [item for item in checkins if item is not None]

            return {
                "status": "success",
                "data": {
                    "server_timestamp": self._iso(self._now_utc()),
                    "activities": activities_result["data"]["items"],
                    "diary_entries": diary_result["data"]["items"],
                    "checkins": checkins,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error loading sync bootstrap: {str(exc)}",
                "data": None,
            }

    async def get_sync_changes(
        self,
        user_id: str,
        cursor: Optional[str] = None,
        limit: int = 100,
        entity_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            allowed_entity_types = {
                "wellness_activity": self.activities_collection,
                "wellness_diary_entry": self.diary_collection,
                "wellness_checkin": self.checkins_collection,
            }
            if entity_type and entity_type not in allowed_entity_types:
                return {
                    "status": "error",
                    "message": f"Unsupported entity_type: {entity_type}",
                    "data": None,
                }

            cursor_filter: Dict[str, Any] = {}
            if cursor:
                cursor_filter["updated_at"] = {"$gt": cursor}

            changes: List[Dict[str, Any]] = []
            selected_types = (
                [entity_type] if entity_type else list(allowed_entity_types.keys())
            )
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
                        await self._build_sync_change(
                            user_id=user_id,
                            entity_type=selected_type,
                            doc=doc,
                        )
                    )

            changes.sort(
                key=lambda item: (
                    item.get("updated_at") or "",
                    item.get("entity_type") or "",
                    item.get("entity_id") or "",
                )
            )
            selected_changes = changes[:limit]
            next_cursor = selected_changes[-1]["updated_at"] if selected_changes else cursor
            has_more = len(changes) > limit

            return {
                "status": "success",
                "data": {
                    "server_timestamp": self._iso(self._now_utc()),
                    "changes": selected_changes,
                    "next_cursor": next_cursor,
                    "has_more": has_more,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error loading sync changes: {str(exc)}",
                "data": None,
            }
    async def update_activity(
        self,
        user_id: str,
        activity_id: str,
        favorite: Optional[bool] = None,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            existing = await self._find_activity_doc(user_id, activity_id)
            if existing is None:
                return {
                    "status": "error",
                    "message": "Activity not found",
                    "data": None,
                }

            update_payload: Dict[str, Any] = {"updated_at": self._iso(self._now_utc())}
            if favorite is not None:
                update_payload["favorite"] = favorite

            await self.activities_collection.update_one(
                {"user_id": user_id, "id": activity_id},
                {"$set": update_payload},
            )
            updated = await self._find_activity_doc(user_id, activity_id)
            return {
                "status": "success",
                "message": "Activity updated successfully",
                "data": updated,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error updating activity: {str(exc)}",
                "data": None,
            }

    async def create_checkin(
        self,
        user_id: str,
        mood_score: int,
        stress_score: int,
        energy_score: int,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            now = self._now_utc()
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "recorded_at": self._iso(now),
                "mood_score": mood_score,
                "stress_score": stress_score,
                "energy_score": energy_score,
                "note": note.strip() if isinstance(note, str) and note.strip() else None,
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            }
            await self.checkins_collection.insert_one(payload)
            latest_payload = {
                "recorded_at": payload["recorded_at"],
                "mood": {
                    "state_key": self._metric_state_key("mood", mood_score),
                    "score": mood_score,
                },
                "stress": {
                    "state_key": self._metric_state_key("stress", stress_score),
                    "score": stress_score,
                },
                "energy": {
                    "state_key": self._metric_state_key("energy", energy_score),
                    "score": energy_score,
                },
                "note": payload["note"],
            }
            return {
                "status": "success",
                "message": "Check-in created successfully",
                "data": latest_payload,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error creating check-in: {str(exc)}",
                "data": None,
            }

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            diary_docs = await self.diary_collection.find(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("created_at", -1)],
            ).to_list(length=limit)

            items = []
            for doc in diary_docs:
                items.append(await self._build_diary_item(user_id, doc))

            return {
                "status": "success",
                "data": {
                    "items": items,
                },
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error loading diary entries: {str(exc)}",
                "data": None,
            }

    async def create_diary_entry(
        self,
        user_id: str,
        title: str,
        summary: str,
        mood_score: int,
        tag_keys: List[str],
        related_activity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_seed_data(user_id)
            related_activity = await self._find_activity_doc(user_id, related_activity_id)
            if related_activity_id and related_activity is None:
                return {
                    "status": "error",
                    "message": "Related activity not found",
                    "data": None,
                }

            now = self._now_utc()
            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "title": title.strip(),
                "summary": summary.strip(),
                "title_key": None,
                "summary_key": None,
                "mood_state_key": self._metric_state_key("mood", mood_score),
                "mood_score": mood_score,
                "tag_keys": self._normalize_tag_keys(tag_keys),
                "related_activity_id": related_activity_id,
                "created_at": self._iso(now),
                "updated_at": self._iso(now),
            }
            await self.diary_collection.insert_one(payload)
            created = await self._build_diary_item(user_id, payload)
            return {
                "status": "success",
                "message": "Diary entry created successfully",
                "data": created,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Error creating diary entry: {str(exc)}",
                "data": None,
            }




