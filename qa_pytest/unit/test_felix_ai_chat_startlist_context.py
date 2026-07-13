"""Unit coverage for Felix AI Startlist context validation and selection."""
from __future__ import annotations

from apps.felix.services.ai_chat_service import _select_activity
from apps.felix.services.ai_chat_startlist_context import (
    FELIX_AI_STARTLIST_ID_LIMIT,
    intersect_felix_ai_startlist_context,
    parse_felix_ai_startlist_context,
    prioritize_felix_ai_activities,
)


def _activity(
    activity_id: str,
    *,
    favorite: bool = False,
    summary: str = "",
) -> dict[str, object]:
    """Build one minimal backend activity row for tests.

    Args:
        activity_id (str): Stable activity ID.
        favorite (bool): Whether the activity is a favorite. Defaults to False.
        summary (str): Optional searchable summary. Defaults to empty.

    Returns:
        dict[str, object]: Activity row accepted by selection helpers.
    """
    return {
        "id": activity_id,
        "title": activity_id.title(),
        "summary": summary,
        "favorite": favorite,
        "duration_minutes": 5,
        "category_keys": [],
    }


def test_parser_keeps_only_bounded_unique_string_ids() -> None:
    """Ensure malformed values cannot expand or enrich the client hint.

    Returns:
        None.
    """
    ids = [f"activity-{index}" for index in range(FELIX_AI_STARTLIST_ID_LIMIT + 4)]
    context = parse_felix_ai_startlist_context(
        {
            "startlist": {
                "current_activity_ids": [" first ", "first", None, *ids],
                "automatic_activity_ids": ["first", "automatic"],
                "settings": {"reset_time": "06:00"},
            }
        }
    )

    assert context.current_activity_ids[0] == "first"
    assert len(context.current_activity_ids) == FELIX_AI_STARTLIST_ID_LIMIT
    assert context.automatic_activity_ids == ("automatic",)

    exhausted = parse_felix_ai_startlist_context(
        {"startlist": {"current_activity_ids": [None] * 97 + ["too-late"]}}
    )
    assert not exhausted.has_preferences


def test_catalog_intersection_and_priority_ignore_unknown_ids() -> None:
    """Ensure only authenticated backend catalog rows influence ordering.

    Returns:
        None.
    """
    parsed = parse_felix_ai_startlist_context(
        {
            "startlist": {
                "current_activity_ids": ["unknown", "walk"],
                "automatic_activity_ids": ["stretch"],
            }
        }
    )
    activities = [_activity("rest"), _activity("stretch"), _activity("walk")]

    validated = intersect_felix_ai_startlist_context(parsed, activities)
    prioritized = prioritize_felix_ai_activities(activities, validated)

    assert validated.current_activity_ids == ("walk",)
    assert [item["id"] for item in prioritized] == ["walk", "stretch", "rest"]


def test_selection_prefers_startlist_within_metric_matches() -> None:
    """Ensure matching Startlist rows win before other metric matches.

    Returns:
        None.
    """
    activities = [
        _activity("favorite-calm", favorite=True, summary="stress"),
        _activity("startlist-calm", summary="stress"),
    ]
    parsed = parse_felix_ai_startlist_context(
        {"startlist": {"current_activity_ids": ["startlist-calm"]}}
    )
    validated = intersect_felix_ai_startlist_context(parsed, activities)
    prioritized = prioritize_felix_ai_activities(activities, validated)

    selected = _select_activity(prioritized, ["stress"], validated)
    selected_without_metric = _select_activity(prioritized, [], validated)

    assert selected is not None
    assert selected["id"] == "startlist-calm"
    assert selected_without_metric is not None
    assert selected_without_metric["id"] == "startlist-calm"
