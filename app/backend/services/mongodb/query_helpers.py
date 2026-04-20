"""Query helpers for the MongoDB wellness runtime."""
from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.mongodb.common import normalize_document


async def find_activity_doc(collection, *, user_id: str, activity_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return one activity payload for the given user-scoped id."""
    if not activity_id:
        return None
    return await collection.find_one({"user_id": user_id, "id": activity_id}, {"_id": 0})


async def build_diary_item(activities_collection, *, user_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Attach related activity metadata to a diary entry payload."""
    item = normalize_document(entry) or {}
    related_activity = await find_activity_doc(
        activities_collection,
        user_id=user_id,
        activity_id=item.get("related_activity_id"),
    )
    item["related_activity_title_key"] = related_activity.get("title_key") if related_activity else None
    item["related_activity_title"] = related_activity.get("title") if related_activity else None
    return item


async def build_sync_change(activities_collection, *, user_id: str, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a backend document into the shared sync change envelope."""
    normalized = normalize_document(payload) or {}
    shaped_payload = normalized
    if entity_type == "wellness_diary_entry":
        shaped_payload = await build_diary_item(activities_collection, user_id=user_id, entry=normalized)
    return {
        "entity_type": entity_type,
        "entity_id": shaped_payload.get("id", ""),
        "action": "upsert",
        "updated_at": shaped_payload.get("updated_at") or shaped_payload.get("created_at"),
        "payload": shaped_payload,
    }
