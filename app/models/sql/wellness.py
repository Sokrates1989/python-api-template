from __future__ import annotations

import json
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


def _decode_string_list(value: str | None) -> List[str]:
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
    payload = [str(item) for item in (values or []) if str(item).strip()]
    return json.dumps(payload, separators=(",", ":"))


class WellnessActivity(Base):
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
    duration_minutes = Column(Integer, nullable=False)
    favorite = Column(Boolean, nullable=False, server_default="false")
    _category_keys = Column("category_keys", Text, nullable=False, server_default="[]")
    energy_impact = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def category_keys(self) -> List[str]:
        return _decode_string_list(self._category_keys)

    @category_keys.setter
    def category_keys(self, values: List[str] | None) -> None:
        self._category_keys = _encode_string_list(values)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "icon_key": self.icon_key,
            "title_key": self.title_key,
            "title": self.title,
            "summary_key": self.summary_key,
            "summary": self.summary,
            "duration_minutes": self.duration_minutes,
            "favorite": bool(self.favorite),
            "category_keys": self.category_keys,
            "energy_impact": self.energy_impact,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WellnessDiaryEntry(Base):
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
        return _decode_string_list(self._tag_keys)

    @tag_keys.setter
    def tag_keys(self, values: List[str] | None) -> None:
        self._tag_keys = _encode_string_list(values)

    def to_dict(self) -> dict:
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
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "mood_score": self.mood_score,
            "stress_score": self.stress_score,
            "energy_score": self.energy_score,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
