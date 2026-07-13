"""Privacy-safe Startlist context helpers for Felix AI chat.

The module parses the untrusted device hint, keeps only bounded activity IDs,
intersects those IDs with the authenticated user's backend activity catalog,
and provides deterministic ordering without moving prompt ownership to the
client.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple


FELIX_AI_STARTLIST_ID_LIMIT = 24
"""Maximum activity IDs accepted from each Startlist tier."""

FELIX_AI_STARTLIST_ID_LENGTH = 128
"""Maximum length accepted for one activity ID."""

FELIX_AI_STARTLIST_CANDIDATE_LIMIT = 96
"""Maximum raw entries inspected from each untrusted Startlist tier."""


@dataclass(frozen=True)
class FelixAiStartlistContext:
    """Validated Startlist preferences for one Felix AI request.

    Attributes:
        current_activity_ids (Tuple[str, ...]): Ordered current-list IDs.
        automatic_activity_ids (Tuple[str, ...]): Ordered automatic-list IDs
            that were not already present in the current list.
    """

    current_activity_ids: Tuple[str, ...] = ()
    automatic_activity_ids: Tuple[str, ...] = ()

    @property
    def has_preferences(self) -> bool:
        """Return whether at least one validated preference is available.

        Returns:
            bool: True when either Startlist tier contains an activity ID.
        """
        return bool(self.current_activity_ids or self.automatic_activity_ids)

    def membership(self, activity_id: Any) -> str:
        """Return the Startlist tier for one activity ID.

        Args:
            activity_id (Any): Candidate backend activity ID.

        Returns:
            str: ``"current"``, ``"automatic"``, or an empty string when the
            activity has no validated Startlist membership.
        """
        normalized = str(activity_id or "").strip()
        if normalized in self.current_activity_ids:
            return "current"
        if normalized in self.automatic_activity_ids:
            return "automatic"
        return ""


def parse_felix_ai_startlist_context(
    external_context: Mapping[str, Any],
) -> FelixAiStartlistContext:
    """Parse the bounded Startlist portion of an untrusted client hint.

    Args:
        external_context (Mapping[str, Any]): Request external-context map.

    Returns:
        FelixAiStartlistContext: Normalized ID-only preferences. Malformed or
        absent payloads return an empty context rather than failing the request.

    Side Effects:
        None.
    """
    raw_startlist = external_context.get("startlist")
    if not isinstance(raw_startlist, Mapping):
        return FelixAiStartlistContext()
    current_ids = _sanitize_activity_ids(
        raw_startlist.get("current_activity_ids"),
    )
    automatic_ids = _sanitize_activity_ids(
        raw_startlist.get("automatic_activity_ids"),
        excluded=current_ids,
    )
    return FelixAiStartlistContext(current_ids, automatic_ids)


def intersect_felix_ai_startlist_context(
    context: FelixAiStartlistContext,
    activities: Iterable[Mapping[str, Any]],
) -> FelixAiStartlistContext:
    """Keep only Startlist IDs present in the backend activity catalog.

    Args:
        context (FelixAiStartlistContext): Parsed client preference hint.
        activities (Iterable[Mapping[str, Any]]): Authenticated user's backend
            activity rows.

    Returns:
        FelixAiStartlistContext: Catalog-backed preferences in client order.

    Side Effects:
        None.
    """
    catalog_ids = {
        str(activity.get("id") or "").strip()
        for activity in activities
        if str(activity.get("id") or "").strip()
    }
    return FelixAiStartlistContext(
        tuple(item for item in context.current_activity_ids if item in catalog_ids),
        tuple(item for item in context.automatic_activity_ids if item in catalog_ids),
    )


def prioritize_felix_ai_activities(
    activities: Iterable[Dict[str, Any]],
    context: FelixAiStartlistContext,
) -> List[Dict[str, Any]]:
    """Order catalog rows by current, automatic, then catalog position.

    Args:
        activities (Iterable[Dict[str, Any]]): Backend activity rows.
        context (FelixAiStartlistContext): Catalog-validated preferences.

    Returns:
        List[Dict[str, Any]]: New ordered list without mutating input rows.

    Side Effects:
        None.
    """
    rows = list(activities)
    rows_by_id = {
        str(row.get("id") or "").strip(): row
        for row in rows
        if str(row.get("id") or "").strip()
    }
    preferred_ids = context.current_activity_ids + context.automatic_activity_ids
    prioritized = [rows_by_id[item] for item in preferred_ids if item in rows_by_id]
    selected_ids = set(preferred_ids)
    prioritized.extend(
        row
        for row in rows
        if str(row.get("id") or "").strip() not in selected_ids
    )
    return prioritized


def felix_ai_startlist_debug_payload(
    context: FelixAiStartlistContext,
) -> Dict[str, int]:
    """Build count-only diagnostics for a validated Startlist hint.

    Args:
        context (FelixAiStartlistContext): Catalog-validated preferences.

    Returns:
        Dict[str, int]: Current and automatic activity counts without IDs.

    Side Effects:
        None.
    """
    return {
        "current_activity_count": len(context.current_activity_ids),
        "automatic_activity_count": len(context.automatic_activity_ids),
    }


def _sanitize_activity_ids(
    value: Any,
    *,
    excluded: Iterable[str] = (),
) -> Tuple[str, ...]:
    """Normalize one untrusted ordered activity-ID collection.

    Args:
        value (Any): Candidate list or tuple from the request payload.
        excluded (Iterable[str]): IDs owned by a higher-priority tier.

    Returns:
        Tuple[str, ...]: Unique bounded IDs in first-seen order.

    Side Effects:
        None.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    seen = set(excluded)
    normalized: List[str] = []
    for item in value[:FELIX_AI_STARTLIST_CANDIDATE_LIMIT]:
        if not isinstance(item, str):
            continue
        activity_id = item.strip()
        if not activity_id or len(activity_id) > FELIX_AI_STARTLIST_ID_LENGTH:
            continue
        if activity_id in seen:
            continue
        seen.add(activity_id)
        normalized.append(activity_id)
        if len(normalized) == FELIX_AI_STARTLIST_ID_LIMIT:
            break
    return tuple(normalized)
