"""SQL-backed wellness content service for dashboard, activities, diary, and check-ins."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import and_, delete, select

from backend.database import get_database_handler
from backend.database.sql_handler import SQLHandler
from models.sql.sync_conflict_log import SyncConflictLog
from models.sql.sync_operation_log import SyncOperationLog
from models.sql.user import User
from models.sql.wellness import WellnessActivity, WellnessActivityCategory, WellnessCheckIn, WellnessDiaryEntry, WellnessSyncTombstone


class WellnessService:
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
        handler = get_database_handler()
        if not isinstance(handler, SQLHandler):
            raise ValueError("SQL WellnessService requires SQL database")
        self.handler = handler

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_dt(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _iso(cls, value: datetime) -> str:
        return cls._normalize_dt(value).isoformat().replace("+00:00", "Z")

    @classmethod
    def _parse_iso(cls, value: str) -> datetime:
        return cls._normalize_dt(datetime.fromisoformat(value.replace("Z", "+00:00")))

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

    @staticmethod
    def _normalize_metric_values(metrics: Optional[Dict[str, int]]) -> Dict[str, int]:
        """Normalize flexible metric values before persistence.

        Args:
            metrics (Optional[Dict[str, int]]): Raw metric map from a request or
                sync operation.

        Returns:
            Dict[str, int]: Metric values keyed by non-empty identifiers and
            clamped to the inclusive 0-10 wellness scale.

        Side Effects:
            None.
        """
        return {
            str(key).strip(): max(0, min(10, int(value)))
            for key, value in (metrics or {}).items()
            if str(key).strip()
        }

    @staticmethod
    def _optional_text(value: object) -> Optional[str]:
        """Normalize optional free-form text values.

        Args:
            value (object): Raw request value.

        Returns:
            Optional[str]: Trimmed text, or ``None`` when the value is empty.

        Side Effects:
            None.
        """
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    async def _ensure_user_exists(self, session, user_id: str) -> None:
        result = await session.execute(select(User.id).where(User.id == user_id))
        if result.scalar_one_or_none() is None:
            raise ValueError("User not found")

    def _starter_activities(self, user_id: str) -> List[WellnessActivity]:
        now = self._now_utc().replace(hour=9, minute=0, second=0, microsecond=0)
        payloads = [
            {"id": "breathe-reset", "icon_key": "air", "title_key": "app_shell.activities.seed_breathe_title", "summary_key": "app_shell.activities.seed_breathe_summary", "duration_minutes": 1, "favorite": True, "category_keys": ["calm", "focus"], "energy_impact": "reset"},
            {"id": "clarity-journal", "icon_key": "book", "title_key": "app_shell.activities.seed_journal_title", "summary_key": "app_shell.activities.seed_journal_summary", "duration_minutes": 8, "favorite": True, "category_keys": ["focus"], "energy_impact": "grounding"},
            {"id": "soft-stretch", "icon_key": "self_improvement", "title_key": "app_shell.activities.seed_stretch_title", "summary_key": "app_shell.activities.seed_stretch_summary", "duration_minutes": 6, "favorite": False, "category_keys": ["energy", "calm"], "energy_impact": "lift"},
            {"id": "focus-walk", "icon_key": "directions_walk", "title_key": "app_shell.activities.seed_walk_title", "summary_key": "app_shell.activities.seed_walk_summary", "duration_minutes": 12, "favorite": False, "category_keys": ["energy", "focus"], "energy_impact": "lift"},
            {"id": "pause-and-tea", "icon_key": "local_cafe", "title_key": "app_shell.activities.seed_tea_title", "summary_key": "app_shell.activities.seed_tea_summary", "duration_minutes": 10, "favorite": False, "category_keys": ["calm"], "energy_impact": "ease"},
        ]
        activities: List[WellnessActivity] = []
        for sort_order, item in enumerate(payloads):
            activity = WellnessActivity(
                user_id=user_id,
                id=item["id"],
                icon_key=item["icon_key"],
                title_key=item["title_key"],
                title=None,
                summary_key=item["summary_key"],
                summary=None,
                duration_minutes=item["duration_minutes"],
                favorite=item["favorite"],
                harmful=False,
                sort_order=sort_order,
                energy_impact=item["energy_impact"],
                created_at=now,
                updated_at=now,
            )
            activity.category_keys = list(item["category_keys"])
            activities.append(activity)
        return activities

    def _starter_categories(self, user_id: str) -> List[WellnessActivityCategory]:
        """Build the default persisted category rows for a user.

        Args:
            user_id (str): Owner identifier applied to every category.

        Returns:
            List[WellnessActivityCategory]: Ordered default category rows.
        """
        return [
            WellnessActivityCategory(
                user_id=user_id,
                key=key,
                title_key=definition["title_key"],
                title=None,
                description_key=definition["description_key"],
                description=None,
                icon_key={"calm": "self_improvement", "focus": "center_focus_strong", "energy": "bolt"}.get(key, "category"),
                sort_order=sort_order,
            )
            for sort_order, (key, definition) in enumerate(self._CATEGORY_DEFINITIONS.items())
        ]

    async def _ensure_seed_data(self, user_id: str) -> None:
        async with self.handler.AsyncSessionLocal() as session:
            await self._ensure_user_exists(session, user_id)
            existing = await session.execute(select(WellnessActivity.pk).where(WellnessActivity.user_id == user_id).limit(1))
            if existing.scalar_one_or_none() is None:
                session.add_all(self._starter_activities(user_id))
            existing_category = await session.execute(select(WellnessActivityCategory.pk).where(WellnessActivityCategory.user_id == user_id).limit(1))
            if existing_category.scalar_one_or_none() is None:
                session.add_all(self._starter_categories(user_id))
            await session.commit()

    async def _find_activity(self, session, user_id: str, activity_id: Optional[str]) -> Optional[WellnessActivity]:
        if not activity_id:
            return None
        result = await session.execute(select(WellnessActivity).where(and_(WellnessActivity.user_id == user_id, WellnessActivity.id == activity_id)))
        return result.scalar_one_or_none()

    async def _find_category(self, session, user_id: str, category_key: Optional[str]) -> Optional[WellnessActivityCategory]:
        """Find one category scoped to a user."""
        if not category_key:
            return None
        result = await session.execute(select(WellnessActivityCategory).where(and_(WellnessActivityCategory.user_id == user_id, WellnessActivityCategory.key == category_key)))
        return result.scalar_one_or_none()

    async def _record_tombstone(self, session, user_id: str, entity_type: str, entity_id: str) -> None:
        """Create or refresh an incremental deletion marker."""
        result = await session.execute(select(WellnessSyncTombstone).where(and_(WellnessSyncTombstone.user_id == user_id, WellnessSyncTombstone.entity_type == entity_type, WellnessSyncTombstone.entity_id == entity_id)))
        tombstone = result.scalar_one_or_none()
        if tombstone is None:
            session.add(WellnessSyncTombstone(user_id=user_id, entity_type=entity_type, entity_id=entity_id, deleted_at=self._now_utc()))
        else:
            tombstone.deleted_at = self._now_utc()

    @staticmethod
    def _clean_keys(values: object) -> List[str]:
        """Normalize a sequence of stable keys while preserving order."""
        if not isinstance(values, list):
            return []
        cleaned: List[str] = []
        for value in values:
            key = str(value).strip()
            if key and key not in cleaned:
                cleaned.append(key)
        return cleaned

    async def _validate_category_keys(self, session, user_id: str, values: object) -> List[str]:
        """Return normalized category keys or raise for missing categories."""
        keys = self._clean_keys(values)
        if not keys:
            raise ValueError("Activity requires at least one category")
        result = await session.execute(select(WellnessActivityCategory.key).where(and_(WellnessActivityCategory.user_id == user_id, WellnessActivityCategory.key.in_(keys))))
        existing = set(result.scalars().all())
        missing = [key for key in keys if key not in existing]
        if missing:
            raise ValueError(f"Unknown activity categories: {', '.join(missing)}")
        return keys

    def _apply_activity_patch(self, activity: WellnessActivity, patch: Dict[str, object]) -> None:
        """Apply normalized mutable catalogue fields to an activity row."""
        for field in ("title_key", "title", "summary_key", "summary", "activity_reminder", "energy_impact"):
            if field in patch:
                setattr(activity, field, self._optional_text(patch.get(field)))
        if "icon_key" in patch and self._optional_text(patch.get("icon_key")):
            activity.icon_key = self._optional_text(patch.get("icon_key")) or activity.icon_key
        if "duration_minutes" in patch:
            activity.duration_minutes = max(0, int(patch["duration_minutes"]))
        if "favorite" in patch:
            activity.favorite = bool(patch["favorite"])
        if "harmful" in patch:
            activity.harmful = bool(patch["harmful"])
        if "sort_order" in patch:
            activity.sort_order = int(patch["sort_order"])
        if "tags" in patch:
            activity.tags = self._clean_keys(patch["tags"])

    async def _build_diary_item(self, session, user_id: str, entry: WellnessDiaryEntry) -> Dict[str, object]:
        item = entry.to_dict()
        related_activity = await self._find_activity(session, user_id, item.get("related_activity_id"))
        item["related_activity_title_key"] = related_activity.title_key if related_activity else None
        item["related_activity_title"] = related_activity.title if related_activity else None
        return item

    async def _build_sync_change(self, *, session, user_id: str, entity_type: str, payload) -> Dict[str, object]:
        normalized = payload.to_dict()
        if entity_type == "wellness_diary_entry":
            normalized = await self._build_diary_item(session, user_id, payload)
        return {
            "entity_type": entity_type,
            "entity_id": normalized.get("id") or normalized.get("key", ""),
            "action": "upsert",
            "updated_at": normalized.get("updated_at") or normalized.get("created_at"),
            "payload": normalized,
        }

    async def reset_user_data(self, user_id: str, *, keep_activity_catalog: bool = True) -> Dict[str, object]:
        try:
            async with self.handler.AsyncSessionLocal() as session:
                await self._ensure_user_exists(session, user_id)
                diary_result = await session.execute(delete(WellnessDiaryEntry).where(WellnessDiaryEntry.user_id == user_id))
                checkin_result = await session.execute(delete(WellnessCheckIn).where(WellnessCheckIn.user_id == user_id))
                operation_log_result = await session.execute(delete(SyncOperationLog).where(SyncOperationLog.user_id == user_id))
                conflict_log_result = await session.execute(delete(SyncConflictLog).where(SyncConflictLog.user_id == user_id))
                await session.execute(delete(WellnessActivity).where(WellnessActivity.user_id == user_id))
                await session.execute(delete(WellnessActivityCategory).where(WellnessActivityCategory.user_id == user_id))
                await session.execute(delete(WellnessSyncTombstone).where(WellnessSyncTombstone.user_id == user_id))
                await session.commit()
            activity_count = 0
            if keep_activity_catalog:
                await self._ensure_seed_data(user_id)
                async with self.handler.AsyncSessionLocal() as session:
                    count_result = await session.execute(select(WellnessActivity).where(WellnessActivity.user_id == user_id))
                    activity_count = len(count_result.scalars().all())
            return {"status": "success", "message": "Wellness data reset successfully", "data": {"activities": activity_count, "deleted_diary_entries": int(diary_result.rowcount or 0), "deleted_checkins": int(checkin_result.rowcount or 0), "deleted_sync_operation_logs": int(operation_log_result.rowcount or 0), "deleted_sync_conflicts": int(conflict_log_result.rowcount or 0)}}
        except Exception as exc:
            return {"status": "error", "message": f"Error resetting wellness data: {str(exc)}", "data": None}

    async def get_dashboard(self, user_id: str) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                latest_result = await session.execute(select(WellnessCheckIn).where(WellnessCheckIn.user_id == user_id).order_by(WellnessCheckIn.recorded_at.desc()).limit(1))
                latest = latest_result.scalar_one_or_none()
                trend_result = await session.execute(select(WellnessCheckIn).where(WellnessCheckIn.user_id == user_id).order_by(WellnessCheckIn.recorded_at.desc()).limit(90))
                trend_docs = trend_result.scalars().all()
                trend_by_date: Dict[date, List[int]] = {}
                for item in trend_docs:
                    recorded_at = self._normalize_dt(item.recorded_at).date()
                    trend_by_date.setdefault(recorded_at, []).append(int(item.mood_score or 0))
                today = self._now_utc().date()
                weekly_trend = []
                for offset in range(6, -1, -1):
                    target_day = today - timedelta(days=offset)
                    mood_values = trend_by_date.get(target_day, [])
                    value = round(sum(mood_values) / len(mood_values), 1) if mood_values else None
                    weekly_trend.append({"day_key": self._WEEKDAY_KEYS[target_day.weekday()], "value": value})
                latest_payload = None
                if latest is not None:
                    latest_payload = {"recorded_at": self._iso(latest.recorded_at), "mood": {"state_key": self._metric_state_key("mood", int(latest.mood_score or 0)), "score": int(latest.mood_score or 0)}, "stress": {"state_key": self._metric_state_key("stress", int(latest.stress_score or 0)), "score": int(latest.stress_score or 0)}, "energy": {"state_key": self._metric_state_key("energy", int(latest.energy_score or 0)), "score": int(latest.energy_score or 0)}, "note": latest.note}
                return {"status": "success", "data": {"latest_checkin": latest_payload, "weekly_trend": weekly_trend}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading dashboard: {str(exc)}", "data": None}

    async def list_activities(self, user_id: str) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(select(WellnessActivity).where(WellnessActivity.user_id == user_id).order_by(WellnessActivity.favorite.desc(), WellnessActivity.sort_order.asc(), WellnessActivity.title_key.asc()))
                activities = [item.to_dict() for item in result.scalars().all()]
                category_result = await session.execute(select(WellnessActivityCategory).where(WellnessActivityCategory.user_id == user_id).order_by(WellnessActivityCategory.sort_order.asc(), WellnessActivityCategory.key.asc()))
                categories = [category.to_dict(item_count=sum(1 for item in activities if category.key in item.get("category_keys", []))) for category in category_result.scalars().all()]
                return {"status": "success", "data": {"categories": categories, "items": activities}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading activities: {str(exc)}", "data": None}

    async def get_sync_bootstrap(self, user_id: str, diary_limit: int = 50, checkin_limit: int = 50) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                activity_result = await session.execute(select(WellnessActivity).where(WellnessActivity.user_id == user_id).order_by(WellnessActivity.favorite.desc(), WellnessActivity.sort_order.asc(), WellnessActivity.title_key.asc()))
                activities = [item.to_dict() for item in activity_result.scalars().all()]
                category_result = await session.execute(select(WellnessActivityCategory).where(WellnessActivityCategory.user_id == user_id).order_by(WellnessActivityCategory.sort_order.asc(), WellnessActivityCategory.key.asc()))
                categories = [item.to_dict() for item in category_result.scalars().all()]
                diary_result = await session.execute(select(WellnessDiaryEntry).where(WellnessDiaryEntry.user_id == user_id).order_by(WellnessDiaryEntry.created_at.desc()).limit(diary_limit))
                diary_entries = [await self._build_diary_item(session, user_id, entry) for entry in diary_result.scalars().all()]
                checkin_result = await session.execute(select(WellnessCheckIn).where(WellnessCheckIn.user_id == user_id).order_by(WellnessCheckIn.recorded_at.desc()).limit(checkin_limit))
                checkins = [item.to_dict() for item in checkin_result.scalars().all()]
                return {"status": "success", "data": {"server_timestamp": self._iso(self._now_utc()), "activity_categories": categories, "activities": activities, "diary_entries": diary_entries, "checkins": checkins}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync bootstrap: {str(exc)}", "data": None}

    async def get_sync_changes(self, user_id: str, cursor: Optional[str] = None, limit: int = 100, entity_type: Optional[str] = None) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            allowed_entity_types = {"wellness_activity": WellnessActivity, "wellness_activity_category": WellnessActivityCategory, "wellness_diary_entry": WellnessDiaryEntry, "wellness_checkin": WellnessCheckIn}
            if entity_type and entity_type not in allowed_entity_types:
                return {"status": "error", "message": f"Unsupported entity_type: {entity_type}", "data": None}
            cursor_dt = self._parse_iso(cursor) if cursor else None
            selected_types = [entity_type] if entity_type else list(allowed_entity_types.keys())
            query_limit = max(limit * 2, 100)
            changes: List[Dict[str, object]] = []
            async with self.handler.AsyncSessionLocal() as session:
                for selected_type in selected_types:
                    model = allowed_entity_types[selected_type]
                    filters = [model.user_id == user_id]
                    if cursor_dt is not None:
                        filters.append(model.updated_at > cursor_dt)
                    identity_column = model.key if selected_type == "wellness_activity_category" else model.id
                    result = await session.execute(select(model).where(and_(*filters)).order_by(model.updated_at.asc(), identity_column.asc()).limit(query_limit))
                    for item in result.scalars().all():
                        changes.append(await self._build_sync_change(session=session, user_id=user_id, entity_type=selected_type, payload=item))
                tombstone_filters = [WellnessSyncTombstone.user_id == user_id]
                if entity_type:
                    tombstone_filters.append(WellnessSyncTombstone.entity_type == entity_type)
                if cursor_dt is not None:
                    tombstone_filters.append(WellnessSyncTombstone.deleted_at > cursor_dt)
                tombstones = await session.execute(select(WellnessSyncTombstone).where(and_(*tombstone_filters)).order_by(WellnessSyncTombstone.deleted_at.asc()).limit(query_limit))
                changes.extend(item.to_sync_change() for item in tombstones.scalars().all())
            changes.sort(key=lambda item: (item.get("updated_at") or "", item.get("entity_type") or "", item.get("entity_id") or ""))
            selected_changes = changes[:limit]
            next_cursor = selected_changes[-1]["updated_at"] if selected_changes else cursor
            return {"status": "success", "data": {"server_timestamp": self._iso(self._now_utc()), "changes": selected_changes, "next_cursor": next_cursor, "has_more": len(changes) > limit}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading sync changes: {str(exc)}", "data": None}

    async def create_activity(self, user_id: str, payload: Dict[str, object]) -> Dict[str, object]:
        """Create a user-owned activity and validate all category references."""
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                activity_id = str(payload.get("id") or uuid4()).strip()
                if await self._find_activity(session, user_id, activity_id) is not None:
                    return {"status": "error", "message": "Activity already exists", "data": None}
                title = self._optional_text(payload.get("title"))
                title_key = self._optional_text(payload.get("title_key"))
                if not title and not title_key:
                    return {"status": "error", "message": "Activity title is required", "data": None}
                category_keys = await self._validate_category_keys(session, user_id, payload.get("category_keys"))
                now = self._now_utc()
                activity = WellnessActivity(user_id=user_id, id=activity_id, icon_key=self._optional_text(payload.get("icon_key")) or "auto_awesome", title_key=title_key, title=title, summary_key=None, summary=None, duration_minutes=0, favorite=False, harmful=False, sort_order=0, created_at=now, updated_at=now)
                self._apply_activity_patch(activity, payload)
                activity.category_keys = category_keys
                session.add(activity)
                await session.commit()
                await session.refresh(activity)
                return {"status": "success", "message": "Activity created successfully", "data": activity.to_dict()}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity: {str(exc)}", "data": None}

    async def update_activity(self, user_id: str, activity_id: str, patch: Dict[str, object]) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                activity = await self._find_activity(session, user_id, activity_id)
                if activity is None:
                    return {"status": "error", "message": "Activity not found", "data": None}
                self._apply_activity_patch(activity, patch)
                if "category_keys" in patch:
                    activity.category_keys = await self._validate_category_keys(session, user_id, patch["category_keys"])
                activity.updated_at = self._now_utc()
                await session.commit()
                await session.refresh(activity)
                return {"status": "success", "message": "Activity updated successfully", "data": activity.to_dict()}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity: {str(exc)}", "data": None}

    async def delete_activity(self, user_id: str, activity_id: str) -> Dict[str, object]:
        """Delete one activity idempotently."""
        try:
            async with self.handler.AsyncSessionLocal() as session:
                activity = await self._find_activity(session, user_id, activity_id)
                await self._record_tombstone(session, user_id, "wellness_activity", activity_id)
                if activity is not None:
                    await session.delete(activity)
                await session.commit()
                return {"status": "success", "message": "Activity deleted successfully", "data": {"id": activity_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting activity: {str(exc)}", "data": None}

    async def create_activity_category(self, user_id: str, payload: Dict[str, object]) -> Dict[str, object]:
        """Create one persisted activity category."""
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                key = str(payload.get("key") or uuid4()).strip()
                if await self._find_category(session, user_id, key) is not None:
                    return {"status": "error", "message": "Activity category already exists", "data": None}
                title = self._optional_text(payload.get("title"))
                title_key = self._optional_text(payload.get("title_key"))
                if not title and not title_key:
                    return {"status": "error", "message": "Activity category title is required", "data": None}
                now = self._now_utc()
                category = WellnessActivityCategory(user_id=user_id, key=key, title_key=title_key, title=title, description_key=self._optional_text(payload.get("description_key")), description=self._optional_text(payload.get("description")), icon_key=self._optional_text(payload.get("icon_key")) or "category", sort_order=int(payload.get("sort_order") or 0), created_at=now, updated_at=now)
                session.add(category)
                await session.commit()
                await session.refresh(category)
                return {"status": "success", "message": "Activity category created successfully", "data": category.to_dict()}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating activity category: {str(exc)}", "data": None}

    async def update_activity_category(self, user_id: str, category_key: str, patch: Dict[str, object]) -> Dict[str, object]:
        """Patch one persisted activity category."""
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                category = await self._find_category(session, user_id, category_key)
                if category is None:
                    return {"status": "error", "message": "Activity category not found", "data": None}
                for field in ("title_key", "title", "description_key", "description"):
                    if field in patch:
                        setattr(category, field, self._optional_text(patch.get(field)))
                if "icon_key" in patch and self._optional_text(patch.get("icon_key")):
                    category.icon_key = self._optional_text(patch.get("icon_key")) or category.icon_key
                if "sort_order" in patch:
                    category.sort_order = int(patch["sort_order"])
                category.updated_at = self._now_utc()
                await session.commit()
                await session.refresh(category)
                return {"status": "success", "message": "Activity category updated successfully", "data": category.to_dict()}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating activity category: {str(exc)}", "data": None}

    async def delete_activity_category(self, user_id: str, category_key: str) -> Dict[str, object]:
        """Delete a category only when no activity still references it."""
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                activities = (await session.execute(select(WellnessActivity).where(WellnessActivity.user_id == user_id))).scalars().all()
                if any(category_key in activity.category_keys for activity in activities):
                    return {"status": "error", "message": "Activity category is still in use", "data": None}
                category = await self._find_category(session, user_id, category_key)
                await self._record_tombstone(session, user_id, "wellness_activity_category", category_key)
                if category is not None:
                    await session.delete(category)
                await session.commit()
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
    ) -> Dict[str, object]:
        """Create a check-in row with optional activity execution metadata.

        Args:
            user_id (str): Authenticated user identifier.
            mood_score (int): Legacy mood score for dashboard compatibility.
            stress_score (int): Legacy stress score for dashboard compatibility.
            energy_score (int): Legacy energy score for dashboard compatibility.
            note (Optional[str]): Optional user note.
            recorded_at (Optional[str]): Optional ISO occurrence timestamp.
            tag_keys (Optional[List[str]]): Semantic tags to store.
            metrics (Optional[Dict[str, int]]): Captured flexible metrics.
            activity_id (Optional[str]): Optional linked activity identifier.

        Returns:
            Dict[str, object]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                now = self._now_utc()
                occurred_at = self._parse_iso(recorded_at) if recorded_at else now
                checkin = WellnessCheckIn(user_id=user_id, id=str(uuid4()), recorded_at=occurred_at, mood_score=mood_score, stress_score=stress_score, energy_score=energy_score, note=note.strip() if isinstance(note, str) and note.strip() else None, activity_id=activity_id.strip() if isinstance(activity_id, str) and activity_id.strip() else None, created_at=now, updated_at=now)
                checkin.tag_keys = self._normalize_tag_keys(tag_keys or [])
                checkin.metrics = self._normalize_metric_values(metrics)
                session.add(checkin)
                await session.commit()
                latest_payload = {"recorded_at": self._iso(checkin.recorded_at), "mood": {"state_key": self._metric_state_key("mood", mood_score), "score": mood_score}, "stress": {"state_key": self._metric_state_key("stress", stress_score), "score": stress_score}, "energy": {"state_key": self._metric_state_key("energy", energy_score), "score": energy_score}, "note": checkin.note}
                return {"status": "success", "message": "Check-in created successfully", "data": latest_payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating check-in: {str(exc)}", "data": None}

    async def update_checkin(
        self,
        user_id: str,
        checkin_id: str,
        patch: Dict[str, object],
    ) -> Dict[str, object]:
        """Update one existing check-in row.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.
            patch (Dict[str, object]): Mutable check-in fields to replace.

        Returns:
            Dict[str, object]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(
                    select(WellnessCheckIn).where(
                        and_(
                            WellnessCheckIn.user_id == user_id,
                            WellnessCheckIn.id == checkin_id,
                        ),
                    ),
                )
                checkin = result.scalar_one_or_none()
                if checkin is None:
                    return {"status": "error", "message": "Check-in not found", "data": None}

                if "recorded_at" in patch and patch["recorded_at"]:
                    checkin.recorded_at = self._parse_iso(str(patch["recorded_at"]))
                if "mood_score" in patch and patch["mood_score"] is not None:
                    checkin.mood_score = int(patch["mood_score"])
                if "stress_score" in patch and patch["stress_score"] is not None:
                    checkin.stress_score = int(patch["stress_score"])
                if "energy_score" in patch and patch["energy_score"] is not None:
                    checkin.energy_score = int(patch["energy_score"])
                if "note" in patch:
                    checkin.note = self._optional_text(patch["note"])
                if "activity_id" in patch:
                    checkin.activity_id = self._optional_text(patch["activity_id"])
                if "tag_keys" in patch and isinstance(patch["tag_keys"], list):
                    checkin.tag_keys = self._normalize_tag_keys(
                        [str(item) for item in patch["tag_keys"]]
                    )
                if "metrics" in patch and isinstance(patch["metrics"], dict):
                    checkin.metrics = self._normalize_metric_values(patch["metrics"])
                checkin.updated_at = self._now_utc()
                await session.commit()
                await session.refresh(checkin)
                return {"status": "success", "message": "Check-in updated successfully", "data": checkin.to_dict()}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating check-in: {str(exc)}", "data": None}

    async def delete_checkin(self, user_id: str, checkin_id: str) -> Dict[str, object]:
        """Delete one existing check-in row.

        Args:
            user_id (str): Authenticated user identifier.
            checkin_id (str): Check-in identifier scoped by user.

        Returns:
            Dict[str, object]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(
                    select(WellnessCheckIn).where(
                        and_(
                            WellnessCheckIn.user_id == user_id,
                            WellnessCheckIn.id == checkin_id,
                        ),
                    ),
                )
                checkin = result.scalar_one_or_none()
                if checkin is None:
                    return {"status": "error", "message": "Check-in not found", "data": None}
                await session.delete(checkin)
                await self._record_tombstone(session, user_id, "wellness_checkin", checkin_id)
                await session.commit()
                return {"status": "success", "message": "Check-in deleted successfully", "data": {"id": checkin_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting check-in: {str(exc)}", "data": None}

    async def list_diary_entries(self, user_id: str, limit: int = 20) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(select(WellnessDiaryEntry).where(WellnessDiaryEntry.user_id == user_id).order_by(WellnessDiaryEntry.created_at.desc()).limit(limit))
                items = [await self._build_diary_item(session, user_id, entry) for entry in result.scalars().all()]
                return {"status": "success", "data": {"items": items}}
        except Exception as exc:
            return {"status": "error", "message": f"Error loading diary entries: {str(exc)}", "data": None}

    async def create_diary_entry(self, user_id: str, title: str, summary: str, mood_score: int, tag_keys: List[str], related_activity_id: Optional[str] = None) -> Dict[str, object]:
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                related_activity = await self._find_activity(session, user_id, related_activity_id)
                if related_activity_id and related_activity is None:
                    return {"status": "error", "message": "Related activity not found", "data": None}
                now = self._now_utc()
                entry = WellnessDiaryEntry(user_id=user_id, id=str(uuid4()), title_key=None, title=title.strip(), summary_key=None, summary=summary.strip(), mood_state_key=self._metric_state_key("mood", mood_score), mood_score=mood_score, related_activity_id=related_activity_id, created_at=now, updated_at=now)
                entry.tag_keys = self._normalize_tag_keys(tag_keys)
                session.add(entry)
                await session.commit()
                payload = await self._build_diary_item(session, user_id, entry)
                return {"status": "success", "message": "Diary entry created successfully", "data": payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error creating diary entry: {str(exc)}", "data": None}

    async def update_diary_entry(
        self,
        user_id: str,
        entry_id: str,
        patch: Dict[str, object],
    ) -> Dict[str, object]:
        """Update one existing diary entry row.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.
            patch (Dict[str, object]): Mutable diary fields to replace.

        Returns:
            Dict[str, object]: Provider-normalized mutation result.
        """
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(
                    select(WellnessDiaryEntry).where(
                        and_(
                            WellnessDiaryEntry.user_id == user_id,
                            WellnessDiaryEntry.id == entry_id,
                        ),
                    ),
                )
                entry = result.scalar_one_or_none()
                if entry is None:
                    return {"status": "error", "message": "Diary entry not found", "data": None}

                if "title" in patch and isinstance(patch["title"], str):
                    entry.title = patch["title"].strip()
                    entry.title_key = None
                if "summary" in patch and isinstance(patch["summary"], str):
                    entry.summary = patch["summary"].strip()
                    entry.summary_key = None
                if "mood_score" in patch and patch["mood_score"] is not None:
                    entry.mood_score = int(patch["mood_score"])
                    entry.mood_state_key = self._metric_state_key("mood", entry.mood_score)
                if "tag_keys" in patch and isinstance(patch["tag_keys"], list):
                    entry.tag_keys = self._normalize_tag_keys(
                        [str(item) for item in patch["tag_keys"]]
                    )
                if "related_activity_id" in patch:
                    related_activity_id = self._optional_text(patch["related_activity_id"])
                    if (
                        related_activity_id
                        and await self._find_activity(session, user_id, related_activity_id) is None
                    ):
                        return {"status": "error", "message": "Related activity not found", "data": None}
                    entry.related_activity_id = related_activity_id
                entry.updated_at = self._now_utc()
                await session.commit()
                await session.refresh(entry)
                payload = await self._build_diary_item(session, user_id, entry)
                return {"status": "success", "message": "Diary entry updated successfully", "data": payload}
        except Exception as exc:
            return {"status": "error", "message": f"Error updating diary entry: {str(exc)}", "data": None}

    async def delete_diary_entry(self, user_id: str, entry_id: str) -> Dict[str, object]:
        """Delete one existing diary entry row.

        Args:
            user_id (str): Authenticated user identifier.
            entry_id (str): Diary entry identifier scoped by user.

        Returns:
            Dict[str, object]: Provider-normalized deletion result.
        """
        try:
            await self._ensure_seed_data(user_id)
            async with self.handler.AsyncSessionLocal() as session:
                result = await session.execute(
                    select(WellnessDiaryEntry).where(
                        and_(
                            WellnessDiaryEntry.user_id == user_id,
                            WellnessDiaryEntry.id == entry_id,
                        ),
                    ),
                )
                entry = result.scalar_one_or_none()
                if entry is None:
                    return {"status": "error", "message": "Diary entry not found", "data": None}
                await session.delete(entry)
                await self._record_tombstone(session, user_id, "wellness_diary_entry", entry_id)
                await session.commit()
                return {"status": "success", "message": "Diary entry deleted successfully", "data": {"id": entry_id}}
        except Exception as exc:
            return {"status": "error", "message": f"Error deleting diary entry: {str(exc)}", "data": None}
