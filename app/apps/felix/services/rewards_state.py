"""Felix rewards-state normalization helpers.

This module is intentionally app-owned because reward cards, media preferences,
and streak-saver semantics are Felix product behavior rather than shared
template behavior. Database services call these helpers so MongoDB, SQL, and
Neo4j return the same JSON contract.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


DEFAULT_FORMAT_ORDER = ["video", "audio", "text"]
"""Default FelixAppNew media format priority."""

ALLOWED_FORMATS = {"video", "audio", "text"}
"""Reward media formats accepted by Felix."""

ALLOWED_LANGUAGES = {"app", "de", "en"}
"""Reward media language keys accepted by Felix."""

ALLOWED_SPEAKERS = {"any", "female", "male"}
"""Reward media speaker keys accepted by Felix."""


def default_media_preferences() -> Dict[str, Any]:
    """Return default Felix reward media preferences.

    Args:
        None.

    Returns:
        Dict[str, Any]: Fresh media preference dictionary.

    Side Effects:
        None.
    """
    return {
        "format_order": list(DEFAULT_FORMAT_ORDER),
        "language": "app",
        "speaker": "any",
        "subtitles_enabled": True,
    }


def default_rewards_state() -> Dict[str, Any]:
    """Return default Felix rewards state for a new user.

    Args:
        None.

    Returns:
        Dict[str, Any]: Fresh reward-state dictionary.

    Side Effects:
        None.
    """
    return {
        "purchases": [],
        "spent_suns": 0,
        "last_seen_earned_suns": 0,
        "last_celebrated_earned_suns": 0,
        "streak_savers_available": 0,
        "streak_savers_max": 1,
        "streak_saver_used_day_keys": [],
        "last_streak_saver_grant_day_key": None,
        "media_preferences": default_media_preferences(),
    }


def normalize_rewards_state(raw_state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize a stored Felix rewards-state document.

    Args:
        raw_state (Optional[Mapping[str, Any]]): Stored document or partial
            state dictionary.

    Returns:
        Dict[str, Any]: Complete canonical rewards-state dictionary.

    Side Effects:
        None.
    """
    raw = dict(raw_state or {})
    return {
        "purchases": _normalize_string_list(raw.get("purchases")),
        "spent_suns": _normalize_non_negative_int(raw.get("spent_suns")),
        "last_seen_earned_suns": _normalize_non_negative_int(raw.get("last_seen_earned_suns")),
        "last_celebrated_earned_suns": _normalize_non_negative_int(raw.get("last_celebrated_earned_suns")),
        "streak_savers_available": _normalize_non_negative_int(raw.get("streak_savers_available")),
        "streak_savers_max": max(1, _normalize_non_negative_int(raw.get("streak_savers_max"), default=1)),
        "streak_saver_used_day_keys": _normalize_string_list(raw.get("streak_saver_used_day_keys")),
        "last_streak_saver_grant_day_key": _normalize_optional_string(
            raw.get("last_streak_saver_grant_day_key")
        ),
        "media_preferences": normalize_media_preferences(raw.get("media_preferences")),
    }


def normalize_rewards_patch(
    patch: Mapping[str, Any],
    *,
    current_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge a partial rewards-state patch into current state.

    Args:
        patch (Mapping[str, Any]): Client-supplied update fields.
        current_state (Optional[Mapping[str, Any]]): Existing state used as the
            merge base. Defaults are used when missing.

    Returns:
        Dict[str, Any]: Complete normalized rewards-state dictionary.

    Side Effects:
        None.
    """
    merged = normalize_rewards_state(current_state)
    patch_map = dict(patch or {})
    for key in (
        "purchases",
        "spent_suns",
        "last_seen_earned_suns",
        "last_celebrated_earned_suns",
        "streak_savers_available",
        "streak_savers_max",
        "streak_saver_used_day_keys",
        "last_streak_saver_grant_day_key",
    ):
        if key in patch_map:
            merged[key] = patch_map[key]
    if "media_preferences" in patch_map:
        merged["media_preferences"] = normalize_media_preferences(
            patch_map.get("media_preferences"),
            current=merged.get("media_preferences"),
        )
    return normalize_rewards_state(merged)


def normalize_media_preferences(
    raw_preferences: Any,
    *,
    current: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize Felix reward media preferences.

    Args:
        raw_preferences (Any): Stored or client-supplied preference mapping.
        current (Optional[Mapping[str, Any]]): Existing preferences used as the
            merge base for partial updates.

    Returns:
        Dict[str, Any]: Canonical media-preference dictionary.

    Side Effects:
        None.
    """
    result = deepcopy(default_media_preferences())
    if current:
        result.update(_normalize_media_mapping(current))
    if isinstance(raw_preferences, Mapping):
        result.update(_normalize_media_mapping(raw_preferences))
    return result


def _normalize_media_mapping(raw_preferences: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize one media-preference mapping.

    Args:
        raw_preferences (Mapping[str, Any]): Raw preference fields.

    Returns:
        Dict[str, Any]: Valid normalized fields present in the input.

    Side Effects:
        None.
    """
    normalized: Dict[str, Any] = {}
    if "format_order" in raw_preferences:
        normalized["format_order"] = _normalize_format_order(raw_preferences.get("format_order"))
    if "language" in raw_preferences:
        language = str(raw_preferences.get("language") or "").strip()
        normalized["language"] = language if language in ALLOWED_LANGUAGES else "app"
    if "speaker" in raw_preferences:
        speaker = str(raw_preferences.get("speaker") or "").strip()
        normalized["speaker"] = speaker if speaker in ALLOWED_SPEAKERS else "any"
    if "subtitles_enabled" in raw_preferences:
        normalized["subtitles_enabled"] = bool(raw_preferences.get("subtitles_enabled"))
    return normalized


def _normalize_format_order(value: Any) -> List[str]:
    """Normalize media format priority order.

    Args:
        value (Any): Raw list-like format order.

    Returns:
        List[str]: Unique valid formats with missing defaults appended.

    Side Effects:
        None.
    """
    ordered: List[str] = []
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        for item in value:
            candidate = str(item).strip()
            if candidate in ALLOWED_FORMATS and candidate not in ordered:
                ordered.append(candidate)
    for item in DEFAULT_FORMAT_ORDER:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _normalize_string_list(value: Any) -> List[str]:
    """Normalize a list-like value into unique non-empty strings.

    Args:
        value (Any): Raw list-like value.

    Returns:
        List[str]: Unique strings in first-seen order.

    Side Effects:
        None.
    """
    normalized: List[str] = []
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return normalized
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_non_negative_int(value: Any, *, default: int = 0) -> int:
    """Normalize a raw value into a non-negative integer.

    Args:
        value (Any): Raw numeric value.
        default (int): Fallback used when conversion fails.

    Returns:
        int: Non-negative integer.

    Side Effects:
        None.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, parsed)


def _normalize_optional_string(value: Any) -> Optional[str]:
    """Normalize an optional string.

    Args:
        value (Any): Raw optional value.

    Returns:
        Optional[str]: Trimmed string, or None for blank values.

    Side Effects:
        None.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None
