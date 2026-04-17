"""Sync conflict log for SQL-backed sync replay."""

from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from .base import Base


class SyncConflictLog(Base):
    """Stores detected sync conflicts for later inspection."""

    __tablename__ = "sync_conflicts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    op_id = Column(String(128), nullable=False, index=True)
    feature = Column(String(64), nullable=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(255), nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    result_json = Column(Text, nullable=False)

    def get_result(self) -> Dict[str, Any]:
        """Return stored conflict payload as dictionary."""
        return json.loads(self.result_json)

    @staticmethod
    def dump_result(result: Dict[str, Any]) -> str:
        """Serialize conflict payload for storage."""
        return json.dumps(result, separators=(",", ":"), default=str)
