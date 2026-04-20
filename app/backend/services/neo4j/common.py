"""Shared helpers for Neo4j-backed wellness and sync services.

This module centralizes timestamp normalization, payload shaping, starter
wellness content, and shared category metadata used by the Neo4j wellness
feature slice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
CATEGORY_DEFINITIONS = {
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


def now_utc() -> datetime:
    """Return the current UTC timestamp.

    Returns:
        datetime: Current timezone-aware UTC timestamp.
    """
    return datetime.now(timezone.utc)



def normalize_dt(value: datetime) -> datetime:
    """Normalize a datetime into timezone-aware UTC.

    Args:
        value (datetime): Incoming datetime to normalize.

    Returns:
        datetime: UTC-normalized datetime.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)



def iso_utc(value: datetime) -> str:
    """Serialize a datetime using the shared Z-suffixed UTC format.

    Args:
        value (datetime): Datetime to serialize.

    Returns:
        str: ISO-8601 timestamp suffixed with `Z`.
    """
    return normalize_dt(value).isoformat().replace("+00:00", "Z")



def parse_iso(value: Any) -> Optional[datetime]:
    """Parse an API timestamp into a UTC datetime when possible.

    Args:
        value (Any): Raw timestamp candidate.

    Returns:
        Optional[datetime]: Parsed UTC datetime or `None` when parsing fails.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return normalize_dt(parsed)



def payload_datetime(value: Any) -> Optional[datetime]:
    """Convert a payload timestamp field into a normalized datetime.

    Args:
        value (Any): Payload field containing a datetime or ISO string.

    Returns:
        Optional[datetime]: Parsed datetime when present and valid.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return normalize_dt(value)
    if isinstance(value, str):
        return parse_iso(value)
    return None



def metric_state_key(metric: str, score: int) -> str:
    """Map a numeric wellness score to the shared UI state key.

    Args:
        metric (str): Metric family such as `mood`, `stress`, or `energy`.
        score (int): Raw score value.

    Returns:
        str: UI state key describing the score bucket.
    """
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



def normalize_tag_keys(tag_keys: List[str]) -> List[str]:
    """Normalize diary tag keys into the shared lowercase underscore format.

    Args:
        tag_keys (List[str]): Raw tag labels received from API clients.

    Returns:
        List[str]: Deduplicated normalized tag keys capped at six items.
    """
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



def normalize_record(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a plain dictionary copy for Neo4j record payloads.

    Args:
        record (Optional[Dict[str, Any]]): Record payload from Neo4j projection.

    Returns:
        Optional[Dict[str, Any]]: Plain dict copy when the record exists.
    """
    if not record:
        return None
    return dict(record)



def starter_activities(user_id: str) -> List[Dict[str, Any]]:
    """Build the shared starter activity catalog for a user.

    Args:
        user_id (str): Authenticated user identifier.

    Returns:
        List[Dict[str, Any]]: Seed activity payloads ready for Neo4j insertion.
    """
    now = now_utc().replace(hour=9, minute=0, second=0, microsecond=0)
    created_at = iso_utc(now)
    payloads = [
        {"id": "breathe-reset", "icon_key": "air", "title_key": "app_shell.activities.seed_breathe_title", "summary_key": "app_shell.activities.seed_breathe_summary", "duration_minutes": 1, "favorite": True, "category_keys": ["calm", "focus"], "energy_impact": "reset"},
        {"id": "clarity-journal", "icon_key": "book", "title_key": "app_shell.activities.seed_journal_title", "summary_key": "app_shell.activities.seed_journal_summary", "duration_minutes": 8, "favorite": True, "category_keys": ["focus"], "energy_impact": "grounding"},
        {"id": "soft-stretch", "icon_key": "self_improvement", "title_key": "app_shell.activities.seed_stretch_title", "summary_key": "app_shell.activities.seed_stretch_summary", "duration_minutes": 6, "favorite": False, "category_keys": ["energy", "calm"], "energy_impact": "lift"},
        {"id": "focus-walk", "icon_key": "directions_walk", "title_key": "app_shell.activities.seed_walk_title", "summary_key": "app_shell.activities.seed_walk_summary", "duration_minutes": 12, "favorite": False, "category_keys": ["energy", "focus"], "energy_impact": "lift"},
        {"id": "pause-and-tea", "icon_key": "local_cafe", "title_key": "app_shell.activities.seed_tea_title", "summary_key": "app_shell.activities.seed_tea_summary", "duration_minutes": 10, "favorite": False, "category_keys": ["calm"], "energy_impact": "ease"},
    ]
    return [
        {
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
        }
        for item in payloads
    ]



def build_weekly_trend(trend_records: Iterable[Dict[str, Any]]) -> List[Dict[str, Optional[float]]]:
    """Aggregate recent check-in rows into the seven-day dashboard trend.

    Args:
        trend_records (Iterable[Dict[str, Any]]): Records containing `recorded_at`
            and `mood_score` values.

    Returns:
        List[Dict[str, Optional[float]]]: Ordered weekly trend payload.
    """
    trend_by_date: Dict[date, List[int]] = {}
    for item in trend_records:
        recorded_at = parse_iso(item["recorded_at"])
        if recorded_at is None:
            continue
        trend_by_date.setdefault(recorded_at.date(), []).append(int(item["mood_score"] or 0))

    today = now_utc().date()
    weekly_trend: List[Dict[str, Optional[float]]] = []
    for offset in range(6, -1, -1):
        target_day = today - timedelta(days=offset)
        mood_values = trend_by_date.get(target_day, [])
        value = round(sum(mood_values) / len(mood_values), 1) if mood_values else None
        weekly_trend.append({
            "day_key": WEEKDAY_KEYS[target_day.weekday()],
            "value": value,
        })
    return weekly_trend



def build_latest_checkin_payload(checkin: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shape one raw check-in record into the dashboard payload format.

    Args:
        checkin (Optional[Dict[str, Any]]): Raw stored check-in record.

    Returns:
        Optional[Dict[str, Any]]: Dashboard payload for the latest check-in.
    """
    if checkin is None:
        return None
    mood_score = int(checkin.get("mood_score") or 0)
    stress_score = int(checkin.get("stress_score") or 0)
    energy_score = int(checkin.get("energy_score") or 0)
    return {
        "recorded_at": checkin["recorded_at"],
        "mood": {"state_key": metric_state_key("mood", mood_score), "score": mood_score},
        "stress": {"state_key": metric_state_key("stress", stress_score), "score": stress_score},
        "energy": {"state_key": metric_state_key("energy", energy_score), "score": energy_score},
        "note": checkin.get("note"),
    }



def build_activity_categories(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the activity category summary for the wellness catalog response.

    Args:
        items (List[Dict[str, Any]]): Activity payloads returned for a user.

    Returns:
        List[Dict[str, Any]]: Category metadata plus item counts.
    """
    categories: List[Dict[str, Any]] = []
    for category_key, definition in CATEGORY_DEFINITIONS.items():
        count = sum(1 for item in items if category_key in item.get("category_keys", []))
        categories.append({
            "key": category_key,
            "title_key": definition["title_key"],
            "description_key": definition["description_key"],
            "item_count": count,
        })
    return categories
