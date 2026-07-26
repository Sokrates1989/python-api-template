"""Canonical starter activity catalog shared by all wellness providers.

The definitions mirror the Felix Flutter/PWA catalog. Provider runtimes add
their own owner ids and timestamps, but must not maintain separate seed lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class StarterCategory:
    """Describe one immutable starter category.

    Attributes:
        key: Stable category identifier.
        title_key: Localization key for the visible title.
        description_key: Localization key for supporting copy.
        icon_key: Cross-client icon-registry identifier.
        sort_order: Stable display order.
    """

    key: str
    title_key: str
    description_key: str
    icon_key: str
    sort_order: int


@dataclass(frozen=True)
class StarterActivity:
    """Describe one immutable starter activity.

    Attributes:
        activity_id: Stable activity identifier.
        icon_key: Cross-client icon-registry identifier.
        title_key: Localization key for the visible title.
        summary_key: Optional localization key for supporting copy.
        duration_minutes: Suggested execution duration.
        favorite: Whether the starter is initially favorited.
        category_keys: Categories assigned to the activity.
        sort_order: Stable display order.
        harmful: Whether the activity records an intentionally harmful habit.
    """

    activity_id: str
    icon_key: str
    title_key: str
    duration_minutes: int
    favorite: bool
    category_keys: Tuple[str, ...]
    sort_order: int
    summary_key: str | None = None
    harmful: bool = False


#
# Canonical category definitions.
# These ids and localization keys match FelixDefaultActivityCatalog.
#
STARTER_CATEGORIES: Tuple[StarterCategory, ...] = (
    StarterCategory("breathing", "app_shell.activities.category_breathing", "app_shell.activities.category_breathing_description", "Wind", 10),
    StarterCategory("movement", "app_shell.activities.category_movement", "app_shell.activities.category_movement_description", "Footprints", 20),
    StarterCategory("nature", "app_shell.activities.category_nature", "app_shell.activities.category_nature_description", "TreePine", 30),
    StarterCategory("social", "app_shell.activities.category_social", "app_shell.activities.category_social_description", "Users", 40),
    StarterCategory("creativity", "app_shell.activities.category_creativity", "app_shell.activities.category_creativity_description", "Palette", 50),
    StarterCategory("music", "app_shell.activities.category_music", "app_shell.activities.category_music_description", "Music", 55),
    StarterCategory("food", "app_shell.activities.category_food", "app_shell.activities.category_food_description", "Soup", 60),
    StarterCategory("mindset", "app_shell.activities.category_mindset", "app_shell.activities.category_mindset_description", "NotebookPen", 70),
    StarterCategory("home", "app_shell.activities.category_home", "app_shell.activities.category_home_description", "Home", 80),
    StarterCategory("recovery", "app_shell.activities.category_recovery", "app_shell.activities.category_recovery_description", "HeartPulse", 90),
    StarterCategory("sleep", "app_shell.activities.category_sleep", "app_shell.activities.category_sleep_description", "Moon", 100),
    StarterCategory("mornings", "app_shell.activities.category_mornings", "app_shell.activities.category_mornings_description", "Coffee", 110),
    StarterCategory("evenings", "app_shell.activities.category_evenings", "app_shell.activities.category_evenings_description", "Lamp", 120),
    StarterCategory("stress", "app_shell.activities.category_stress", "app_shell.activities.category_stress_description", "Waves", 130),
    StarterCategory("hygiene", "app_shell.activities.category_hygiene", "app_shell.activities.category_hygiene_description", "Droplets", 140),
    StarterCategory("harmful", "app_shell.activities.category_harmful", "app_shell.activities.category_harmful_description", "Zap", 150),
)


#
# Canonical activity definitions.
# The catalog is intentionally complete so a non-empty backend response does
# not suppress Flutter's local fallback while still omitting most defaults.
#
STARTER_ACTIVITIES: Tuple[StarterActivity, ...] = (
    StarterActivity("getting-started", "NotebookPen", "app_shell.activities.default_getting_started_title", 1, True, ("mindset", "home"), 5, "app_shell.activities.default_getting_started_reminder"),
    StarterActivity("box-breathing", "Wind", "app_shell.activities.default_box_breathing_title", 1, True, ("breathing", "recovery", "stress"), 10),
    StarterActivity("fresh-air", "TreePine", "app_shell.activities.default_fresh_air_title", 5, True, ("nature", "movement", "recovery", "stress"), 20),
    StarterActivity("drink-water", "Soup", "app_shell.activities.default_drink_water_title", 2, False, ("food", "mornings", "recovery"), 30),
    StarterActivity("walk-10min", "TreePine", "app_shell.activities.default_walk_10min_title", 10, False, ("nature", "movement", "recovery"), 40),
    StarterActivity("stretching", "Footprints", "app_shell.activities.default_stretching_title", 3, False, ("movement", "recovery", "mornings"), 50),
    StarterActivity("social-check-in", "Users", "app_shell.activities.default_call_friend_title", 5, False, ("social",), 60),
    StarterActivity("mindful-music", "Music", "app_shell.activities.default_music_title", 4, False, ("music", "creativity", "mindset", "evenings", "recovery"), 70),
    StarterActivity("mini-tidy", "NotebookPen", "app_shell.activities.default_mini_tidy_title", 5, False, ("mindset", "home", "stress"), 80),
    StarterActivity("body-scan", "Wind", "app_shell.activities.default_body_scan_title", 2, False, ("breathing", "mindset", "recovery", "stress", "sleep"), 90),
    StarterActivity("warm-drink", "Soup", "app_shell.activities.default_warm_drink_title", 5, False, ("food", "recovery", "evenings", "sleep"), 100),
    StarterActivity("short-journal", "NotebookPen", "app_shell.activities.default_short_journal_title", 3, False, ("mindset", "evenings", "stress"), 110),
    StarterActivity("shower-reset", "Droplets", "app_shell.activities.default_shower_reset_title", 10, False, ("hygiene", "home", "recovery"), 120),
    StarterActivity("couch-rest", "HeartPulse", "app_shell.activities.default_couch_rest_title", 15, False, ("recovery", "home", "evenings"), 130),
    StarterActivity("power-nap", "Moon", "app_shell.activities.default_power_nap_title", 20, False, ("sleep", "recovery"), 140),
    StarterActivity("breakfast", "Soup", "app_shell.activities.default_breakfast_title", 15, False, ("food", "mornings"), 150),
    StarterActivity("healthy-snack", "Soup", "app_shell.activities.default_healthy_snack_title", 10, False, ("food", "home", "mornings"), 160),
    StarterActivity("read-book", "NotebookPen", "app_shell.activities.default_read_book_title", 15, False, ("mindset", "evenings", "recovery", "sleep", "creativity"), 170),
    StarterActivity("sunlight-bench", "TreePine", "app_shell.activities.default_sunlight_bench_title", 10, False, ("nature", "recovery", "mornings"), 180),
    StarterActivity("active-recovery", "HeartPulse", "app_shell.activities.default_active_recovery_title", 15, False, ("recovery", "movement", "stress"), 190),
    StarterActivity("calming-breaths", "Wind", "app_shell.activities.default_calming_breaths_title", 1, False, ("breathing", "mornings", "stress"), 200),
    StarterActivity("bike-ride", "Footprints", "app_shell.activities.default_bike_ride_title", 20, False, ("movement", "nature", "recovery"), 210),
    StarterActivity("call-someone", "Users", "app_shell.activities.default_call_someone_title", 10, False, ("social", "recovery"), 220),
    StarterActivity("shared-walk", "Users", "app_shell.activities.default_shared_walk_title", 20, False, ("social", "nature", "movement"), 230),
    StarterActivity("calming-playlist", "Music", "app_shell.activities.default_calming_playlist_title", 10, False, ("music", "stress", "recovery", "evenings"), 240),
    StarterActivity("sing-along", "Music", "app_shell.activities.default_sing_along_title", 5, False, ("music", "creativity", "recovery"), 250),
    StarterActivity("creative-doodle", "Palette", "app_shell.activities.default_creative_doodle_title", 5, False, ("creativity", "home", "recovery", "mindset"), 260),
    StarterActivity("healthy-meal", "Soup", "app_shell.activities.default_healthy_meal_title", 20, False, ("food", "home", "evenings"), 270),
    StarterActivity("brush-teeth-face", "Droplets", "app_shell.activities.default_brush_teeth_face_title", 5, False, ("hygiene", "mornings", "evenings"), 280),
    StarterActivity("fresh-clothes", "Droplets", "app_shell.activities.default_fresh_clothes_title", 5, False, ("hygiene", "home", "mornings"), 290),
    StarterActivity("sleep-wind-down", "Moon", "app_shell.activities.default_sleep_wind_down_title", 15, False, ("sleep", "evenings", "recovery"), 300),
    StarterActivity("doom-scrolling", "Zap", "app_shell.activities.default_doom_scrolling_title", 0, False, ("harmful", "evenings"), 310, harmful=True),
    StarterActivity("late-screen-spiral", "Zap", "app_shell.activities.default_late_screen_spiral_title", 0, False, ("harmful", "evenings", "sleep"), 320, harmful=True),
    StarterActivity("skip-breaks", "Zap", "app_shell.activities.default_skip_breaks_title", 0, False, ("harmful", "stress"), 330, harmful=True),
)

# Derived signatures used for complete-provider seed verification.
STARTER_ACTIVITY_IDS = frozenset(item.activity_id for item in STARTER_ACTIVITIES)
STARTER_CATEGORY_KEYS = frozenset(item.key for item in STARTER_CATEGORIES)


#
# Obsolete provider-local seed signatures.
# Only an exact match is eligible for one-time replacement. Partial or custom
# catalogs must remain untouched.
#
LEGACY_STARTER_ACTIVITY_IDS = frozenset(
    {
        "breathe-reset",
        "clarity-journal",
        "soft-stretch",
        "focus-walk",
        "pause-and-tea",
    }
)
LEGACY_STARTER_CATEGORY_KEYS = frozenset({"calm", "focus", "energy"})


def should_seed_starter_group(
    persisted_identifiers: Iterable[str],
    *,
    legacy_identifiers: AbstractSet[str],
    has_tombstones: bool,
) -> bool:
    """Return whether an empty or exact obsolete group may receive defaults.

    Args:
        persisted_identifiers (Iterable[str]): Complete stored ids or keys for
            one owner-scoped catalog group.
        legacy_identifiers (AbstractSet[str]): Exact obsolete seed signature
            eligible for one-time replacement.
        has_tombstones (bool): Whether the owner has deletion markers for this
            entity group.

    Returns:
        bool: ``True`` only for a brand-new empty group or the exact obsolete
        seed group, and only when no tombstone records user deletions.

    Side Effects:
        None.
    """
    identifiers = frozenset(persisted_identifiers)
    return not has_tombstones and (
        not identifiers or identifiers == legacy_identifiers
    )


def build_starter_activity_payloads(user_id: str) -> List[Dict[str, Any]]:
    """Build provider-neutral starter activity payloads for one owner.

    Args:
        user_id: Authenticated owner id added to every payload.

    Returns:
        List[Dict[str, Any]]: Fresh mutable dictionaries suitable for provider
        insertion after provider-specific timestamps are added.

    Side Effects:
        None.
    """
    return [
        {
            "id": item.activity_id,
            "user_id": user_id,
            "icon_key": item.icon_key,
            "title_key": item.title_key,
            "title": None,
            "summary_key": item.summary_key,
            "summary": None,
            "activity_reminder": None,
            "duration_minutes": item.duration_minutes,
            "favorite": item.favorite,
            "harmful": item.harmful,
            "category_keys": list(item.category_keys),
            "tags": [],
            "sort_order": item.sort_order,
            "energy_impact": None,
        }
        for item in STARTER_ACTIVITIES
    ]


def build_starter_category_payloads(user_id: str) -> List[Dict[str, Any]]:
    """Build provider-neutral starter category payloads for one owner.

    Args:
        user_id: Authenticated owner id added to every payload.

    Returns:
        List[Dict[str, Any]]: Fresh mutable category dictionaries.

    Side Effects:
        None.
    """
    return [
        {
            "user_id": user_id,
            "key": item.key,
            "title_key": item.title_key,
            "title": None,
            "description_key": item.description_key,
            "description": None,
            "icon_key": item.icon_key,
            "sort_order": item.sort_order,
        }
        for item in STARTER_CATEGORIES
    ]
