"""Query helpers for the Neo4j wellness runtime.

This module isolates repeated Neo4j wellness read/query shaping logic so the
runtime service can stay below the repository file-size limit.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.neo4j.common import normalize_record


async def find_activity_doc(driver, *, user_id: str, activity_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return one activity payload for the given user-scoped id.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        activity_id (Optional[str]): Activity identifier to load.

    Returns:
        Optional[Dict[str, Any]]: Activity payload when found.
    """
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
    with driver.session() as session:
        record = session.run(query, user_id=user_id, activity_id=activity_id).single()
    return normalize_record(record["activity"]) if record else None


async def build_diary_item(driver, *, user_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Attach related activity metadata to a diary entry payload.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        entry (Dict[str, Any]): Raw diary entry payload.

    Returns:
        Dict[str, Any]: Enriched diary entry payload.
    """
    item = normalize_record(entry) or {}
    related_activity = await find_activity_doc(driver, user_id=user_id, activity_id=item.get("related_activity_id"))
    item["related_activity_title_key"] = related_activity.get("title_key") if related_activity else None
    item["related_activity_title"] = related_activity.get("title") if related_activity else None
    return item


async def build_sync_change(
    driver,
    *,
    user_id: str,
    entity_type: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a backend record into the shared sync change envelope.

    Args:
        driver: Neo4j driver instance used to open sessions.
        user_id (str): Authenticated user identifier.
        entity_type (str): Wellness entity type for the payload.
        payload (Dict[str, Any]): Stored backend payload.

    Returns:
        Dict[str, Any]: Sync change envelope.
    """
    normalized = normalize_record(payload) or {}
    shaped_payload = normalized
    if entity_type == "wellness_diary_entry":
        shaped_payload = await build_diary_item(driver, user_id=user_id, entry=normalized)
    return {
        "entity_type": entity_type,
        "entity_id": shaped_payload.get("id") or shaped_payload.get("key", ""),
        "action": "upsert",
        "updated_at": shaped_payload.get("updated_at") or shaped_payload.get("created_at"),
        "payload": shaped_payload,
    }
