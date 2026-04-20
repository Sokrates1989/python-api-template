"""Shared helpers for MongoDB-backed wellness and sync services."""
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
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Serialize a datetime using the shared UTC format."""
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string."""
    return datetime.fromisoformat(value)


def metric_state_key(metric: str, score: int) -> str:
    """Map a numeric score to the shared UI state key."""
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


def normalize_document(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a plain Mongo document without the internal `_id` field."""
    if not doc:
        return None
    data = dict(doc)
    data.pop("_id", None)
    return data


def normalize_tag_keys(tag_keys: List[str]) -> List[str]:
    """Normalize diary tag keys into the shared lowercase underscore format."""
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


def starter_activities(user_id: str) -> List[Dict[str, Any]]:
    """Build the shared starter activity catalog for one user."""
    now = now_utc().replace(hour=9, minute=0, second=0, microsecond=0)
    created_at = iso_utc(now)
    return [
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
            "created_at": created_at,
            "updated_at": created_at,
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
            "created_at": created_at,
            "updated_at": created_at,
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
            "created_at": created_at,
            "updated_at": created_at,
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
            "created_at": created_at,
            "updated_at": created_at,
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
            "created_at": created_at,
            "updated_at": created_at,
        },
    ]


def looks_like_legacy_seed_checkins(checkin_docs: List[Dict[str, Any]]) -> bool:
    """Return whether stored check-ins still match the legacy seed pattern."""
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
            recorded_at = parse_iso(str(recorded_at_raw)).astimezone(timezone.utc)
            created_at = parse_iso(str(created_at_raw)).astimezone(timezone.utc)
            updated_at = parse_iso(str(updated_at_raw)).astimezone(timezone.utc)
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


def build_latest_checkin_payload(checkin: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shape one raw check-in document into the dashboard payload."""
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


def build_weekly_trend(trend_records: Iterable[Dict[str, Any]]) -> List[Dict[str, Optional[float]]]:
    """Aggregate recent check-ins into the seven-day dashboard trend."""
    trend_by_date: Dict[date, List[int]] = {}
    for item in trend_records:
        recorded_at = parse_iso(str(item["recorded_at"])).astimezone(timezone.utc).date()
        trend_by_date.setdefault(recorded_at, []).append(int(item.get("mood_score") or 0))

    today = now_utc().date()
    weekly_trend: List[Dict[str, Optional[float]]] = []
    for offset in range(6, -1, -1):
        target_day = today - timedelta(days=offset)
        mood_values = trend_by_date.get(target_day, [])
        value = round(sum(mood_values) / len(mood_values), 1) if mood_values else None
        weekly_trend.append({"day_key": WEEKDAY_KEYS[target_day.weekday()], "value": value})
    return weekly_trend


def build_activity_categories(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build the category summary payload for the activity list."""
    categories: List[Dict[str, Any]] = []
    for category_key, definition in CATEGORY_DEFINITIONS.items():
        count = sum(1 for item in activities if category_key in item.get("category_keys", []))
        categories.append(
            {
                "key": category_key,
                "title_key": definition["title_key"],
                "description_key": definition["description_key"],
                "item_count": count,
            }
        )
    return categories
