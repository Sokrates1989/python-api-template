"""Sync operation result log for idempotent operation replay."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func
from .base import Base


class SyncOperationLog(Base):
    """Stores processed sync operation outcomes keyed by operation id."""

    __tablename__ = "sync_operation_log"

    op_id = Column(String(128), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    device_id = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(255), nullable=False)
    action = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def get_result(self) -> Dict[str, Any]:
        """Return stored result payload as dictionary."""
        return json.loads(self.result_json)

    @staticmethod
    def dump_result(result: Dict[str, Any]) -> str:
        """Serialize result payload for storage."""
        return json.dumps(result, separators=(",", ":"), default=str)
