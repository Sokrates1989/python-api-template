"""Shared SQL ORM models for the reusable wellness feature runtime.

These models are intentionally feature-shared, not Felix-specific. Selected
backend apps that opt into SQL wellness routes must own their table creation in
``app/apps/<app_id>/migrations/versions`` so the global Alembic stream remains
provider-wide.
"""
from __future__ import annotations

import json
from typing import Dict, List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


def _decode_string_list(value: str | None) -> List[str]:
    """Decode a JSON string column into a clean list of strings.

    Args:
        value (str | None): Raw JSON payload stored in a text column.

    Returns:
        List[str]: Non-empty string values, or an empty list when decoding
        fails or the stored payload is not a list.

    Side Effects:
        None.
    """
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]


def _encode_string_list(values: List[str] | None) -> str:
    """Encode string-like values for storage in text JSON columns.

    Args:
        values (List[str] | None): Optional list of values to normalize.

    Returns:
        str: Compact JSON array containing non-empty string values.

    Side Effects:
        None.
    """
    payload = [str(item) for item in (values or []) if str(item).strip()]
    return json.dumps(payload, separators=(",", ":"))


def _decode_int_map(value: str | None) -> Dict[str, int]:
    """Decode a JSON string column into a clean integer metric map.

    Args:
        value (str | None): Raw JSON object stored in a text column.

    Returns:
        Dict[str, int]: Metric values keyed by non-empty strings. Values outside
        the 0-10 wellness score range are clamped defensively.

    Side Effects:
        None.
    """
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {
        str(key): max(0, min(10, int(raw_value)))
        for key, raw_value in decoded.items()
        if str(key).strip() and isinstance(raw_value, (int, float))
    }


def _encode_int_map(values: Dict[str, int] | None) -> str:
    """Encode metric values for storage in text JSON columns.

    Args:
        values (Dict[str, int] | None): Optional metric map to normalize.

    Returns:
        str: Compact JSON object containing 0-10 integer metric values.

    Side Effects:
        None.
    """
    payload = {
        str(key): max(0, min(10, int(value)))
        for key, value in (values or {}).items()
        if str(key).strip()
    }
    return json.dumps(payload, separators=(",", ":"))


class WellnessActivityCategory(Base):
    """SQL category row for a user-owned wellness activity catalog.

    Categories are persisted independently so custom names, icons, and ordering
    survive local, online, and hybrid runtime transitions.
    """

    __tablename__ = "wellness_activity_categories"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_wellness_activity_categories_user_key"),
        Index("ix_wellness_activity_categories_user_order", "user_id", "sort_order"),
    )

    pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(128), nullable=False)
    title_key = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    description_key = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    icon_key = Column(String(64), nullable=False, server_default="category")
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self, *, item_count: int = 0) -> dict:
        """Serialize category metadata with its computed activity count.

        Args:
            item_count (int): Number of activities assigned to this category.

        Returns:
            dict: API-friendly category fields.
        """
        return {
            "key": self.key,
            "title_key": self.title_key,
            "title": self.title,
            "description_key": self.description_key,
            "description": self.description,
            "icon_key": self.icon_key,
            "sort_order": int(self.sort_order or 0),
            "item_count": item_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WellnessActivity(Base):
    """SQL activity row used by apps that opt into shared wellness.

    Attributes:
        pk (int): Internal database primary key.
        user_id (str): Owner id from the shared users table.
        id (str): App-visible activity id scoped by user.
        icon_key (str): Icon identifier used by clients.
        title_key (str | None): Optional localization key for the title.
        title (str | None): Optional persisted title override.
        summary_key (str | None): Optional localization key for the summary.
        summary (str | None): Optional persisted summary override.
        duration_minutes (int): Suggested activity duration.
        favorite (bool): Whether the user favorited the activity.
        energy_impact (str | None): Optional energy impact descriptor.
        created_at (datetime): Row creation timestamp.
        updated_at (datetime): Row update timestamp.

    Methods:
        category_keys: Decodes and stores category keys.
        to_dict: Serializes the row for wellness service responses.
    """

    __tablename__ = "wellness_activities"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_wellness_activities_user_id_id"),
        Index("ix_wellness_activities_user_favorite", "user_id", "favorite"),
    )

    pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    id = Column(String(128), nullable=False)
    icon_key = Column(String(64), nullable=False)
    title_key = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    summary_key = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    activity_reminder = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    favorite = Column(Boolean, nullable=False, server_default="false")
    harmful = Column(Boolean, nullable=False, server_default="false")
    sort_order = Column(Integer, nullable=False, server_default="0")
    _tags = Column("tags", Text, nullable=False, server_default="[]")
    _category_keys = Column("category_keys", Text, nullable=False, server_default="[]")
    energy_impact = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def category_keys(self) -> List[str]:
        """Return decoded activity category keys.

        Returns:
            List[str]: Category identifiers, or an empty list when none are
            stored.

        Side Effects:
            None.
        """
        return _decode_string_list(self._category_keys)

    @category_keys.setter
    def category_keys(self, values: List[str] | None) -> None:
        """Store activity category keys as compact JSON text.

        Args:
            values (List[str] | None): Category identifiers to persist.

        Returns:
            None.

        Side Effects:
            Updates the mapped ``category_keys`` column value.
        """
        self._category_keys = _encode_string_list(values)

    @property
    def tags(self) -> List[str]:
        """Return decoded activity tags.

        Returns:
            List[str]: Stable activity tags.
        """
        return _decode_string_list(self._tags)

    @tags.setter
    def tags(self, values: List[str] | None) -> None:
        """Store activity tags as compact JSON text.

        Args:
            values (List[str] | None): Activity tags to persist.
        """
        self._tags = _encode_string_list(values)

    def to_dict(self) -> dict:
        """Serialize the activity row into an API-friendly dictionary.

        Args:
            None.

        Returns:
            dict: Activity fields with decoded categories and ISO timestamps.

        Side Effects:
            None.
        """
        return {
            "id": self.id,
            "icon_key": self.icon_key,
            "title_key": self.title_key,
            "title": self.title,
            "summary_key": self.summary_key,
            "summary": self.summary,
            "activity_reminder": self.activity_reminder,
            "duration_minutes": self.duration_minutes,
            "favorite": bool(self.favorite),
            "harmful": bool(self.harmful),
            "category_keys": self.category_keys,
            "tags": self.tags,
            "sort_order": int(self.sort_order or 0),
            "energy_impact": self.energy_impact,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WellnessSyncTombstone(Base):
    """SQL deletion marker consumed by incremental wellness synchronization."""

    __tablename__ = "wellness_sync_tombstones"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_wellness_sync_tombstones_entity"),
        Index("ix_wellness_sync_tombstones_user_deleted", "user_id", "deleted_at"),
    )

    pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_sync_change(self) -> dict:
        """Serialize the marker into a shared incremental delete envelope."""
        timestamp = self.deleted_at.isoformat() if self.deleted_at else None
        return {"entity_type": self.entity_type, "entity_id": self.entity_id, "action": "delete", "updated_at": timestamp, "payload": {}}


class WellnessDiaryEntry(Base):
    """SQL diary entry row used by apps that opt into shared wellness.

    Attributes:
        pk (int): Internal database primary key.
        user_id (str): Owner id from the shared users table.
        id (str): App-visible diary id scoped by user.
        title_key (str | None): Optional localization key for the title.
        title (str | None): Optional persisted title override.
        summary_key (str | None): Optional localization key for the summary.
        summary (str | None): Optional persisted summary override.
        mood_state_key (str): Mood state identifier.
        mood_score (int): Numeric mood value.
        related_activity_id (str | None): Optional related activity id.
        created_at (datetime): Row creation timestamp.
        updated_at (datetime): Row update timestamp.

    Methods:
        tag_keys: Decodes and stores tag keys.
        to_dict: Serializes the row for wellness service responses.
    """

    __tablename__ = "wellness_diary_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_wellness_diary_entries_user_id_id"),
        Index("ix_wellness_diary_entries_user_created_at", "user_id", "created_at"),
    )

    pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    id = Column(String(128), nullable=False)
    title_key = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    summary_key = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    mood_state_key = Column(String(64), nullable=False)
    mood_score = Column(Integer, nullable=False)
    _tag_keys = Column("tag_keys", Text, nullable=False, server_default="[]")
    related_activity_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def tag_keys(self) -> List[str]:
        """Return decoded diary tag keys.

        Returns:
            List[str]: Tag identifiers, or an empty list when none are stored.

        Side Effects:
            None.
        """
        return _decode_string_list(self._tag_keys)

    @tag_keys.setter
    def tag_keys(self, values: List[str] | None) -> None:
        """Store diary tag keys as compact JSON text.

        Args:
            values (List[str] | None): Tag identifiers to persist.

        Returns:
            None.

        Side Effects:
            Updates the mapped ``tag_keys`` column value.
        """
        self._tag_keys = _encode_string_list(values)

    def to_dict(self) -> dict:
        """Serialize the diary entry row into an API-friendly dictionary.

        Args:
            None.

        Returns:
            dict: Diary fields with decoded tags and ISO timestamps.

        Side Effects:
            None.
        """
        return {
            "id": self.id,
            "title_key": self.title_key,
            "title": self.title,
            "summary_key": self.summary_key,
            "summary": self.summary,
            "mood_state_key": self.mood_state_key,
            "mood_score": self.mood_score,
            "tag_keys": self.tag_keys,
            "related_activity_id": self.related_activity_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WellnessCheckIn(Base):
    """SQL check-in row used by apps that opt into shared wellness.

    Attributes:
        pk (int): Internal database primary key.
        user_id (str): Owner id from the shared users table.
        id (str): App-visible check-in id scoped by user.
        recorded_at (datetime): User-facing check-in timestamp.
        mood_score (int): Numeric mood value.
        stress_score (int): Numeric stress value.
        energy_score (int): Numeric energy value.
        tag_keys (List[str]): Semantic tags describing the check-in.
        metrics (Dict[str, int]): Flexible captured metrics.
        activity_id (str | None): Optional linked activity id.
        note (str | None): Optional user note.
        created_at (datetime): Row creation timestamp.
        updated_at (datetime): Row update timestamp.

    Methods:
        to_dict: Serializes the row for wellness service responses.
    """

    __tablename__ = "wellness_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_wellness_checkins_user_id_id"),
        Index("ix_wellness_checkins_user_recorded_at", "user_id", "recorded_at"),
    )

    pk = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    id = Column(String(128), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    mood_score = Column(Integer, nullable=False)
    stress_score = Column(Integer, nullable=False)
    energy_score = Column(Integer, nullable=False)
    _tag_keys = Column("tag_keys", Text, nullable=False, server_default="[]")
    _metrics = Column("metrics", Text, nullable=False, server_default="{}")
    activity_id = Column(String(128), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def tag_keys(self) -> List[str]:
        """Return decoded check-in tag keys.

        Returns:
            List[str]: Tag identifiers, or an empty list when none are stored.

        Side Effects:
            None.
        """
        return _decode_string_list(self._tag_keys)

    @tag_keys.setter
    def tag_keys(self, values: List[str] | None) -> None:
        """Store check-in tag keys as compact JSON text.

        Args:
            values (List[str] | None): Tag identifiers to persist.

        Returns:
            None.

        Side Effects:
            Updates the mapped ``tag_keys`` column value.
        """
        self._tag_keys = _encode_string_list(values)

    @property
    def metrics(self) -> Dict[str, int]:
        """Return decoded flexible check-in metrics.

        Returns:
            Dict[str, int]: Captured metric values keyed by metric id.

        Side Effects:
            None.
        """
        return _decode_int_map(self._metrics)

    @metrics.setter
    def metrics(self, values: Dict[str, int] | None) -> None:
        """Store flexible check-in metrics as compact JSON text.

        Args:
            values (Dict[str, int] | None): Metric values to persist.

        Returns:
            None.

        Side Effects:
            Updates the mapped ``metrics`` column value.
        """
        self._metrics = _encode_int_map(values)

    def to_dict(self) -> dict:
        """Serialize the check-in row into an API-friendly dictionary.

        Args:
            None.

        Returns:
            dict: Check-in fields with ISO timestamps.

        Side Effects:
            None.
        """
        return {
            "id": self.id,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "mood_score": self.mood_score,
            "stress_score": self.stress_score,
            "energy_score": self.energy_score,
            "tag_keys": self.tag_keys,
            "metrics": self.metrics,
            "activity_id": self.activity_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
